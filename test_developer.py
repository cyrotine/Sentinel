"""End-to-end test of the developer node against real ingested data.

Tests the full 7-stage pipeline:
  1. repo_analyzer -> RepoContext
  2. issue_analyzer -> IssueAnalysis
  3. issue_prioritizer -> SelectedIssue
  4. retrieve_context -> RetrievedChunks
  5. planner -> Plan
  6. developer -> CodeChanges
  7. State transitions verified

Repository: 70cc7b50-ca9d-41ef-be4c-bb56f1be9a82 (cyrotine/TempRepo)
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

from forge_workflows.state import (
    SentinelState,
    SentinelStatus,
    Plan,
    CodeChange,
)
from forge_workflows.graph import (
    repo_analyzer,
    issue_analyzer,
    issue_prioritizer,
    retrieve_context,
    planner,
    developer,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test")

REPO_ID = "70cc7b50-ca9d-41ef-be4c-bb56f1be9a82"


async def main() -> None:
    # ---------------------------------------------------------------
    # Phase 1: Initial state
    # ---------------------------------------------------------------
    state = SentinelState(repository_id=REPO_ID)

    print("\n" + "=" * 60)
    print("PHASE 1: Initial State")
    print("=" * 60)
    assert state.status == SentinelStatus.PENDING
    assert state.code_changes == []
    print("  status:        PENDING")
    print("  code_changes:  0")
    print("  [PASS] Initial state correct")

    # ---------------------------------------------------------------
    # Phase 2: repo_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 2: Run repo_analyzer")
    print("=" * 60)
    result = await repo_analyzer(state)
    state = state.model_copy(update=result)
    assert state.repo_context is not None
    print(f"  repo: {state.repo_context.repository_name}")
    print("  [PASS] repo_analyzer completed")

    # ---------------------------------------------------------------
    # Phase 3: issue_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 3: Run issue_analyzer")
    print("=" * 60)
    result = await issue_analyzer(state)
    state = state.model_copy(update=result)
    assert len(state.issue_analyses) > 0
    print(f"  issues classified: {len(state.issue_analyses)}")
    print("  [PASS] issue_analyzer completed")

    # ---------------------------------------------------------------
    # Phase 4: issue_prioritizer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 4: Run issue_prioritizer")
    print("=" * 60)
    result = await issue_prioritizer(state)
    state = state.model_copy(update=result)
    assert state.selected_issue is not None
    print(f"  selected: #{state.selected_issue.number} - {state.selected_issue.title}")
    print("  [PASS] issue_prioritizer completed")

    # ---------------------------------------------------------------
    # Phase 5: retrieve_context
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 5: Run retrieve_context")
    print("=" * 60)
    result = await retrieve_context(state)
    state = state.model_copy(update=result)
    assert len(state.relevant_chunks) > 0
    print(f"  chunks retrieved: {len(state.relevant_chunks)}")
    for c in state.relevant_chunks:
        print(f"    [{c.score:.4f}] {c.file_path} (L{c.start_line}-{c.end_line})")
    print("  [PASS] retrieve_context completed")

    # ---------------------------------------------------------------
    # Phase 6: planner
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 6: Run planner")
    print("=" * 60)
    result = await planner(state)
    state = state.model_copy(update=result)
    assert state.plan is not None
    print(f"  tasks: {len(state.plan.tasks)}")
    print(f"  affected_files: {state.plan.affected_files}")
    print("  [PASS] planner completed")

    # ---------------------------------------------------------------
    # Phase 7: developer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 7: Run developer")
    print("=" * 60)

    result = await developer(state)

    print(f"  Returned keys:    {list(result.keys())}")
    print(f"  status:           {result.get('status')}")
    print(f"  current_agent:    {result.get('current_agent')}")

    assert result["status"] == SentinelStatus.DEVELOPING
    assert result["current_agent"] == "developer"
    assert isinstance(result["code_changes"], list)
    assert len(result["code_changes"]) >= 1, "Expected at least 1 code change"

    code_changes = result["code_changes"]

    is_fallback = any("Fallback" in c.description for c in code_changes)
    print(f"\n  LLM Path: {'FALLBACK' if is_fallback else 'FULL LLM'}")

    for i, change in enumerate(code_changes, 1):
        assert isinstance(change, CodeChange)
        print(f"\n  --- CodeChange {i} ---")
        print(f"  file_path:   {change.file_path}")
        print(f"  description: {change.description}")
        print(f"  patch:")
        for line in change.patch.split("\n"):
            print(f"    {line}")

    # Validate index.html is targeted
    file_paths = [c.file_path for c in code_changes]
    assert "index.html" in file_paths, \
        f"Expected index.html in changes, got: {file_paths}"
    print(f"\n  [PASS] {len(code_changes)} CodeChange(s) generated")
    print(f"  [PASS] index.html targeted")

    # ---------------------------------------------------------------
    # Phase 8: State transition verification
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 8: State Transition Verification")
    print("=" * 60)

    updated_state = state.model_copy(update=result)

    print(f"  Before:  status={state.status}  changes={len(state.code_changes)}")
    print(f"  After:   status={updated_state.status}  changes={len(updated_state.code_changes)}")

    assert updated_state.status == SentinelStatus.DEVELOPING
    assert len(updated_state.code_changes) >= 1
    # Prior state persists
    assert updated_state.repo_context is not None
    assert len(updated_state.issue_analyses) > 0
    assert updated_state.selected_issue is not None
    assert len(updated_state.relevant_chunks) > 0
    assert updated_state.plan is not None
    # Original immutability
    assert state.code_changes == []

    print("  [PASS] State transition: PLANNING -> DEVELOPING")
    print("  [PASS] code_changes stored in SentinelState")
    print("  [PASS] All prior state fields persist")
    print("  [PASS] Original state immutability preserved")

    # Simulate completion
    completed = updated_state.model_copy(
        update={"status": SentinelStatus.COMPLETED, "current_agent": ""}
    )
    assert completed.status == SentinelStatus.COMPLETED
    assert len(completed.code_changes) >= 1
    print("  [PASS] State transition: DEVELOPING -> COMPLETED")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:      {updated_state.repo_context.repository_name}")
    print(f"  Selected issue:  #{updated_state.selected_issue.number} - {updated_state.selected_issue.title}")
    print(f"  Plan tasks:      {len(updated_state.plan.tasks)}")
    print(f"  Code changes:    {len(updated_state.code_changes)}")
    for c in updated_state.code_changes:
        print(f"    [{c.file_path}] {c.description}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
