"""Direct test of the test agent with pre-built state.

Tests:
  1. Positive case: Code changes align with the plan.
  2. Negative case: Bad patch with an unrelated file.
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
)
from forge_workflows.graph import test_agent


def build_base_state(**overrides) -> SentinelState:
    """Build a base state with all prior pipeline outputs."""
    defaults = dict(
        repository_id="70cc7b50-ca9d-41ef-be4c-bb56f1be9a82",
        status=SentinelStatus.VALIDATING,
        current_agent="validator",
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
            tests_needed=[
                "Verify text is displayed in red",
                "Verify text remains centered",
                "Verify font size unchanged"
            ],
        ),
        validation_result=ValidationResult(
            passed=True,
            issues=[],
            suggestions=["Proceed to testing and review."]
        )
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

BAD_CHANGE = CodeChange(
    file_path="package.json",
    description="Added new dependency.",
    patch=(
        "--- a/package.json\n"
        "+++ b/package.json\n"
        '@@ -5,3 +5,4 @@\n'
        '     "dependencies": {\n'
        '+      "express": "^4.18.2",\n'
        '     }\n'
    ),
)


async def main() -> None:
    # ---------------------------------------------------------------
    # TEST 1: Positive case
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 1: Positive Testing (valid patch)")
    print("=" * 60)

    state = build_base_state(code_changes=[GOOD_CHANGE])
    result = await test_agent(state)

    tests = result["test_results"]
    assert isinstance(tests, list)
    assert len(tests) > 0
    assert all(isinstance(t, TestResult) for t in tests)

    for i, t in enumerate(tests, 1):
        print(f"\nTest {i}:")
        print(f"  Name:   {t.name}")
        print(f"  Passed: {t.passed}")
        print(f"  Details:\n    {t.output}")
        if t.error:
            print(f"  Error:  {t.error}")

    print("\n  [PASS] Test results successfully generated")

    # ---------------------------------------------------------------
    # TEST 2: Negative case
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 2: Negative Testing (unrelated file)")
    print("=" * 60)

    state_bad = build_base_state(
        code_changes=[GOOD_CHANGE, BAD_CHANGE],
        validation_result=ValidationResult(
            passed=False,
            issues=["Modified unrelated file package.json"],
            suggestions=["Remove package.json modification"]
        )
    )
    result_bad = await test_agent(state_bad)

    tests_bad = result_bad["test_results"]
    assert isinstance(tests_bad, list)
    
    for i, t in enumerate(tests_bad, 1):
        print(f"\nTest {i}:")
        print(f"  Name:   {t.name}")
        print(f"  Passed: {t.passed}")
        print(f"  Details:\n    {t.output}")
        if t.error:
            print(f"  Error:  {t.error}")

    print("\n  [PASS] Negative test results generated")

    # ---------------------------------------------------------------
    # TEST 3: State transitions
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 3: State Transitions")
    print("=" * 60)

    updated = state.model_copy(update=result)
    assert updated.status == SentinelStatus.TESTING
    assert updated.current_agent == "test_agent"
    assert len(updated.test_results) > 0
    assert len(state.test_results) == 0  # immutability

    print("  [PASS] State transition: VALIDATING -> TESTING")
    print("  [PASS] test_results stored in SentinelState")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print()


if __name__ == "__main__":
    asyncio.run(main())
