"""End-to-end test of the PR Generator agent node against real ingested data.

Tests the full 11-stage pipeline:
  1-9. Prior agents (repo_analyzer through reviewer)
  10.  pr_generator synthesizes the final pull request draft
  11.  State transitions verified

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
    PullRequestDraft,
)
from forge_workflows.graph import (
    repo_analyzer,
    issue_analyzer,
    issue_prioritizer,
    retrieve_context,
    planner,
    developer,
    validator,
    test_agent,
    reviewer,
    pr_generator,
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
    print("  [PASS] Initial state correct")

    # Phase 2: repo_analyzer
    print("\n" + "=" * 60)
    print("PHASE 2: Run repo_analyzer")
    print("=" * 60)
    result = await repo_analyzer(state)
    state = state.model_copy(update=result)
    print(f"  repo: {state.repo_context.repository_name}")

    # Phase 3: issue_analyzer
    print("\n" + "=" * 60)
    print("PHASE 3: Run issue_analyzer")
    print("=" * 60)
    result = await issue_analyzer(state)
    state = state.model_copy(update=result)
    print(f"  issues: {len(state.issue_analyses)}")

    # Phase 4: issue_prioritizer
    print("\n" + "=" * 60)
    print("PHASE 4: Run issue_prioritizer")
    print("=" * 60)
    result = await issue_prioritizer(state)
    state = state.model_copy(update=result)
    print(f"  selected: #{state.selected_issue.number} - {state.selected_issue.title}")

    # Phase 5: retrieve_context
    print("\n" + "=" * 60)
    print("PHASE 5: Run retrieve_context")
    print("=" * 60)
    result = await retrieve_context(state)
    state = state.model_copy(update=result)
    print(f"  chunks: {len(state.relevant_chunks)}")

    # Phase 6: planner
    print("\n" + "=" * 60)
    print("PHASE 6: Run planner")
    print("=" * 60)
    result = await planner(state)
    state = state.model_copy(update=result)
    print(f"  tasks: {len(state.plan.tasks)}")
    
    # Phase 7: developer
    print("\n" + "=" * 60)
    print("PHASE 7: Run developer")
    print("=" * 60)
    result = await developer(state)
    state = state.model_copy(update=result)
    print(f"  code_changes: {len(state.code_changes)}")
    
    # Phase 8: validator
    print("\n" + "=" * 60)
    print("PHASE 8: Run validator")
    print("=" * 60)
    result = await validator(state)
    state = state.model_copy(update=result)
    print(f"  validation passed: {state.validation_result.passed}")

    # Phase 9: test_agent
    print("\n" + "=" * 60)
    print("PHASE 9: Run test_agent")
    print("=" * 60)
    result = await test_agent(state)
    state = state.model_copy(update=result)
    print(f"  test_results: {len(state.test_results)}")

    # Phase 10: reviewer
    print("\n" + "=" * 60)
    print("PHASE 10: Run reviewer")
    print("=" * 60)
    result = await reviewer(state)
    state = state.model_copy(update=result)
    print(f"  review approved: {state.review.approved}")

    # Phase 11: pr_generator
    print("\n" + "=" * 60)
    print("PHASE 11: Run pr_generator")
    print("=" * 60)
    result = await pr_generator(state)

    assert result["status"] == SentinelStatus.GENERATING_PR
    assert result["current_agent"] == "pr_generator"
    
    draft = result["pull_request_draft"]
    assert isinstance(draft, PullRequestDraft)

    print(f"\n  Title:       {draft.title}")
    print(f"  Branch:      {draft.branch}")
    print(f"  Base Branch: {draft.base_branch}")
    print(f"\n  Body:\n{draft.body}")

    print("\n  [PASS] PR Generator generated results")

    # Phase 12: State transitions
    print("\n" + "=" * 60)
    print("PHASE 12: State Transition Verification")
    print("=" * 60)

    updated = state.model_copy(update=result)
    assert updated.status == SentinelStatus.GENERATING_PR
    assert updated.pull_request_draft is not None
    assert state.pull_request_draft is None

    print("  [PASS] State transition: REVIEWING -> GENERATING_PR")
    print("  [PASS] pull_request_draft stored")

    # Summary
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:         {updated.repo_context.repository_name}")
    print(f"  Issue:              #{updated.selected_issue.number} - {updated.selected_issue.title}")
    print(f"  Final PR Title:     {draft.title}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
