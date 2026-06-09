"""Direct test of the developer agent with pre-built state.

Avoids calling prior agents to save Gemini API quota.
Tests only the developer LLM path.
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
)
from forge_workflows.graph import developer


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


async def main() -> None:
    state = SentinelState(
        repository_id="70cc7b50-ca9d-41ef-be4c-bb56f1be9a82",
        status=SentinelStatus.PLANNING,
        current_agent="planner",
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
                start_line=1,
                end_line=27,
                language="html",
                score=0.83,
            ),
        ],
        plan=Plan(
            tasks=[
                PlanTask(
                    id="task_1",
                    description=(
                        "Locate the <style> block within index.html. "
                        "Find the h1 CSS rule. Change the color property "
                        "from black to red."
                    ),
                    depends_on=[],
                ),
            ],
            affected_files=["index.html"],
            dependencies=[],
            approach_reasoning=(
                "The h1 CSS rule explicitly sets color: black. "
                "Change it to color: red to implement the requested feature."
            ),
        ),
    )

    print("\n" + "=" * 60)
    print("DEVELOPER AGENT DIRECT TEST")
    print("=" * 60)

    result = await developer(state)

    print(f"\n  Returned keys:    {list(result.keys())}")
    print(f"  status:           {result.get('status')}")
    print(f"  current_agent:    {result.get('current_agent')}")

    assert result["status"] == SentinelStatus.DEVELOPING
    assert result["current_agent"] == "developer"
    assert isinstance(result["code_changes"], list)

    code_changes = result["code_changes"]
    is_fallback = any("Fallback" in c.description for c in code_changes)
    print(f"\n  LLM Path: {'FALLBACK (rate limited)' if is_fallback else 'FULL LLM'}")
    print(f"  Code changes: {len(code_changes)}")

    for i, change in enumerate(code_changes, 1):
        assert isinstance(change, CodeChange)
        print(f"\n  --- Change {i} ---")
        print(f"  file_path:   {change.file_path}")
        print(f"  description: {change.description}")
        print(f"  patch:")
        for line in change.patch.split("\n"):
            print(f"    {line}")

    assert len(code_changes) >= 1, "Expected at least 1 code change"

    # Verify index.html is targeted
    file_paths = [c.file_path for c in code_changes]
    assert "index.html" in file_paths, f"Expected index.html in changes, got: {file_paths}"

    # Verify the patch mentions color change
    index_change = next(c for c in code_changes if c.file_path == "index.html")
    patch_lower = index_change.patch.lower()
    assert "black" in patch_lower or "red" in patch_lower, \
        "Patch should reference black or red color"

    print(f"\n  [PASS] Developer generated {len(code_changes)} change(s)")
    print(f"  [PASS] index.html targeted")
    print(f"  [PASS] Patch references color change")

    # State transition test
    updated_state = state.model_copy(update=result)
    assert updated_state.status == SentinelStatus.DEVELOPING
    assert len(updated_state.code_changes) >= 1
    assert updated_state.plan is not None  # Prior state preserved
    assert state.code_changes == []  # Original immutability
    print(f"  [PASS] State transition: PLANNING -> DEVELOPING")
    print(f"  [PASS] code_changes stored in SentinelState")
    print(f"  [PASS] Original state immutability preserved")


if __name__ == "__main__":
    asyncio.run(main())
