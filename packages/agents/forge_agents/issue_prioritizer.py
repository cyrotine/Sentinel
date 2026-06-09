"""Issue Prioritizer agent for Sentinel Brain.

Selects the single highest-priority issue from a list of :class:`IssueAnalysis`
objects, producing a :class:`SelectedIssue`.

Design:
    - The agent is a **pure LLM class** — it does not access databases directly.
    - Pre-classified issue analyses are passed in via the ``prioritize`` method.
    - The LLM acts as an experienced engineering lead choosing the next task
      for an autonomous software engineer, optimizing for hackathon demo value.
    - Supports a ``target_issue_id`` override to bypass LLM ranking when the
      user has pre-selected a specific issue.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from forge_workflows.state import IssueAnalysis, SelectedIssue

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class IssuePrioritizerAgent:
    """Selects the best issue for implementation using an LLM.

    The agent receives pre-classified issue analyses and uses the LLM
    to select one issue, providing reasoning and a complexity estimate.

    Args:
        llm: A LangChain chat model instance (e.g. ``ChatGoogleGenerativeAI``).
    """

    name: str = "issue_prioritizer"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def prioritize(
        self,
        *,
        issue_analyses: list[IssueAnalysis],
        target_issue_id: str | None = None,
    ) -> SelectedIssue:
        """Select the highest-priority issue for implementation.

        Args:
            issue_analyses: Classified issues from the IssueAnalyzerAgent.
            target_issue_id: If set, bypass LLM ranking and select this issue
                directly (user-specified override).

        Returns:
            A :class:`SelectedIssue` with the chosen issue and reasoning.

        Raises:
            ValueError: If no issues are provided.
        """
        if not issue_analyses:
            raise ValueError("No issue analyses provided — cannot prioritize")

        # --- Fast path: user-specified target ---
        if target_issue_id:
            return self._select_by_id(issue_analyses, target_issue_id)

        # --- Single issue: skip LLM, select directly ---
        if len(issue_analyses) == 1:
            analysis = issue_analyses[0]
            logger.info(
                "Single issue #%d — selecting directly without LLM",
                analysis.number,
            )
            return SelectedIssue(
                issue_id=analysis.issue_id,
                number=analysis.number,
                title=analysis.title,
                body=analysis.body,
                reasoning=(
                    f"Only open issue available (#{analysis.number}: {analysis.title}). "
                    f"Classified as {analysis.issue_type}/{analysis.severity} "
                    f"with confidence {analysis.confidence:.2f} and impact {analysis.impact:.2f}."
                ),
                estimated_complexity=self._estimate_complexity_from_analysis(analysis),
            )

        # --- Multiple issues: use LLM to rank ---
        logger.info("Prioritizing %d issues via LLM", len(issue_analyses))

        prompt = self._build_prompt(issue_analyses)

        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_llm_response(content)
            selected = self._build_selected_issue(parsed, issue_analyses)
            logger.info("LLM selected issue #%d: %s", selected.number, selected.title)
            return selected
        except Exception:
            logger.exception(
                "LLM prioritization failed — falling back to heuristic ranking"
            )
            return self._heuristic_fallback(issue_analyses)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _select_by_id(
        analyses: list[IssueAnalysis],
        target_id: str,
    ) -> SelectedIssue:
        """Select a specific issue by ID (user override)."""
        for a in analyses:
            if a.issue_id == target_id:
                logger.info(
                    "User-specified target issue #%d selected directly", a.number
                )
                return SelectedIssue(
                    issue_id=a.issue_id,
                    number=a.number,
                    title=a.title,
                    body=a.body,
                    reasoning=(
                        f"User explicitly requested issue #{a.number}. "
                        f"Classified as {a.issue_type}/{a.severity}."
                    ),
                    estimated_complexity="medium",
                )
        # Target not found — log warning and fall through to first issue
        logger.warning(
            "target_issue_id=%s not found in analyses — selecting first issue",
            target_id,
        )
        a = analyses[0]
        return SelectedIssue(
            issue_id=a.issue_id,
            number=a.number,
            title=a.title,
            body=a.body,
            reasoning=f"Requested issue {target_id} not found. Defaulting to #{a.number}.",
            estimated_complexity="medium",
        )

    def _build_prompt(self, analyses: list[IssueAnalysis]) -> str:
        """Construct the prioritization prompt for the LLM."""

        issue_blocks = []
        for a in analyses:
            block = (
                f"  Issue #{a.number}:\n"
                f"    Title: {a.title}\n"
                f"    Body: {a.body or '(no description)'}\n"
                f"    Type: {a.issue_type}\n"
                f"    Severity: {a.severity}\n"
                f"    Confidence: {a.confidence:.2f}\n"
                f"    Impact: {a.impact:.2f}\n"
                f"    Affected Areas: {', '.join(a.affected_areas) or 'unknown'}\n"
                f"    Analysis: {a.reasoning}"
            )
            issue_blocks.append(block)

        issues_text = "\n\n".join(issue_blocks)

        return f"""You are an experienced engineering lead selecting the next task for an autonomous AI software engineer called Sentinel.

Sentinel is an AI agent that can:
- Read repository code
- Understand issues
- Plan implementations
- Generate code changes
- Create pull requests

You must select exactly ONE issue for Sentinel to work on next.

Evaluated Issues:

{issues_text}

Selection Criteria (in priority order):

1. DEMO VALUE: Prefer issues that clearly demonstrate Sentinel's capabilities.
   Issues with visible, tangible output (UI changes, new features) are preferred
   over invisible infrastructure work.

2. FEASIBILITY: Prefer issues that an AI agent can realistically complete autonomously.
   Simple, well-scoped issues are preferred over vague or complex ones.

3. IMPACT: Prefer issues with higher impact scores and severity.

4. RISK: Prefer issues with lower implementation risk.
   Well-defined issues with clear requirements are preferred.

5. CONFIDENCE: Prefer issues where the analysis has higher confidence.

Respond with a JSON object containing exactly these fields:

1. "number": The GitHub issue number you selected (integer).

2. "reasoning": A 2-3 sentence explanation of WHY you selected this issue over
   the others. Reference the selection criteria above.

3. "estimated_complexity": One of "low", "medium", "high".
   - "low": Simple change, single file, clear requirements.
   - "medium": Multiple files or moderate logic changes.
   - "high": Complex architecture changes or many dependencies.

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
            # If array, take first element
            if isinstance(parsed, list) and parsed:
                return parsed[0]
            logger.warning("LLM returned unexpected JSON type: %s", type(parsed))
            return {}
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM JSON response: %s", exc)
            logger.debug("Raw LLM output: %s", content[:500])
            return {}

    @staticmethod
    def _build_selected_issue(
        parsed: dict[str, Any],
        analyses: list[IssueAnalysis],
    ) -> SelectedIssue:
        """Build a SelectedIssue from the LLM response and source analyses."""
        selected_number = parsed.get("number", 0)

        # Find the matching analysis
        source = None
        for a in analyses:
            if a.number == selected_number:
                source = a
                break

        if source is None:
            logger.warning(
                "LLM selected issue #%d which is not in the analyses — "
                "falling back to first issue",
                selected_number,
            )
            source = analyses[0]

        return SelectedIssue(
            issue_id=source.issue_id,
            number=source.number,
            title=source.title,
            body=source.body,
            reasoning=parsed.get("reasoning", "Selected by LLM prioritization."),
            estimated_complexity=parsed.get("estimated_complexity", "medium"),
        )

    @staticmethod
    def _heuristic_fallback(analyses: list[IssueAnalysis]) -> SelectedIssue:
        """Simple heuristic selection when LLM fails.

        Ranks by: severity weight * impact * confidence.
        """
        severity_weights = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}

        def score(a: IssueAnalysis) -> float:
            w = severity_weights.get(a.severity, 1.0)
            return w * a.impact * a.confidence

        ranked = sorted(analyses, key=score, reverse=True)
        best = ranked[0]

        return SelectedIssue(
            issue_id=best.issue_id,
            number=best.number,
            title=best.title,
            body=best.body,
            reasoning=(
                f"Heuristic fallback: selected #{best.number} with highest "
                f"composite score ({best.severity}/{best.impact:.2f}/{best.confidence:.2f})."
            ),
            estimated_complexity="medium",
        )

    @staticmethod
    def _estimate_complexity_from_analysis(analysis: IssueAnalysis) -> str:
        """Estimate complexity from issue analysis metadata (no LLM needed)."""
        # Simple heuristic based on affected areas and issue type
        area_count = len(analysis.affected_areas)
        if analysis.issue_type in ("refactor", "feature") and area_count > 3:
            return "high"
        if area_count > 1 or analysis.issue_type == "feature":
            return "medium"
        return "low"
