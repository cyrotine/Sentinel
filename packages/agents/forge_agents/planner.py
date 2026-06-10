"""Planner agent for Sentinel Brain.

Produces a structured :class:`Plan` by reasoning about the selected issue,
retrieved code context, and repository structure. The plan is an executable
engineering strategy — it tells the Developer agent exactly what to do.

Design:
    - The agent is a **pure LLM class** — it does not access databases,
      files, or external services directly.
    - All context (issue, code chunks, repo structure) is passed in via
      the ``plan`` method.
    - The LLM acts as a senior software engineer producing a step-by-step
      implementation plan.
    - Output is parsed into the existing :class:`Plan` / :class:`PlanTask`
      Pydantic models.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from forge_workflows.state import FullFileContext, Plan, PlanTask, RepoContext, RetrievedChunk, SelectedIssue

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Produces an implementation plan using an LLM.

    The agent synthesizes the selected issue, relevant code chunks,
    and repository context into a structured Plan with ordered tasks.

    Args:
        llm: A LangChain chat model instance (e.g. ``ChatGoogleGenerativeAI``).
    """

    name: str = "planner"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def plan(
        self,
        *,
        selected_issue: SelectedIssue,
        repo_context: RepoContext,
        retrieved_chunks: list[RetrievedChunk],
        full_file_contexts: list[FullFileContext],
    ) -> Plan:
        """Produce an implementation plan for the selected issue.

        Args:
            selected_issue: The issue chosen for implementation.
            repo_context: Repository understanding from the repo_analyzer.
            retrieved_chunks: Relevant code chunks from Qdrant.
            full_file_contexts: Complete file contents from the workspace.

        Returns:
            A :class:`Plan` with tasks, affected files, and reasoning.
        """
        logger.info(
            "Planning implementation for issue #%d: %s",
            selected_issue.number,
            selected_issue.title,
        )

        prompt = self._build_prompt(selected_issue, repo_context, retrieved_chunks, full_file_contexts)

        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_llm_response(content)
            plan = self._build_plan(parsed)
            logger.info(
                "Plan generated: %d tasks, %d affected files",
                len(plan.tasks),
                len(plan.affected_files),
            )
            return plan
        except Exception:
            logger.exception("LLM planning failed — returning minimal safe plan")
            return self._fallback_plan(selected_issue, retrieved_chunks)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        issue: SelectedIssue,
        repo_context: RepoContext,
        chunks: list[RetrievedChunk],
        full_file_contexts: list[FullFileContext],
    ) -> str:
        """Construct the planning prompt for the LLM."""

        # Repository context block
        repo_block = (
            f"Repository: {repo_context.repository_name}\n"
            f"Description: {repo_context.description or 'No description provided.'}\n"
            f"Languages: {', '.join(repo_context.languages) or 'Unknown'}\n"
            f"Frameworks: {', '.join(repo_context.framework_hints) or 'None detected'}\n"
            f"Key Files: {', '.join(repo_context.key_files) or 'Unknown'}\n"
            f"Modules: {', '.join(repo_context.detected_modules) or 'None detected'}\n"
            f"Architecture: {repo_context.architecture_summary or 'Not available'}"
        )

        # Issue block
        issue_block = (
            f"Issue #{issue.number}: {issue.title}\n"
            f"Body: {issue.body or '(no description)'}\n"
            f"Estimated Complexity: {issue.estimated_complexity}"
        )

        # Full file contents (ground truth for line-accurate planning)
        full_file_entries = []
        for fc in full_file_contexts:
            lang = fc.language or ""
            numbered = "\n".join(
                f"{i + 1:4d} | {line}"
                for i, line in enumerate(fc.content.splitlines())
            )
            full_file_entries.append(
                f"  ### {fc.file_path} ({fc.line_count} lines, {lang})\n"
                f"  ```{lang}\n{numbered}\n  ```"
            )
        full_files_block = (
            "\n\n".join(full_file_entries)
            if full_file_entries
            else "  (No full file context — workspace not cloned)"
        )

        # Supplementary Qdrant chunks for files not covered by full file loading
        covered = {fc.file_path for fc in full_file_contexts}
        supplementary = [c for c in chunks if c.file_path not in covered]
        if supplementary:
            chunk_entries = []
            for i, chunk in enumerate(supplementary, 1):
                entry = (
                    f"  Chunk {i}: {chunk.file_path} "
                    f"(lines {chunk.start_line}-{chunk.end_line}, "
                    f"{chunk.language}, score={chunk.score:.2f})\n"
                    f"  ```\n{chunk.content}\n  ```"
                )
                chunk_entries.append(entry)
            chunks_block = "\n\n".join(chunk_entries)
        else:
            chunks_block = "  (All relevant files covered by full file context above)"

        return f"""You are a senior software engineer creating an implementation plan for an autonomous AI coding agent called Sentinel.

Sentinel can:
- Read and understand repository code
- Modify existing files
- Create new files
- Generate code changes as patches

You must produce a detailed, step-by-step implementation plan.

{repo_block}

Selected Issue:
{issue_block}

Full File Contents (exact line numbers — use these for precise file references):
{full_files_block}

Additional Context (Qdrant chunks for files not listed above):
{chunks_block}

Plan Requirements:
1. Analyze the root cause of the issue.
2. Identify the MINIMUM set of changes needed.
3. Prefer the smallest safe modification.
4. Preserve existing functionality.
5. Minimize implementation risk.
6. Explain WHY each step is needed.

Respond with a JSON object containing exactly these fields:

1. "summary": A 1-2 sentence summary of what this plan accomplishes.

2. "approach_reasoning": A paragraph explaining WHY this approach was chosen,
   what the root cause is, and what alternatives were considered.

3. "estimated_complexity": One of "low", "medium", "high".

4. "affected_files": A list of file paths that will be modified or created.

5. "tests_needed": A list of test descriptions (what should be verified).

6. "dependencies": A list of external packages or internal modules this plan
   depends on (empty list if none).

7. "tasks": An ordered list of implementation tasks. Each task is an object with:
   - "id": A unique string identifier (e.g. "task_1", "task_2").
   - "description": A detailed description of what to do in this step,
     including the specific code change. Explain WHY this change is needed.
   - "depends_on": A list of task IDs that must complete before this one
     (empty list for the first task).

Respond with valid JSON only. No markdown, no explanation, just the JSON object."""

    @staticmethod
    def _parse_llm_response(content: str) -> dict[str, Any]:
        """Extract a JSON object from the LLM response."""
        text = content.strip()

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            logger.warning("LLM returned unexpected JSON type: %s", type(parsed))
            return {}
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM JSON response: %s", exc)
            logger.debug("Raw LLM output: %s", content[:500])
            return {}

    @staticmethod
    def _build_plan(parsed: dict[str, Any]) -> Plan:
        """Build a Plan from the LLM response."""

        # Build PlanTask list
        raw_tasks = parsed.get("tasks", [])
        tasks: list[PlanTask] = []
        for t in raw_tasks:
            try:
                task = PlanTask(
                    id=t.get("id", f"task_{len(tasks) + 1}"),
                    description=t.get("description", ""),
                    depends_on=t.get("depends_on", []),
                )
                tasks.append(task)
            except Exception:
                logger.warning("Failed to build PlanTask from: %s", t)

        # Build reasoning — combine summary and approach_reasoning
        summary = parsed.get("summary", "")
        approach = parsed.get("approach_reasoning", "")
        reasoning_parts = []
        if summary:
            reasoning_parts.append(f"Summary: {summary}")
        if approach:
            reasoning_parts.append(approach)

        # Include extra metadata in the reasoning field
        complexity = parsed.get("estimated_complexity", "medium")
        tests_needed = parsed.get("tests_needed", [])
        if tests_needed:
            tests_str = "; ".join(tests_needed)
            reasoning_parts.append(f"Tests needed: {tests_str}")
        if complexity:
            reasoning_parts.append(f"Estimated complexity: {complexity}")

        return Plan(
            tasks=tasks,
            affected_files=parsed.get("affected_files", []),
            dependencies=parsed.get("dependencies", []),
            approach_reasoning="\n\n".join(reasoning_parts),
        )

    @staticmethod
    def _fallback_plan(
        issue: SelectedIssue,
        chunks: list[RetrievedChunk],
    ) -> Plan:
        """Create a minimal safe plan when the LLM fails."""
        affected = list({c.file_path for c in chunks}) if chunks else []

        return Plan(
            tasks=[
                PlanTask(
                    id="task_1",
                    description=(
                        f"Investigate issue #{issue.number}: {issue.title}. "
                        f"Review the affected files and identify the minimal change needed. "
                        f"Issue body: {issue.body}"
                    ),
                    depends_on=[],
                ),
                PlanTask(
                    id="task_2",
                    description="Apply the minimal code change to resolve the issue.",
                    depends_on=["task_1"],
                ),
                PlanTask(
                    id="task_3",
                    description="Verify the change does not break existing functionality.",
                    depends_on=["task_2"],
                ),
            ],
            affected_files=affected,
            dependencies=[],
            approach_reasoning=(
                f"Fallback plan: LLM planning failed. "
                f"Manual investigation required for issue #{issue.number}."
            ),
        )
