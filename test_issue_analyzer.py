"""End-to-end test of the issue_analyzer node against real ingested data.

Tests:
  1. repo_analyzer produces RepoContext (prerequisite)
  2. issue_analyzer loads issues from Postgres and classifies them
  3. IssueAnalysis fields are populated correctly
  4. SentinelState transitions: PENDING -> ANALYZING_REPO -> ANALYZING_ISSUES
  5. issue_analyses stored in SentinelState

Repository: 70cc7b50-ca9d-41ef-be4c-bb56f1be9a82 (cyrotine/TempRepo)
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

from forge_workflows.state import SentinelState, SentinelStatus, IssueAnalysis, RepoContext
from forge_workflows.graph import repo_analyzer, issue_analyzer

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
    print(f"  repository_id:   {state.repository_id}")
    print(f"  status:          {state.status}")
    print(f"  repo_context:    {state.repo_context}")
    print(f"  issue_analyses:  {state.issue_analyses}")

    assert state.status == SentinelStatus.PENDING
    assert state.repo_context is None
    assert state.issue_analyses == []
    print("  [PASS] Initial state is PENDING, no context, no analyses")

    # ---------------------------------------------------------------
    # Phase 2: Run repo_analyzer (prerequisite)
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 2: Run repo_analyzer (prerequisite)")
    print("=" * 60)

    repo_result = await repo_analyzer(state)
    state = state.model_copy(update=repo_result)

    assert state.status == SentinelStatus.ANALYZING_REPO
    assert state.repo_context is not None
    assert state.repo_context.repository_name == "cyrotine/TempRepo"
    print(f"  repo_context.repository_name: {state.repo_context.repository_name}")
    print(f"  repo_context.languages:       {state.repo_context.languages}")
    print(f"  repo_context.key_files:        {state.repo_context.key_files}")
    print(f"  status: {state.status}")
    print("  [PASS] repo_analyzer completed, RepoContext available")

    # ---------------------------------------------------------------
    # Phase 3: Run issue_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 3: Run issue_analyzer")
    print("=" * 60)

    issue_result = await issue_analyzer(state)

    print(f"  Returned keys:   {list(issue_result.keys())}")
    print(f"  status:          {issue_result.get('status')}")
    print(f"  current_agent:   {issue_result.get('current_agent')}")
    print(f"  issue_analyses:  {len(issue_result.get('issue_analyses', []))} items")

    assert issue_result["status"] == SentinelStatus.ANALYZING_ISSUES
    assert issue_result["current_agent"] == "issue_analyzer"
    assert isinstance(issue_result["issue_analyses"], list)
    assert len(issue_result["issue_analyses"]) > 0, "Expected at least 1 issue analysis"
    print("  [PASS] issue_analyzer returned correct status and analyses")

    # ---------------------------------------------------------------
    # Phase 4: Validate IssueAnalysis contents
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 4: IssueAnalysis Contents")
    print("=" * 60)

    analyses = issue_result["issue_analyses"]
    valid_types = {"bug", "feature", "refactor", "docs", "test", "chore"}
    valid_severities = {"critical", "high", "medium", "low"}

    for i, analysis in enumerate(analyses):
        assert isinstance(analysis, IssueAnalysis), f"Item {i} is not IssueAnalysis"
        print(f"\n  --- Issue #{analysis.number} ---")
        print(f"  issue_id:       {analysis.issue_id}")
        print(f"  title:          {analysis.title}")
        print(f"  body:           {analysis.body[:80]}{'...' if len(analysis.body) > 80 else ''}")
        print(f"  issue_type:     {analysis.issue_type}")
        print(f"  severity:       {analysis.severity}")
        print(f"  confidence:     {analysis.confidence}")
        print(f"  impact:         {analysis.impact}")
        print(f"  affected_areas: {analysis.affected_areas}")
        print(f"  reasoning:      {analysis.reasoning}")

        # Validate field constraints
        assert analysis.issue_type in valid_types, \
            f"Invalid issue_type: {analysis.issue_type}"
        assert analysis.severity in valid_severities, \
            f"Invalid severity: {analysis.severity}"
        assert 0.0 <= analysis.confidence <= 1.0, \
            f"confidence out of range: {analysis.confidence}"
        assert 0.0 <= analysis.impact <= 1.0, \
            f"impact out of range: {analysis.impact}"
        assert analysis.issue_id, "issue_id should not be empty"
        assert analysis.number > 0, "number should be positive"
        assert analysis.title, "title should not be empty"
        assert isinstance(analysis.affected_areas, list)
        assert analysis.reasoning, "reasoning should not be empty"

    print(f"\n  [PASS] All {len(analyses)} IssueAnalysis objects validated")

    # ---------------------------------------------------------------
    # Phase 5: State transition verification
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 5: State Transition Verification")
    print("=" * 60)

    # Merge issue_analyzer result into state
    updated_state = state.model_copy(update=issue_result)

    print(f"  Before:  status={state.status}  analyses={len(state.issue_analyses)}")
    print(f"  After:   status={updated_state.status}  analyses={len(updated_state.issue_analyses)}")

    assert updated_state.status == SentinelStatus.ANALYZING_ISSUES
    assert len(updated_state.issue_analyses) == len(analyses)
    assert updated_state.repo_context is not None  # persists from previous phase

    # Original state was not mutated
    assert state.issue_analyses == []
    assert state.status == SentinelStatus.ANALYZING_REPO

    print("  [PASS] State transition: ANALYZING_REPO -> ANALYZING_ISSUES")
    print("  [PASS] issue_analyses stored in SentinelState")
    print("  [PASS] repo_context persists through transition")
    print("  [PASS] Original state immutability preserved")

    # Simulate completion
    completed = updated_state.model_copy(
        update={"status": SentinelStatus.COMPLETED, "current_agent": ""}
    )
    assert completed.status == SentinelStatus.COMPLETED
    assert len(completed.issue_analyses) > 0
    assert completed.repo_context is not None
    print("  [PASS] State transition: ANALYZING_ISSUES -> COMPLETED")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:      {updated_state.repo_context.repository_name}")
    print(f"  Issues analyzed: {len(updated_state.issue_analyses)}")
    for a in updated_state.issue_analyses:
        print(f"    #{a.number} [{a.issue_type}/{a.severity}] "
              f"conf={a.confidence:.2f} impact={a.impact:.2f} "
              f"- {a.title}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
