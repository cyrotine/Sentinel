"""Developer agent for Sentinel Brain.

Translates an implementation :class:`Plan` into concrete :class:`CodeChange`
objects containing unified diffs for each affected file.

Design:
    - The agent is a **pure LLM class** — it does not access databases,
      files, or external services directly.
    - All context (plan, issue, code chunks, repo structure) is passed in
      via the ``develop`` method.
    - The LLM acts as a senior developer executing a plan by producing
      the minimum set of precise code modifications.
    - Output is parsed into the existing :class:`CodeChange` Pydantic model.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from forge_workflows.state import (
    CodeChange,
    Plan,
    RepoContext,
    RetrievedChunk,
    SelectedIssue,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class DeveloperAgent:
    """Generates code changes from an implementation plan using an LLM.

    The agent translates a Plan (from the PlannerAgent) into a list of
    CodeChange objects, each containing a unified diff and description.

    Args:
        llm: A LangChain chat model instance (e.g. ``ChatGoogleGenerativeAI``).
    """

    name: str = "developer"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def develop(
        self,
        *,
        plan: Plan,
        selected_issue: SelectedIssue,
        repo_context: RepoContext,
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[CodeChange]:
        """Generate code changes based on the implementation plan.

        Args:
            plan: The implementation plan from the PlannerAgent.
            selected_issue: The issue being resolved.
            repo_context: Repository understanding from the repo_analyzer.
            retrieved_chunks: Relevant code chunks from Qdrant.

        Returns:
            A list of :class:`CodeChange` objects with unified diffs.
        """
        logger.info(
            "Developing code changes for issue #%d: %s (%d tasks, %d affected files)",
            selected_issue.number,
            selected_issue.title,
            len(plan.tasks),
            len(plan.affected_files),
        )

        prompt = self._build_prompt(plan, selected_issue, repo_context, retrieved_chunks)

        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_llm_response(content)
            changes = self._build_code_changes(parsed)
            logger.info("Generated %d code change(s)", len(changes))
            return changes
        except Exception:
            logger.exception("LLM development failed — returning fallback changes")
            return self._fallback_changes(plan, selected_issue, retrieved_chunks)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        plan: Plan,
        issue: SelectedIssue,
        repo_context: RepoContext,
        chunks: list[RetrievedChunk],
    ) -> str:
        """Construct the code generation prompt for the LLM."""

        # Repository context
        repo_block = (
            f"Repository: {repo_context.repository_name}\n"
            f"Languages: {', '.join(repo_context.languages) or 'Unknown'}\n"
            f"Frameworks: {', '.join(repo_context.framework_hints) or 'None'}"
        )

        # Issue
        issue_block = (
            f"Issue #{issue.number}: {issue.title}\n"
            f"Body: {issue.body or '(no description)'}"
        )

        # Plan
        plan_block = f"Approach: {plan.approach_reasoning}\n"
        plan_block += f"Affected Files: {', '.join(plan.affected_files)}\n"
        if plan.tasks:
            plan_block += "Tasks:\n"
            for t in plan.tasks:
                plan_block += f"  [{t.id}] {t.description}\n"

        # Current code (retrieved chunks)
        if chunks:
            code_entries = []
            for chunk in chunks:
                entry = (
                    f"  File: {chunk.file_path} "
                    f"(lines {chunk.start_line}-{chunk.end_line}, {chunk.language})\n"
                    f"  ```{chunk.language}\n{chunk.content}\n  ```"
                )
                code_entries.append(entry)
            code_block = "\n\n".join(code_entries)
        else:
            code_block = "  (No code context available)"

        return f"""You are a senior software engineer implementing code changes for an autonomous AI coding agent called Sentinel.

You are executing a pre-approved implementation plan. Your job is to produce the EXACT code modifications needed.

{repo_block}

{issue_block}

Implementation Plan:
{plan_block}

Current Code:
{code_block}

Requirements:
1. Generate ONLY the changes described in the plan.
2. Produce unified diffs (like git diff output).
3. Minimize the number of changed lines.
4. Preserve code style and formatting.
5. Do NOT make speculative or unnecessary changes.
6. Do NOT refactor beyond what the plan requires.
7. Each change must include a clear description of what changed and why.

Respond with a JSON object containing a single field:

"changes": A list of file changes. Each change is an object with:
  - "file_path": The relative file path being modified.
  - "description": A human-readable summary of the change and why it was made.
  - "patch": A unified diff showing the exact change. Use standard unified diff format:
    Lines starting with '-' are removed.
    Lines starting with '+' are added.
    Lines starting with ' ' (space) are unchanged context lines.
    Include a few context lines around each change for clarity.

Example format:
{{
  "changes": [
    {{
      "file_path": "src/main.py",
      "description": "Fix the return value to match expected type.",
      "patch": "--- a/src/main.py\\n+++ b/src/main.py\\n@@ -10,3 +10,3 @@\\n     result = compute()\\n-    return None\\n+    return result\\n     # end"
    }}
  ]
}}

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
    def _build_code_changes(parsed: dict[str, Any]) -> list[CodeChange]:
        """Build CodeChange objects from the LLM response."""
        raw_changes = parsed.get("changes", [])
        changes: list[CodeChange] = []

        for c in raw_changes:
            try:
                change = CodeChange(
                    file_path=c.get("file_path", ""),
                    patch=c.get("patch", ""),
                    description=c.get("description", ""),
                )
                if change.file_path and change.patch:
                    changes.append(change)
                else:
                    logger.warning(
                        "Skipping empty CodeChange: file_path=%s, patch length=%d",
                        change.file_path,
                        len(change.patch),
                    )
            except Exception:
                logger.warning("Failed to build CodeChange from: %s", c)

        return changes

    @staticmethod
    def _fallback_changes(
        plan: Plan,
        issue: SelectedIssue,
        chunks: list[RetrievedChunk],
    ) -> list[CodeChange]:
        """Generate conservative fallback changes when the LLM fails.

        Uses the plan's affected files and retrieved chunks to produce
        a minimal placeholder change with instructions.
        """
        changes: list[CodeChange] = []

        for file_path in plan.affected_files:
            # Find the matching chunk for this file
            matching_chunk = None
            for chunk in chunks:
                if chunk.file_path == file_path:
                    matching_chunk = chunk
                    break

            task_descriptions = "\n".join(
                f"  - {t.description}" for t in plan.tasks
            )

            description = (
                f"Fallback: LLM code generation failed for issue #{issue.number}. "
                f"Manual implementation required.\n"
                f"Plan tasks:\n{task_descriptions}"
            )

            patch = f"--- a/{file_path}\n+++ b/{file_path}\n"
            if matching_chunk:
                patch += (
                    f"@@ Manual change required @@\n"
                    f" # Issue: {issue.title}\n"
                    f" # File: {file_path}\n"
                    f" # Action: {plan.approach_reasoning[:200]}\n"
                )

            changes.append(
                CodeChange(
                    file_path=file_path,
                    patch=patch,
                    description=description,
                )
            )

        return changes
