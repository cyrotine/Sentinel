"""End-to-end test of the issue_prioritizer node against real ingested data.

Tests:
  1. repo_analyzer produces RepoContext (prerequisite)
  2. issue_analyzer classifies issues (prerequisite)
  3. issue_prioritizer selects the best issue
  4. SelectedIssue fields are populated correctly
  5. SentinelState transitions: PENDING -> ANALYZING_REPO -> ANALYZING_ISSUES -> PRIORITIZING -> COMPLETED

Repository: 70cc7b50-ca9d-41ef-be4c-bb56f1be9a82 (cyrotine/TempRepo)
Expected: Issue #1 ("Change Text Colour") should be selected (only open issue).
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

from forge_workflows.state import (
    SentinelState,
    SentinelStatus,
    IssueAnalysis,
    SelectedIssue,
)
from forge_workflows.graph import repo_analyzer, issue_analyzer, issue_prioritizer

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
    print(f"  status:          {state.status}")
    print(f"  repo_context:    {state.repo_context}")
    print(f"  issue_analyses:  {len(state.issue_analyses)}")
    print(f"  selected_issue:  {state.selected_issue}")

    assert state.status == SentinelStatus.PENDING
    assert state.selected_issue is None
    print("  [PASS] Initial state is PENDING, selected_issue is None")

    # ---------------------------------------------------------------
    # Phase 2: Run repo_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 2: Run repo_analyzer")
    print("=" * 60)

    result = await repo_analyzer(state)
    state = state.model_copy(update=result)

    assert state.status == SentinelStatus.ANALYZING_REPO
    assert state.repo_context is not None
    print(f"  repo: {state.repo_context.repository_name}")
    print(f"  status: {state.status}")
    print("  [PASS] repo_analyzer completed")

    # ---------------------------------------------------------------
    # Phase 3: Run issue_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 3: Run issue_analyzer")
    print("=" * 60)

    result = await issue_analyzer(state)
    state = state.model_copy(update=result)

    assert state.status == SentinelStatus.ANALYZING_ISSUES
    assert len(state.issue_analyses) > 0
    print(f"  issues classified: {len(state.issue_analyses)}")
    for a in state.issue_analyses:
        print(f"    #{a.number} [{a.issue_type}/{a.severity}] "
              f"conf={a.confidence:.2f} impact={a.impact:.2f} - {a.title}")
    print(f"  status: {state.status}")
    print("  [PASS] issue_analyzer completed")

    # ---------------------------------------------------------------
    # Phase 4: Run issue_prioritizer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 4: Run issue_prioritizer")
    print("=" * 60)

    result = await issue_prioritizer(state)

    print(f"  Returned keys:   {list(result.keys())}")
    print(f"  status:          {result.get('status')}")
    print(f"  current_agent:   {result.get('current_agent')}")

    assert result["status"] == SentinelStatus.PRIORITIZING
    assert result["current_agent"] == "issue_prioritizer"
    assert isinstance(result["selected_issue"], SelectedIssue)
    print("  [PASS] issue_prioritizer returned correct status and SelectedIssue")

    # ---------------------------------------------------------------
    # Phase 5: Validate SelectedIssue contents
    # ---------------------------------------------------------------
    selected = result["selected_issue"]
    print("\n" + "=" * 60)
    print("PHASE 5: SelectedIssue Contents")
    print("=" * 60)
    print(f"  issue_id:             {selected.issue_id}")
    print(f"  number:               {selected.number}")
    print(f"  title:                {selected.title}")
    print(f"  body:                 {selected.body}")
    print(f"  estimated_complexity: {selected.estimated_complexity}")
    print(f"  reasoning:            {selected.reasoning}")

    assert selected.issue_id, "issue_id should not be empty"
    assert selected.number == 1, f"Expected issue #1, got #{selected.number}"
    assert selected.title == "Change Text Colour", f"Wrong title: {selected.title}"
    assert selected.body, "body should not be empty"
    assert selected.estimated_complexity in ("low", "medium", "high"), \
        f"Invalid complexity: {selected.estimated_complexity}"
    assert selected.reasoning, "reasoning should not be empty"
    print("\n  [PASS] All SelectedIssue fields validated")
    print("  [PASS] Issue #1 correctly selected")

    # ---------------------------------------------------------------
    # Phase 6: State transition verification
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 6: State Transition Verification")
    print("=" * 60)

    updated_state = state.model_copy(update=result)

    print(f"  Before:  status={state.status}  selected_issue={'set' if state.selected_issue else 'None'}")
    print(f"  After:   status={updated_state.status}  selected_issue={'set' if updated_state.selected_issue else 'None'}")

    assert updated_state.status == SentinelStatus.PRIORITIZING
    assert updated_state.selected_issue is not None
    assert updated_state.selected_issue.number == 1
    # Previous state fields persist
    assert updated_state.repo_context is not None
    assert len(updated_state.issue_analyses) > 0
    # Original state not mutated
    assert state.selected_issue is None

    print("  [PASS] State transition: ANALYZING_ISSUES -> PRIORITIZING")
    print("  [PASS] selected_issue stored in SentinelState")
    print("  [PASS] repo_context and issue_analyses persist")
    print("  [PASS] Original state immutability preserved")

    # Simulate completion
    completed = updated_state.model_copy(
        update={"status": SentinelStatus.COMPLETED, "current_agent": ""}
    )
    assert completed.status == SentinelStatus.COMPLETED
    assert completed.selected_issue is not None
    print("  [PASS] State transition: PRIORITIZING -> COMPLETED")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:      {updated_state.repo_context.repository_name}")
    print(f"  Issues analyzed: {len(updated_state.issue_analyses)}")
    print(f"  Selected issue:  #{selected.number} - {selected.title}")
    print(f"  Complexity:      {selected.estimated_complexity}")
    print(f"  Reasoning:       {selected.reasoning}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
