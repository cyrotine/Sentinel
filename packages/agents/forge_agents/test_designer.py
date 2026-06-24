"""Test Designer agent for Sentinel Brain.

Authors **executable** test cases for the selected issue *before* the developer writes
any code (test-first / TDD). It reads the issue's acceptance criteria, the planner's
``tests_needed``, and the full files, then emits a list of :class:`TestSpec` objects that
the ``test_agent`` node later runs for real via the SandboxRunner.

Design (mirrors ``planner.py``):
    - Pure LLM class — no filesystem, database, or external services.
    - All context is passed into :meth:`design`.
    - Output is parsed into typed :class:`TestSpec` / :class:`TestAssertion` models —
      never raw dictionaries.
    - Deterministic fallback (one html-validate spec per changed HTML file) when the LLM
      is unavailable or returns nothing usable.

Two test frameworks the designer may emit (both run locally, no Docker):
    - ``html-validate`` — validity of an HTML file (well-formedness, accessibility).
    - ``assertion``     — content/DOM checks (``dom_text``, ``dom_attr``,
      ``content_regex``, ``content_contains``) evaluated in-process.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from forge_workflows.state import (
    FullFileContext,
    Plan,
    RepoContext,
    SelectedIssue,
    TestAssertion,
    TestSpec,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

_ASSERTION_TYPES = {"dom_text", "dom_attr", "content_regex", "content_contains"}


class TestDesignerAgent:
    """Designs executable test specs from a plan, before code generation.

    Args:
        llm: A LangChain chat model instance (e.g. ``ChatGoogleGenerativeAI``).
    """

    name: str = "test_designer"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def design(
        self,
        *,
        selected_issue: SelectedIssue,
        plan: Plan,
        repo_context: RepoContext,
        full_file_contexts: list[FullFileContext],
    ) -> list[TestSpec]:
        """Produce executable test specs for the selected issue.

        Args:
            selected_issue: The issue being resolved.
            plan: The implementation plan (its ``tests_needed`` seeds the criteria).
            repo_context: Repository understanding from the repo_analyzer.
            full_file_contexts: Complete file contents read from the workspace.

        Returns:
            A list of :class:`TestSpec`. Falls back to a minimal html-validate spec set
            on failure; never raises.
        """
        logger.info(
            "Designing tests for issue #%d: %s",
            selected_issue.number,
            selected_issue.title,
        )

        prompt = self._build_prompt(selected_issue, plan, repo_context, full_file_contexts)

        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_llm_response(content)
            specs = self._build_specs(parsed)
            if not specs:
                logger.warning("Test designer produced no specs — using fallback")
                return self._fallback_specs(plan, full_file_contexts)
            logger.info("Designed %d test spec(s)", len(specs))
            return specs
        except Exception:
            logger.exception("LLM test design failed — using fallback specs")
            return self._fallback_specs(plan, full_file_contexts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        issue: SelectedIssue,
        plan: Plan,
        repo_context: RepoContext,
        full_file_contexts: list[FullFileContext],
    ) -> str:
        """Construct the test-design prompt for the LLM."""

        criteria = plan.tests_needed or []
        criteria_block = (
            "\n".join(f"  - {c}" for c in criteria)
            if criteria
            else "  (none stated — derive criteria from the issue and files)"
        )

        file_entries = []
        for fc in full_file_contexts:
            lang = fc.language or ""
            file_entries.append(
                f"  ### {fc.file_path} ({fc.line_count} lines)\n  ```{lang}\n{fc.content}\n  ```"
            )
        files_block = "\n\n".join(file_entries) if file_entries else "  (no files loaded)"

        return f"""You are a senior QA engineer writing executable acceptance tests for a code
change BEFORE the developer implements it (test-driven development).

Repository: {repo_context.repository_name}
Languages: {', '.join(repo_context.languages) or 'Unknown'}

Issue #{issue.number}: {issue.title}
Body: {issue.body or '(no description)'}

Acceptance criteria to verify (from the planner):
{criteria_block}

Current file contents (the tests must pass AFTER the issue is correctly fixed):
{files_block}

You can author two kinds of tests, both run locally:

1. "html-validate" — checks an HTML file is valid/well-formed. Use sparingly, only when
   structural validity matters. Requires only "target_file".

2. "assertion" — checks specific content. Use this for the actual acceptance criteria
   (label text, attribute values, CSS color/text). Each assertion has a "type":
   - "dom_text": element text. Fields: "selector" (CSS), and one of "expected" (exact)
     or "contains" (substring).
   - "dom_attr": element attribute. Fields: "selector", "attr", and "expected"/"contains".
   - "content_regex": regex over raw file text. Field: "pattern".
   - "content_contains": substring over raw file text. Field: "contains".

Rules:
- Write tests that describe the CORRECT end state (what the file should look like after
  the fix), NOT the current buggy state.
- Prefer "assertion" tests tied to each acceptance criterion. Target real files that exist
  above. For CSS values in a .css file, use content_regex/content_contains.
- Keep selectors simple and robust.

Respond with a JSON object containing a "tests" array. Each test has exactly:
- "id": string (e.g. "test_1").
- "name": string (human-readable).
- "acceptance_criterion": string (which requirement this verifies).
- "target_file": string (repo-relative path, must be one of the files above).
- "framework": "html-validate" or "assertion".
- "assertions": array (REQUIRED when framework is "assertion"; omit/empty for html-validate).
  Each assertion: {{"type": ..., "selector": ..., "attr": ..., "expected": ..., "contains": ..., "pattern": ...}}
  Only include the fields relevant to the type.

Respond with valid JSON only. No markdown, no explanation, just the JSON object."""

    @staticmethod
    def _parse_llm_response(content: str) -> dict[str, Any]:
        """Extract a JSON object from the LLM response (mirrors PlannerAgent)."""
        text = content.strip()

        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            logger.warning("Test designer returned unexpected JSON type: %s", type(parsed))
            return {}
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse test designer JSON response: %s", exc)
            logger.debug("Raw LLM output: %s", content[:500])
            return {}

    @staticmethod
    def _build_specs(parsed: dict[str, Any]) -> list[TestSpec]:
        """Build typed TestSpec objects from the parsed LLM response."""
        raw_tests = parsed.get("tests", [])
        if not isinstance(raw_tests, list):
            logger.warning("Expected 'tests' to be a list, got %s", type(raw_tests))
            return []

        specs: list[TestSpec] = []
        for i, t in enumerate(raw_tests, 1):
            if not isinstance(t, dict):
                continue
            target_file = str(t.get("target_file", "")).strip()
            if not target_file:
                continue

            framework = t.get("framework", "assertion")
            if framework not in ("html-validate", "assertion"):
                framework = "assertion"

            assertions: list[TestAssertion] = []
            if framework == "assertion":
                for raw_a in t.get("assertions", []) or []:
                    if not isinstance(raw_a, dict):
                        continue
                    a_type = raw_a.get("type")
                    if a_type not in _ASSERTION_TYPES:
                        continue
                    assertions.append(
                        TestAssertion(
                            type=a_type,
                            selector=raw_a.get("selector"),
                            attr=raw_a.get("attr"),
                            expected=raw_a.get("expected"),
                            contains=raw_a.get("contains"),
                            pattern=raw_a.get("pattern"),
                        )
                    )
                # An assertion spec with no valid assertions is unusable — skip it.
                if not assertions:
                    continue

            specs.append(
                TestSpec(
                    id=str(t.get("id") or f"test_{i}"),
                    name=str(t.get("name") or f"Test {i}"),
                    acceptance_criterion=str(t.get("acceptance_criterion", "")),
                    target_file=target_file,
                    framework=framework,
                    assertions=assertions,
                )
            )

        return specs

    @staticmethod
    def _fallback_specs(
        plan: Plan, full_file_contexts: list[FullFileContext]
    ) -> list[TestSpec]:
        """Minimal deterministic specs: validate each changed HTML file.

        Used when the LLM is unavailable or returns nothing usable. Validity is the only
        thing we can assert without understanding the specific acceptance criteria.
        """
        html_paths = [
            p for p in plan.affected_files if p.lower().endswith((".html", ".htm"))
        ]
        if not html_paths:
            html_paths = [
                fc.file_path
                for fc in full_file_contexts
                if fc.file_path.lower().endswith((".html", ".htm"))
            ]

        specs: list[TestSpec] = []
        for i, path in enumerate(dict.fromkeys(html_paths), 1):
            specs.append(
                TestSpec(
                    id=f"test_{i}",
                    name=f"Validate {path}",
                    acceptance_criterion="Changed HTML remains valid.",
                    target_file=path,
                    framework="html-validate",
                )
            )
        return specs
