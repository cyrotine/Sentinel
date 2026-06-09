"""Direct test of the reviewer agent with pre-built state.

Tests:
  1. Positive case: valid TempRepo patch should PASS and route to PR_GENERATOR.
  2. Negative case: bad patch with failed validation/tests should FAIL and route to DEVELOPER.
  3. Boundary case: bad patch with max_iterations reached should route to PR_GENERATOR anyway.
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
)
from forge_workflows.graph import reviewer, route_after_reviewer


def build_base_state(**overrides) -> SentinelState:
    """Build a base state with all prior pipeline outputs."""
    defaults = dict(
        repository_id="70cc7b50-ca9d-41ef-be4c-bb56f1be9a82",
        status=SentinelStatus.TESTING,
        current_agent="test_agent",
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
            architecture_summary="Simple static HTML page.",
        ),
        selected_issue=SelectedIssue(
            issue_id="458d6960-b51f-4b62-9c5a-1c8d0766878a",
            number=1,
            title="Change Text Colour",
            body="Add red colour to the Hello World text instead of black color",
            estimated_complexity="low",
            reasoning="Only open issue.",
        ),
        plan=Plan(
            tasks=[],
            affected_files=["index.html"],
            dependencies=[],
            approach_reasoning="Modify the h1 CSS rule color: black to color: red.",
        ),
        validation_result=ValidationResult(
            passed=True,
            issues=[],
            suggestions=["Proceed to testing and review."]
        ),
        test_results=[
            TestResult(
                name="Verify H1 Text Color is Red",
                passed=True,
                output="Risk: Low. The h1 color property was successfully changed from black to red."
            )
        ]
    )
    defaults.update(overrides)
    return SentinelState(**defaults)


GOOD_CHANGE = CodeChange(
    file_path="index.html",
    description="Changed h1 color from black to red.",
    patch=(
        "--- a/index.html\n"
        "+++ b/index.html\n"
        "@@ -19,4 +19,4 @@\n"
        "         h1 {\n"
        "             font-size: 5rem;\n"
        "-            color: black;\n"
        "+            color: red;\n"
        "         }\n"
    ),
)


async def main() -> None:
    # ---------------------------------------------------------------
    # TEST 1: Positive case (should route to PR_GENERATOR)
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 1: Positive Review (valid patch)")
    print("=" * 60)

    state = build_base_state(code_changes=[GOOD_CHANGE])
    result = await reviewer(state)

    updated_state = state.model_copy(update=result)
    rev = updated_state.review
    assert isinstance(rev, Review)

    print(f"\n  Approved:        {rev.approved}")
    print(f"  Comments:        {rev.comments}")
    print(f"  Security issues: {rev.security_issues}")
    print(f"  Suggestions:     {rev.suggestions}")

    assert rev.approved is True, "Expected APPROVAL"
    route = route_after_reviewer(updated_state)
    print(f"  Route after:     {route}")
    assert route == "pr_generator", "Should route to pr_generator"
    print("\n  [PASS] Positive review accepted and routed correctly")

    # ---------------------------------------------------------------
    # TEST 2: Negative case (should route to DEVELOPER)
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 2: Negative Review (failed validation)")
    print("=" * 60)

    state_bad = build_base_state(
        code_changes=[GOOD_CHANGE],
        validation_result=ValidationResult(
            passed=False,
            issues=["Missing file header", "Unused variable detected"],
            suggestions=["Fix issues before merge"]
        )
    )
    result_bad = await reviewer(state_bad)

    updated_bad = state_bad.model_copy(update=result_bad)
    rev_bad = updated_bad.review
    
    print(f"\n  Approved:        {rev_bad.approved}")
    print(f"  Comments:        {rev_bad.comments}")

    assert rev_bad.approved is False, "Expected REJECTION"
    route_bad = route_after_reviewer(updated_bad)
    print(f"  Route after:     {route_bad}")
    assert route_bad == "developer", "Should route to developer"
    print("\n  [PASS] Negative review rejected and routed correctly")

    # ---------------------------------------------------------------
    # TEST 3: Boundary case (max iterations reached)
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 3: Boundary Case (max iterations)")
    print("=" * 60)

    state_bound = state_bad.model_copy(update={"iteration": 3})
    route_bound = route_after_reviewer(state_bound)
    print(f"  Route after (iteration=3, max=3): {route_bound}")
    assert route_bound == "pr_generator", "Should force merge if max iterations reached"
    print("  [PASS] Max iterations boundary respected")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(main())
