"""Direct test of the PR Generator agent with pre-built state.

Tests:
  1. Positive case: valid TempRepo patch with approval -> Safe to merge.
  2. Negative case: bad patch rejected -> Do not merge.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from forge_workflows.state import (
    SentinelState,
    SentinelStatus,
    SelectedIssue,
    RepoContext,
    Plan,
    CodeChange,
    ValidationResult,
    TestResult,
    Review,
    PullRequestDraft,
)
from forge_workflows.graph import pr_generator


def build_base_state(**overrides) -> SentinelState:
    """Build a base state with all prior pipeline outputs."""
    defaults = dict(
        repository_id="70cc7b50-ca9d-41ef-be4c-bb56f1be9a82",
        status=SentinelStatus.REVIEWING,
        current_agent="reviewer",
        iteration=0,
        max_iterations=3,
        repo_context=RepoContext(
            repository_name="cyrotine/TempRepo",
            description="",
            languages=["html", "markdown"],
            framework_hints=[],
            total_files=2,
            key_files=["index.html", "README.md"],
            detected_modules=[],
            architecture_summary="Simple static HTML page."
        ),
        selected_issue=SelectedIssue(
            issue_id="458d6960-b51f-4b62-9c5a-1c8d0766878a",
            number=42,
            title="Fix Change Text Colour",
            body="Add red colour to the Hello World text instead of black color",
            estimated_complexity="low",
            reasoning="Only open issue."
        ),
        plan=Plan(
            tasks=[],
            affected_files=["index.html"],
            dependencies=[],
            approach_reasoning="Modify the h1 CSS rule color: black to color: red.",
        ),
        code_changes=[
            CodeChange(
                file_path="index.html",
                description="Changed h1 color from black to red.",
                patch="--- a/index.html\n+++ b/index.html\n@@ -19,4 +19,4 @@\n-color: black;\n+color: red;\n"
            )
        ],
        validation_result=ValidationResult(
            passed=True,
            issues=[],
            suggestions=["Proceed to testing and review."]
        ),
        test_results=[
            TestResult(
                name="Verify H1 Text Color is Red",
                passed=True,
                output="Risk: Low. The h1 color property was successfully changed."
            )
        ],
        review=Review(
            approved=True,
            comments=["Confidence: High. The patch directly addresses the issue."],
            security_issues=[],
            suggestions=["Merge immediately."]
        )
    )
    defaults.update(overrides)
    return SentinelState(**defaults)


async def main() -> None:
    # ---------------------------------------------------------------
    # TEST 1: Positive case
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 1: Positive PR Generation")
    print("=" * 60)

    state = build_base_state()
    result = await pr_generator(state)

    updated_state = state.model_copy(update=result)
    draft = updated_state.pull_request_draft
    assert isinstance(draft, PullRequestDraft)

    print(f"\n  Title:       {draft.title}")
    print(f"  Branch:      {draft.branch}")
    print(f"  Base Branch: {draft.base_branch}")
    print(f"\n  Body:\n{draft.body}")

    assert "Confidence: High" in draft.body
    assert "Safe to merge" in draft.body
    assert "No security concerns identified" in draft.body
    assert draft.branch.startswith("fix/issue-42")
    assert draft.base_branch == "main"
    print("\n  [PASS] Positive PR draft generated correctly")

    # ---------------------------------------------------------------
    # TEST 2: Negative case
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 2: Negative PR Generation")
    print("=" * 60)

    state_bad = build_base_state(
        review=Review(
            approved=False,
            comments=["Confidence: Low. Unrelated dependency added."],
            security_issues=["Potential supply chain attack via express."],
            suggestions=["Remove the dependency."]
        )
    )
    result_bad = await pr_generator(state_bad)

    updated_bad = state_bad.model_copy(update=result_bad)
    draft_bad = updated_bad.pull_request_draft
    
    print(f"\n  Title:       {draft_bad.title}")
    print(f"  Branch:      {draft_bad.branch}")
    print(f"\n  Body:\n{draft_bad.body}")

    assert "Confidence: Low" in draft_bad.body
    assert "Do not merge" in draft_bad.body
    assert "Potential supply chain attack via express." in draft_bad.body
    print("\n  [PASS] Negative PR draft generated correctly")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(main())
