"""Issue Analyzer agent for Sentinel Brain.

Produces a list of :class:`IssueAnalysis` by combining stored issue data
(from Postgres) with LLM-generated classifications (type, severity, impact,
affected areas).

Design:
    - The agent is a **pure LLM class** — it does not access databases directly.
    - Raw data (issues, repo context) is passed in via the ``analyze`` method.
      The caller (graph node or test script) is responsible for querying Postgres.
    - Fields that require LLM reasoning: ``issue_type``, ``severity``,
      ``confidence``, ``impact``, ``affected_areas``, ``reasoning``.
    - Fields copied from stored data: ``issue_id``, ``number``, ``title``, ``body``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from forge_workflows.state import IssueAnalysis, RepoContext

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# Maximum number of issues to include in a single LLM call.
# Beyond this, issues are batched to avoid token overflow.
_MAX_ISSUES_PER_CALL = 30


class IssueAnalyzerAgent:
    """Classifies GitHub issues using an LLM.

    The agent receives pre-loaded issue data and repository context,
    builds a structured prompt, and uses the LLM to produce an
    :class:`IssueAnalysis` for each issue.

    Args:
        llm: A LangChain chat model instance (e.g. ``ChatGoogleGenerativeAI``).
    """

    name: str = "issue_analyzer"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def analyze(
        self,
        *,
        issues: list[dict[str, Any]],
        repo_context: RepoContext,
    ) -> list[IssueAnalysis]:
        """Produce an :class:`IssueAnalysis` for each issue.

        Args:
            issues: List of issue dicts with keys: ``issue_id``, ``number``,
                ``title``, ``body``, ``labels``, ``state``.
            repo_context: Repository context from the prior ``repo_analyzer`` node.

        Returns:
            A list of :class:`IssueAnalysis`, one per input issue.
        """
        if not issues:
            logger.warning("No issues provided — returning empty list")
            return []

        logger.info(
            "Analyzing %d issues for repo=%s",
            len(issues),
            repo_context.repository_name,
        )

        all_analyses: list[IssueAnalysis] = []

        # Batch issues to avoid token overflow on large repositories
        for batch_start in range(0, len(issues), _MAX_ISSUES_PER_CALL):
            batch = issues[batch_start : batch_start + _MAX_ISSUES_PER_CALL]

            prompt = self._build_prompt(batch, repo_context)

            try:
                response = await self._llm.ainvoke(prompt)
                content = response.content if hasattr(response, "content") else str(response)
                parsed = self._parse_llm_response(content)
                batch_analyses = self._build_analyses(parsed, batch)
                all_analyses.extend(batch_analyses)
                logger.info(
                    "LLM analysis completed for batch of %d issues (%d/%d)",
                    len(batch),
                    min(batch_start + _MAX_ISSUES_PER_CALL, len(issues)),
                    len(issues),
                )
            except Exception:
                logger.exception(
                    "LLM call failed for issue batch starting at %d — "
                    "returning partial results with defaults",
                    batch_start,
                )
                # Return fallback analyses for the failed batch
                for issue in batch:
                    all_analyses.append(self._fallback_analysis(issue))

        return all_analyses

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        issues: list[dict[str, Any]],
        repo_context: RepoContext,
    ) -> str:
        """Construct the classification prompt for the LLM."""

        # Build compact repo context block
        repo_block = (
            f"Repository: {repo_context.repository_name}\n"
            f"Description: {repo_context.description or 'No description provided.'}\n"
            f"Languages: {', '.join(repo_context.languages) or 'Unknown'}\n"
            f"Frameworks: {', '.join(repo_context.framework_hints) or 'None detected'}\n"
            f"Key Files: {', '.join(repo_context.key_files) or 'Unknown'}\n"
            f"Modules: {', '.join(repo_context.detected_modules) or 'None detected'}\n"
            f"Architecture: {repo_context.architecture_summary or 'Not available'}"
        )

        # Build issues block
        issue_entries = []
        for issue in issues:
            labels_str = ", ".join(issue.get("labels", [])) or "none"
            entry = (
                f"  Issue #{issue['number']}:\n"
                f"    Title: {issue['title']}\n"
                f"    Body: {issue.get('body') or '(no description)'}\n"
                f"    Labels: {labels_str}\n"
                f"    State: {issue.get('state', 'open')}"
            )
            issue_entries.append(entry)

        issues_block = "\n\n".join(issue_entries)

        return f"""You are a senior software engineer analyzing GitHub issues for a repository.

{repo_block}

The following issues need classification. For EACH issue, provide a structured analysis.

Issues:

{issues_block}

For each issue, respond with a JSON array where each element is an object with exactly these fields:

1. "number": The GitHub issue number (integer, copy from input).

2. "issue_type": One of: "bug", "feature", "refactor", "docs", "test", "chore".
   - "bug": Something is broken or behaving incorrectly.
   - "feature": A new capability or enhancement.
   - "refactor": Code improvement without changing behavior.
   - "docs": Documentation changes.
   - "test": Test additions or modifications.
   - "chore": Maintenance, dependency updates, CI/CD changes.

3. "severity": One of: "critical", "high", "medium", "low".
   - "critical": System is broken or data loss risk.
   - "high": Major functionality affected.
   - "medium": Moderate impact, workaround exists.
   - "low": Minor or cosmetic.

4. "confidence": A float between 0.0 and 1.0 indicating how confident you are in this classification.

5. "impact": A float between 0.0 and 1.0 indicating the estimated impact on the project.

6. "affected_areas": A list of file paths or module names from the repository that are likely affected by this issue. Use the key files and modules from the repository context to inform this.

7. "reasoning": A concise 1-2 sentence explanation of how you arrived at this classification.

Respond with valid JSON only. No markdown, no explanation, just the JSON array."""

    @staticmethod
    def _parse_llm_response(content: str) -> list[dict[str, Any]]:
        """Extract a JSON array from the LLM response.

        Handles cases where the model wraps JSON in markdown code fences.
        """
        text = content.strip()

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                # Some models wrap in {"issues": [...]} or {"analyses": [...]}
                for key in ("issues", "analyses", "results"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                # Single issue wrapped in a dict — wrap in list
                return [parsed]
            logger.warning("LLM returned unexpected JSON type: %s", type(parsed))
            return []
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM JSON response: %s", exc)
            logger.debug("Raw LLM output: %s", content[:500])
            return []

    @staticmethod
    def _build_analyses(
        parsed: list[dict[str, Any]],
        issues: list[dict[str, Any]],
    ) -> list[IssueAnalysis]:
        """Merge LLM classifications with stored issue data.

        The LLM provides: issue_type, severity, confidence, impact,
        affected_areas, reasoning.

        Stored data provides: issue_id, number, title, body.
        """
        # Build a lookup by issue number for matching
        issue_lookup = {issue["number"]: issue for issue in issues}

        analyses: list[IssueAnalysis] = []
        for item in parsed:
            number = item.get("number", 0)
            source_issue = issue_lookup.get(number, {})

            try:
                analysis = IssueAnalysis(
                    # LLM-generated fields
                    issue_type=item.get("issue_type", "chore"),
                    severity=item.get("severity", "medium"),
                    confidence=float(item.get("confidence", 0.5)),
                    impact=float(item.get("impact", 0.5)),
                    affected_areas=item.get("affected_areas", []),
                    reasoning=item.get("reasoning", ""),
                    # Stored data fields (prefer source issue, fallback to LLM)
                    issue_id=source_issue.get("issue_id", ""),
                    number=number,
                    title=source_issue.get("title", item.get("title", "")),
                    body=source_issue.get("body", item.get("body", "")),
                )
                analyses.append(analysis)
            except Exception:
                logger.exception("Failed to build IssueAnalysis for issue #%s", number)

        return analyses

    @staticmethod
    def _fallback_analysis(issue: dict[str, Any]) -> IssueAnalysis:
        """Create a default IssueAnalysis when the LLM call fails."""
        return IssueAnalysis(
            issue_type="chore",
            severity="medium",
            confidence=0.0,
            impact=0.5,
            affected_areas=[],
            reasoning="LLM analysis failed — default classification applied",
            issue_id=issue.get("issue_id", ""),
            number=issue.get("number", 0),
            title=issue.get("title", ""),
            body=issue.get("body", ""),
        )
