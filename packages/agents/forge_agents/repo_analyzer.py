"""Repository Analyzer agent for Sentinel Brain.

Produces a :class:`RepoContext` by combining stored repository metadata
(from Postgres) with LLM-generated insights (framework detection, module
identification, architecture summary).

Design:
    - The agent is a **pure LLM class** — it does not access databases directly.
    - Raw data (file paths, languages, repo metadata) is passed in via
      the ``analyze`` method.  The caller (brain_service or test script)
      is responsible for querying Postgres.
    - Only ``framework_hints``, ``detected_modules``, ``key_files``, and
      ``architecture_summary`` require an LLM call.  Everything else is
      computed from stored data.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import TYPE_CHECKING, Any

from forge_workflows.state import RepoContext

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# Maximum number of file paths to include in the LLM prompt.
# Prevents token overflow on large repositories.
_MAX_FILES_IN_PROMPT = 500


class RepoAnalyzerAgent:
    """Analyzes a repository's structure and technology stack.

    The agent receives pre-loaded data (file list, languages, repo metadata)
    and uses an LLM to produce the fields that require reasoning:
    framework detection, module identification, key file selection,
    and an architecture summary.

    Args:
        llm: A LangChain chat model instance (e.g. ``ChatGoogleGenerativeAI``).
    """

    name: str = "repo_analyzer"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def analyze(
        self,
        *,
        repo_name: str,
        repo_description: str,
        file_paths: list[str],
        file_languages: dict[str, str | None],
        total_files: int,
    ) -> RepoContext:
        """Produce a :class:`RepoContext` for the given repository data.

        Args:
            repo_name: Full repository name (e.g. ``"owner/repo"``).
            repo_description: GitHub description of the repository.
            file_paths: List of relative file paths from the repository.
            file_languages: Mapping of file path → detected language (or None).
            total_files: Total number of source files in the repository.

        Returns:
            A fully populated :class:`RepoContext`.
        """
        # --- Step 1: Compute language distribution from stored data ---
        lang_counter: Counter[str] = Counter()
        for lang in file_languages.values():
            if lang:
                lang_counter[lang] += 1
        languages = [lang for lang, _ in lang_counter.most_common()]

        logger.info(
            "Analyzing repo=%s  files=%d  languages=%s",
            repo_name,
            total_files,
            languages,
        )

        # --- Step 2: Build the LLM prompt ---
        prompt = self._build_prompt(
            repo_name=repo_name,
            repo_description=repo_description,
            file_paths=file_paths,
            lang_counter=lang_counter,
            total_files=total_files,
        )

        # --- Step 3: Call the LLM ---
        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            llm_result = self._parse_llm_response(content)
            logger.info("LLM analysis completed for %s", repo_name)
        except Exception:
            logger.exception("LLM call failed for %s — returning partial RepoContext", repo_name)
            llm_result = {}

        # --- Step 4: Assemble RepoContext ---
        return RepoContext(
            repository_name=repo_name,
            description=repo_description or "",
            languages=languages,
            framework_hints=llm_result.get("framework_hints", []),
            total_files=total_files,
            key_files=llm_result.get("key_files", []),
            detected_modules=llm_result.get("detected_modules", []),
            architecture_summary=llm_result.get("architecture_summary", ""),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        repo_name: str,
        repo_description: str,
        file_paths: list[str],
        lang_counter: Counter[str],
        total_files: int,
    ) -> str:
        """Construct the analysis prompt for the LLM."""

        # Language distribution block
        lang_lines = "\n".join(
            f"  - {lang}: {count} files"
            for lang, count in lang_counter.most_common()
        )

        # File tree — truncate for large repos
        display_paths = file_paths[:_MAX_FILES_IN_PROMPT]
        file_tree = "\n".join(display_paths)
        truncation_note = ""
        if len(file_paths) > _MAX_FILES_IN_PROMPT:
            truncation_note = (
                f"\n(Showing {_MAX_FILES_IN_PROMPT} of {len(file_paths)} files. "
                f"Infer the full structure from these.)"
            )

        return f"""You are a senior software architect analyzing a repository.

Repository: {repo_name}
Description: {repo_description or "No description provided."}
Total source files: {total_files}

Language Distribution:
{lang_lines}

File Tree:
{file_tree}{truncation_note}

Based on this repository structure, respond with a JSON object containing exactly these fields:

1. "framework_hints": A list of frameworks and libraries this project likely uses.
   Detect from file names, directory structure, and language ecosystem conventions.
   Examples: "FastAPI", "React", "Next.js", "SQLAlchemy", "Django", "Express".

2. "key_files": A list of the most architecturally important files in this repository.
   Include entry points, main configuration files, READMEs, and core modules.
   Return relative file paths from the list above. Maximum 15 files.

3. "detected_modules": A list of logical modules or packages in this codebase.
   Identify distinct functional areas based on directory structure and naming.
   Examples: "api", "auth", "database", "frontend", "tests".

4. "architecture_summary": A concise 2-4 sentence summary describing the repository's
   architecture, technology stack, and how the codebase is organized.

Respond with valid JSON only. No markdown, no explanation, just the JSON object."""

    @staticmethod
    def _parse_llm_response(content: str) -> dict[str, Any]:
        """Extract a JSON object from the LLM response.

        Handles cases where the model wraps JSON in markdown code fences.
        """
        text = content.strip()

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            logger.warning("LLM returned non-dict JSON: %s", type(parsed))
            return {}
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM JSON response: %s", exc)
            logger.debug("Raw LLM output: %s", content[:500])
            return {}
