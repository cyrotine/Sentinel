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
    FullFileContext,
    Plan,
    RepairContext,
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
        full_file_contexts: list[FullFileContext],
        repair_context: RepairContext | None = None,
    ) -> list[CodeChange]:
        """Generate code changes based on the implementation plan.

        Args:
            plan: The implementation plan from the PlannerAgent.
            selected_issue: The issue being resolved.
            repo_context: Repository understanding from the repo_analyzer.
            retrieved_chunks: Relevant code chunks from Qdrant.
            full_file_contexts: Complete file contents read from the workspace.
            repair_context: Failure feedback from the prior attempt on a retry
                iteration. ``None`` on the first attempt — when ``None`` the prompt
                is identical to a fresh run.

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

        prompt = self._build_prompt(
            plan, selected_issue, repo_context, retrieved_chunks, full_file_contexts, repair_context
        )

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
        full_file_contexts: list[FullFileContext],
        repair_context: RepairContext | None = None,
    ) -> str:
        """Construct the code generation prompt for the LLM."""

        # On a retry, the failure feedback is the first thing the model sees so it
        # dominates attention. When None (first attempt) the prompt is unchanged.
        repair_block = (
            self._build_repair_block(repair_context) if repair_context is not None else ""
        )

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

        # Full file contents for affected files (ground-truth for diff generation)
        full_file_map = {fc.file_path: fc for fc in full_file_contexts}
        full_file_entries = []
        for file_path in plan.affected_files:
            fc = full_file_map.get(file_path)
            if fc:
                lang = fc.language or ""
                numbered = "\n".join(
                    f"{i + 1:4d} | {line}"
                    for i, line in enumerate(fc.content.splitlines())
                )
                full_file_entries.append(
                    f"  ### {file_path} ({fc.line_count} lines, {lang})\n"
                    f"  ```{lang}\n{numbered}\n  ```"
                )
        full_files_block = (
            "\n\n".join(full_file_entries)
            if full_file_entries
            else "  (No full file context available — workspace not cloned)"
        )

        # Supplementary Qdrant chunks for files not covered by full file loading
        covered = set(full_file_map)
        supplementary = [c for c in chunks if c.file_path not in covered]
        if supplementary:
            chunk_entries = [
                f"  File: {c.file_path} (lines {c.start_line}-{c.end_line}, {c.language})\n"
                f"  ```{c.language}\n{c.content}\n  ```"
                for c in supplementary
            ]
            chunks_block = "\n\n".join(chunk_entries)
        else:
            chunks_block = "  (All affected files covered by full file context above)"

        return f"""You are a senior software engineer implementing code changes for an autonomous AI coding agent called Sentinel.

You are executing a pre-approved implementation plan. Your job is to produce the EXACT code modifications needed.
{repair_block}
{repo_block}

{issue_block}

Implementation Plan:
{plan_block}

Full File Contents (use these as the ground truth for generating diffs — line numbers are exact):
{full_files_block}

Additional Context (Qdrant chunks for files not listed above):
{chunks_block}

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
    def _build_repair_block(repair: RepairContext) -> str:
        """Build the 'PREVIOUS ATTEMPT FAILED' section fed back on a retry.

        Echoes each failed diff alongside the current on-disk file content so the
        model re-diffs against ground truth, plus validation and review feedback.
        The workspace is rolled back to the pristine clone before each apply, so
        regenerated diffs must target the *original* file content shown here.
        """
        lines: list[str] = [
            "",
            "PREVIOUS ATTEMPT FAILED — fix the specific problems below, then regenerate ALL changes.",
            f"Trigger(s): {', '.join(repair.triggers) or 'unknown'}",
        ]

        if repair.failed_patches:
            lines.append("")
            lines.append("The following patch(es) did NOT apply cleanly:")
            for pr in repair.failed_patches:
                lines.append("")
                lines.append(f"  ### {pr.file_path}")
                lines.append(f"  Reason: {pr.error or 'git apply failed'}")
                lines.append("  Your previous (rejected) diff:")
                lines.append("  ```")
                lines.append(pr.failed_patch or "(empty)")
                lines.append("  ```")
                if pr.full_file_content is not None:
                    lines.append(
                        "  Current on-disk content (diff against THIS — line numbers are exact):"
                    )
                    lines.append("  ```")
                    lines.append(pr.full_file_content)
                    lines.append("  ```")

        if repair.validation_issues or repair.validation_suggestions:
            lines.append("")
            if repair.validation_issues:
                lines.append("Validation issues to resolve:")
                lines.extend(f"  - {item}" for item in repair.validation_issues)
            if repair.validation_suggestions:
                lines.append("Suggestions:")
                lines.extend(f"  - {item}" for item in repair.validation_suggestions)

        if repair.test_failures:
            lines.append("")
            lines.append("Tests that FAILED when run against your changes (make these pass):")
            lines.extend(f"  - {item}" for item in repair.test_failures)

        review_items = (
            repair.review_security_issues + repair.review_comments + repair.review_suggestions
        )
        if review_items:
            lines.append("")
            lines.append("Review feedback to address:")
            lines.extend(f"  - {item}" for item in review_items)

        lines.append("")
        lines.append(
            "Regenerate corrected unified diffs for every affected file. "
            "Diff against the original file content shown above. Do not repeat the rejected diff."
        )
        return "\n".join(lines)

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
