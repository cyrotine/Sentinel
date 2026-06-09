"""Quick test of the planner agent directly with pre-built state.

Avoids calling prior agents to save Gemini API quota.
Tests only the planner LLM path.
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
)
from forge_workflows.graph import planner


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
        status=SentinelStatus.RETRIEVING_CONTEXT,
        current_agent="retrieve_context",
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
    )

    print("\n" + "=" * 60)
    print("PLANNER AGENT DIRECT TEST")
    print("=" * 60)

    result = await planner(state)
    plan = result["plan"]

    assert isinstance(plan, Plan)

    is_fallback = "Fallback plan" in plan.approach_reasoning
    print(f"\n  LLM Path: {'FALLBACK (rate limited)' if is_fallback else 'FULL LLM'}")

    print(f"\n  Approach Reasoning:")
    for line in plan.approach_reasoning.split("\n"):
        if line.strip():
            print(f"    {line.strip()}")

    print(f"\n  Affected Files: {plan.affected_files}")
    print(f"  Dependencies:   {plan.dependencies}")

    print(f"\n  Tasks ({len(plan.tasks)}):")
    for t in plan.tasks:
        assert isinstance(t, PlanTask)
        deps = f" (depends_on: {t.depends_on})" if t.depends_on else ""
        print(f"\n    [{t.id}]{deps}")
        print(f"    {t.description}")

    assert len(plan.tasks) >= 1
    assert len(plan.affected_files) >= 1
    assert "index.html" in plan.affected_files

    print(f"\n  [PASS] Plan generated successfully")
    print(f"  [PASS] index.html in affected_files")
    print(f"  [PASS] {len(plan.tasks)} tasks with valid structure")


if __name__ == "__main__":
    asyncio.run(main())
