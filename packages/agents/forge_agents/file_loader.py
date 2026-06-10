from __future__ import annotations

import logging
from pathlib import Path

from forge_workflows.state import FullFileContext

logger = logging.getLogger(__name__)

_EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "bash",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
}


class FileLoader:
    """Reads complete file contents from a cloned workspace.

    Pure filesystem utility — no LLM, no database, no HTTP.
    """

    def load_files(
        self,
        workspace_path: str,
        file_paths: list[str],
    ) -> list[FullFileContext]:
        """Read complete contents for the given relative file paths.

        Args:
            workspace_path: Absolute path to the cloned repository root.
            file_paths: Relative paths from the repo root to load.

        Returns:
            One :class:`FullFileContext` per successfully read file.
            Missing or unreadable files are skipped with a warning.
            Duplicate paths are silently deduplicated.
        """
        seen: set[str] = set()
        results: list[FullFileContext] = []

        for path_str in file_paths:
            if path_str in seen:
                continue
            seen.add(path_str)

            full_path = Path(workspace_path) / path_str
            if not full_path.exists():
                logger.warning("File not found in workspace: %s", path_str)
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                logger.warning("Failed to read file: %s", path_str, exc_info=True)
                continue

            language = _EXTENSION_LANGUAGES.get(full_path.suffix.lower())
            results.append(
                FullFileContext(
                    file_path=path_str,
                    content=content,
                    language=language,
                    line_count=content.count("\n") + 1 if content else 0,
                )
            )

        logger.info("Loaded %d file(s) from workspace", len(results))
        return results


file_loader = FileLoader()
