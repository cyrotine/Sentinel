"""Direct test of the validator agent with pre-built state.

Tests:
  1. Positive case: valid TempRepo patch should PASS
  2. Negative case: bad patch touching unrelated files should FAIL
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
    RetrievedChunk,
    IssueAnalysis,
    Plan,
    PlanTask,
    CodeChange,
    ValidationResult,
)
from forge_workflows.graph import validator


HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World</title>
    <style>
        body {
            margin: 0;
            background: white;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            font-family: Arial, sans-serif;
        }

        h1 {
            font-size: 5rem;
            color: black;
        }
    </style>
</head>
<body>
    <h1>Hello World</h1>
</body>
</html>"""


def build_base_state(**overrides) -> SentinelState:
    """Build a base state with all prior pipeline outputs."""
    defaults = dict(
        repository_id="70cc7b50-ca9d-41ef-be4c-bb56f1be9a82",
        status=SentinelStatus.DEVELOPING,
        current_agent="developer",
        repo_context=RepoContext(
            repository_name="cyrotine/TempRepo",
            description="",
            languages=["html", "markdown"],
            framework_hints=[],
            total_files=2,
            key_files=["index.html", "README.md"],
            detected_modules=[],
            architecture_summary="Simple static HTML page with Hello World heading.",
        ),
        issue_analyses=[
            IssueAnalysis(
                issue_id="458d6960-b51f-4b62-9c5a-1c8d0766878a",
                number=1,
                title="Change Text Colour",
                body="Add red colour to the Hello World text instead of black color",
                issue_type="feature",
                severity="low",
                confidence=1.0,
                impact=0.2,
                affected_areas=["index.html"],
                reasoning="Simple CSS color change.",
            ),
        ],
        selected_issue=SelectedIssue(
            issue_id="458d6960-b51f-4b62-9c5a-1c8d0766878a",
            number=1,
            title="Change Text Colour",
            body="Add red colour to the Hello World text instead of black color",
            estimated_complexity="low",
            reasoning="Only open issue.",
        ),
        relevant_chunks=[
            RetrievedChunk(
                file_path="index.html",
                content=HTML_CONTENT,
                start_line=1, end_line=27,
                language="html", score=0.83,
            ),
        ],
        plan=Plan(
            tasks=[
                PlanTask(
                    id="task_1",
                    description="Change h1 color from black to red in index.html.",
                    depends_on=[],
                ),
            ],
            affected_files=["index.html"],
            dependencies=[],
            approach_reasoning="Modify the h1 CSS rule color: black to color: red.",
        ),
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

BAD_CHANGE_EXTRA_FILE = CodeChange(
    file_path="package.json",
    description="Added new dependency for color management.",
    patch=(
        "--- a/package.json\n"
        "+++ b/package.json\n"
        '@@ -5,3 +5,4 @@\n'
        '     "dependencies": {\n'
        '+      "color-lib": "^2.0.0",\n'
        '     }\n'
    ),
)


async def main() -> None:
    # ---------------------------------------------------------------
    # TEST 1: Positive case — valid patch should PASS
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 1: Positive Validation (valid patch)")
    print("=" * 60)

    state = build_base_state(code_changes=[GOOD_CHANGE])
    result = await validator(state)

    vr = result["validation_result"]
    assert isinstance(vr, ValidationResult)

    is_fallback = result.get("_fallback", False)
    print(f"\n  LLM Path:     {'FALLBACK' if is_fallback else 'FULL LLM'}")
    print(f"  passed:       {vr.passed}")
    print(f"  issues:       {vr.issues}")
    print(f"  suggestions:  {vr.suggestions}")

    assert vr.passed is True, f"Expected PASS, got FAIL with issues: {vr.issues}"
    print("\n  [PASS] Valid patch correctly accepted")

    # ---------------------------------------------------------------
    # TEST 2: Negative case — patch with unrelated file should FAIL
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 2: Negative Validation (unrelated file)")
    print("=" * 60)

    state_bad = build_base_state(code_changes=[GOOD_CHANGE, BAD_CHANGE_EXTRA_FILE])
    result_bad = await validator(state_bad)

    vr_bad = result_bad["validation_result"]
    assert isinstance(vr_bad, ValidationResult)

    print(f"\n  passed:       {vr_bad.passed}")
    print(f"  issues:       {vr_bad.issues}")
    print(f"  suggestions:  {vr_bad.suggestions}")

    assert vr_bad.passed is False, f"Expected FAIL, got PASS"
    assert len(vr_bad.issues) > 0, "Expected at least 1 issue reported"
    print("\n  [PASS] Bad patch correctly rejected")

    # ---------------------------------------------------------------
    # TEST 3: State transitions
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TEST 3: State Transitions")
    print("=" * 60)

    updated = state.model_copy(update=result)
    assert updated.status == SentinelStatus.VALIDATING
    assert updated.validation_result is not None
    assert updated.validation_result.passed is True
    assert updated.plan is not None
    assert len(updated.code_changes) == 1
    assert state.validation_result is None  # immutability

    print("  [PASS] State transition: DEVELOPING -> VALIDATING")
    print("  [PASS] validation_result stored in SentinelState")
    print("  [PASS] Original state immutability preserved")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print("  Test 1: Valid patch     -> PASS  (accepted)")
    print("  Test 2: Unrelated file  -> FAIL  (rejected)")
    print("  Test 3: State transitions verified")
    print()


if __name__ == "__main__":
    asyncio.run(main())
