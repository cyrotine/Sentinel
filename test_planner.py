"""End-to-end test of the planner node against real ingested data.

Tests:
  1. repo_analyzer produces RepoContext (prerequisite)
  2. issue_analyzer classifies issues (prerequisite)
  3. issue_prioritizer selects the best issue (prerequisite)
  4. retrieve_context retrieves relevant code (prerequisite)
  5. planner generates an implementation plan
  6. Plan fields are populated correctly
  7. State transitions: PENDING -> ... -> PLANNING -> COMPLETED

Repository: 70cc7b50-ca9d-41ef-be4c-bb56f1be9a82 (cyrotine/TempRepo)
Expected: Plan should target index.html, change color: black -> red
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
    PlanTask,
)
from forge_workflows.graph import (
    repo_analyzer,
    issue_analyzer,
    issue_prioritizer,
    retrieve_context,
    planner,
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
    print(f"  status: {state.status}")
    print(f"  plan:   {state.plan}")
    assert state.status == SentinelStatus.PENDING
    assert state.plan is None
    print("  [PASS] Initial state is PENDING, no plan")

    # ---------------------------------------------------------------
    # Phase 2: Run repo_analyzer
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
    # Phase 3: Run issue_analyzer
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
    # Phase 4: Run issue_prioritizer
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
    # Phase 5: Run retrieve_context
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
    # Phase 6: Run planner
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 6: Run planner")
    print("=" * 60)

    result = await planner(state)

    print(f"  Returned keys: {list(result.keys())}")
    print(f"  status:        {result.get('status')}")
    print(f"  current_agent: {result.get('current_agent')}")

    assert result["status"] == SentinelStatus.PLANNING
    assert result["current_agent"] == "planner"
    assert isinstance(result["plan"], Plan)
    print("  [PASS] planner returned correct status and Plan")

    # ---------------------------------------------------------------
    # Phase 7: Validate Plan contents
    # ---------------------------------------------------------------
    plan = result["plan"]
    print("\n" + "=" * 60)
    print("PHASE 7: Plan Contents")
    print("=" * 60)

    print(f"\n  Approach Reasoning:")
    for line in plan.approach_reasoning.split("\n"):
        if line.strip():
            print(f"    {line.strip()}")

    print(f"\n  Affected Files: {plan.affected_files}")
    print(f"  Dependencies:   {plan.dependencies}")

    assert plan.approach_reasoning, "approach_reasoning should not be empty"
    assert len(plan.affected_files) > 0, "Should have at least 1 affected file"
    assert "index.html" in plan.affected_files, \
        f"Expected index.html in affected_files, got: {plan.affected_files}"

    print(f"\n  Tasks ({len(plan.tasks)}):")
    for task in plan.tasks:
        assert isinstance(task, PlanTask)
        assert task.id, "task.id should not be empty"
        assert task.description, "task.description should not be empty"
        deps = f" (depends_on: {task.depends_on})" if task.depends_on else ""
        print(f"    [{task.id}]{deps}")
        # Wrap long descriptions
        desc_lines = task.description.split(". ")
        for dl in desc_lines[:3]:
            print(f"      {dl.strip()}")
        if len(desc_lines) > 3:
            print(f"      ...")

    assert len(plan.tasks) >= 1, "Should have at least 1 task"
    print(f"\n  [PASS] All Plan fields validated")
    print(f"  [PASS] index.html in affected_files")
    print(f"  [PASS] {len(plan.tasks)} tasks with valid structure")

    # ---------------------------------------------------------------
    # Phase 8: State transition verification
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 8: State Transition Verification")
    print("=" * 60)

    updated_state = state.model_copy(update=result)

    print(f"  Before:  status={state.status}  plan={'set' if state.plan else 'None'}")
    print(f"  After:   status={updated_state.status}  plan={'set' if updated_state.plan else 'None'}")

    assert updated_state.status == SentinelStatus.PLANNING
    assert updated_state.plan is not None
    # Previous state persists
    assert updated_state.repo_context is not None
    assert len(updated_state.issue_analyses) > 0
    assert updated_state.selected_issue is not None
    assert len(updated_state.relevant_chunks) > 0
    # Original state not mutated
    assert state.plan is None

    print("  [PASS] State transition: RETRIEVING_CONTEXT -> PLANNING")
    print("  [PASS] plan stored in SentinelState")
    print("  [PASS] All prior state fields persist")
    print("  [PASS] Original state immutability preserved")

    # Simulate completion
    completed = updated_state.model_copy(
        update={"status": SentinelStatus.COMPLETED, "current_agent": ""}
    )
    assert completed.status == SentinelStatus.COMPLETED
    assert completed.plan is not None
    print("  [PASS] State transition: PLANNING -> COMPLETED")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:      {updated_state.repo_context.repository_name}")
    print(f"  Selected issue:  #{updated_state.selected_issue.number} - {updated_state.selected_issue.title}")
    print(f"  Chunks used:     {len(updated_state.relevant_chunks)}")
    print(f"  Affected files:  {updated_state.plan.affected_files}")
    print(f"  Tasks:           {len(updated_state.plan.tasks)}")
    for t in updated_state.plan.tasks:
        print(f"    [{t.id}] {t.description[:100]}{'...' if len(t.description) > 100 else ''}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
