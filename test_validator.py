"""End-to-end test of the validator node against real ingested data.

Tests the full 8-stage pipeline:
  1-6. Prior agents (repo_analyzer through developer)
  7.   validator evaluates the generated CodeChanges
  8.   State transitions verified

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
    ValidationResult,
)
from forge_workflows.graph import (
    repo_analyzer,
    issue_analyzer,
    issue_prioritizer,
    retrieve_context,
    planner,
    developer,
    validator,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

REPO_ID = "70cc7b50-ca9d-41ef-be4c-bb56f1be9a82"


async def main() -> None:
    state = SentinelState(repository_id=REPO_ID)

    # Phase 1: Initial state
    print("\n" + "=" * 60)
    print("PHASE 1: Initial State")
    print("=" * 60)
    assert state.status == SentinelStatus.PENDING
    assert state.validation_result is None
    print("  [PASS] Initial state correct")

    # Phase 2: repo_analyzer
    print("\n" + "=" * 60)
    print("PHASE 2: Run repo_analyzer")
    print("=" * 60)
    result = await repo_analyzer(state)
    state = state.model_copy(update=result)
    print(f"  repo: {state.repo_context.repository_name}")
    print("  [PASS] repo_analyzer completed")

    # Phase 3: issue_analyzer
    print("\n" + "=" * 60)
    print("PHASE 3: Run issue_analyzer")
    print("=" * 60)
    result = await issue_analyzer(state)
    state = state.model_copy(update=result)
    print(f"  issues: {len(state.issue_analyses)}")
    print("  [PASS] issue_analyzer completed")

    # Phase 4: issue_prioritizer
    print("\n" + "=" * 60)
    print("PHASE 4: Run issue_prioritizer")
    print("=" * 60)
    result = await issue_prioritizer(state)
    state = state.model_copy(update=result)
    print(f"  selected: #{state.selected_issue.number} - {state.selected_issue.title}")
    print("  [PASS] issue_prioritizer completed")

    # Phase 5: retrieve_context
    print("\n" + "=" * 60)
    print("PHASE 5: Run retrieve_context")
    print("=" * 60)
    result = await retrieve_context(state)
    state = state.model_copy(update=result)
    print(f"  chunks: {len(state.relevant_chunks)}")
    print("  [PASS] retrieve_context completed")

    # Phase 6: planner
    print("\n" + "=" * 60)
    print("PHASE 6: Run planner")
    print("=" * 60)
    result = await planner(state)
    state = state.model_copy(update=result)
    print(f"  tasks: {len(state.plan.tasks)}")
    print("  [PASS] planner completed")

    # Phase 7: developer
    print("\n" + "=" * 60)
    print("PHASE 7: Run developer")
    print("=" * 60)
    result = await developer(state)
    state = state.model_copy(update=result)
    print(f"  code_changes: {len(state.code_changes)}")
    for c in state.code_changes:
        print(f"    [{c.file_path}] {c.description}")
    print("  [PASS] developer completed")

    # Phase 8: validator
    print("\n" + "=" * 60)
    print("PHASE 8: Run validator")
    print("=" * 60)
    result = await validator(state)

    assert result["status"] == SentinelStatus.VALIDATING
    assert result["current_agent"] == "validator"
    assert isinstance(result["validation_result"], ValidationResult)

    vr = result["validation_result"]
    print(f"\n  passed:      {vr.passed}")
    print(f"  issues:      {vr.issues}")
    print(f"  suggestions: {vr.suggestions}")

    assert vr.passed is True, f"Expected PASS, got FAIL: {vr.issues}"
    print("\n  [PASS] Validator approved the patch")

    # Phase 9: State transitions
    print("\n" + "=" * 60)
    print("PHASE 9: State Transition Verification")
    print("=" * 60)

    updated = state.model_copy(update=result)
    assert updated.status == SentinelStatus.VALIDATING
    assert updated.validation_result is not None
    assert updated.validation_result.passed is True
    assert updated.plan is not None
    assert len(updated.code_changes) >= 1
    assert updated.selected_issue is not None
    assert state.validation_result is None

    print("  [PASS] State transition: DEVELOPING -> VALIDATING")
    print("  [PASS] validation_result stored")
    print("  [PASS] All prior state fields persist")
    print("  [PASS] Original immutability preserved")

    completed = updated.model_copy(
        update={"status": SentinelStatus.COMPLETED, "current_agent": ""}
    )
    assert completed.status == SentinelStatus.COMPLETED
    print("  [PASS] State transition: VALIDATING -> COMPLETED")

    # Summary
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:         {updated.repo_context.repository_name}")
    print(f"  Issue:              #{updated.selected_issue.number} - {updated.selected_issue.title}")
    print(f"  Code changes:       {len(updated.code_changes)}")
    print(f"  Validation passed:  {updated.validation_result.passed}")
    print(f"  Issues found:       {len(updated.validation_result.issues)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
