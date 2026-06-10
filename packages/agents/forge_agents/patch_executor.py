"""Patch executor for Sentinel Brain.

Applies the unified diffs produced by the :class:`DeveloperAgent` to the real
files in a cloned workspace, using the host ``git`` binary.

Design (mirrors ``file_loader.py``):
    - Pure filesystem + git utility — no LLM, no database, no HTTP, no ``app.*``.
    - Synchronous; the graph node wraps calls in ``asyncio.to_thread``.
    - A failed patch is a *reported outcome* (:class:`PatchResult` with
      ``applied=False``), never a raised exception. Patch failures are surfaced,
      not swallowed.
    - Instantiated once as a module-level singleton: ``patch_executor``.

The workspace is a git repository (Phase 2 clones it), so we lean on
``git apply`` for strict application and ``git apply --3way`` for one cheap
fuzzy retry before declaring failure.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from forge_workflows.state import CodeChange, PatchResult

logger = logging.getLogger(__name__)

# Matches a leading/trailing markdown code fence the LLM may have wrapped the
# diff in despite instructions to emit raw diffs.
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n|\n?```\s*$")


class PatchExecutor:
    """Applies unified diffs to a cloned workspace via ``git apply``.

    Pure filesystem/git utility — no LLM, no database, no HTTP.
    """

    def apply_patch(self, workspace_path: str, code_change: CodeChange) -> PatchResult:
        """Apply a single ``CodeChange`` to its target file in the workspace.

        Args:
            workspace_path: Absolute path to the cloned repository root.
            code_change: The change to apply; ``patch`` is a unified diff.

        Returns:
            A :class:`PatchResult`. On failure, ``failed_patch`` and
            ``full_file_content`` are populated for downstream regeneration.
            Never raises on a bad patch.
        """
        target = self._safe_target(workspace_path, code_change.file_path)
        if target is None:
            logger.warning(
                "Refusing patch to path outside workspace: %s", code_change.file_path
            )
            return PatchResult(
                file_path=code_change.file_path,
                applied=False,
                error="Target path resolves outside the workspace root.",
                failed_patch=code_change.patch,
                full_file_content=None,
            )

        patch = self._normalize(code_change.patch)

        # Strict apply: dry-run check, then real apply.
        check = self._run(["apply", "--check", "-"], patch, workspace_path)
        if check.returncode == 0:
            applied = self._run(["apply", "-"], patch, workspace_path)
            if applied.returncode == 0:
                return PatchResult(
                    file_path=code_change.file_path,
                    applied=True,
                    strategy="git-apply",
                )

        # Fuzzy apply: use blob context to absorb shifted hunks.
        three_way = self._run(["apply", "--3way", "-"], patch, workspace_path)
        if three_way.returncode == 0:
            return PatchResult(
                file_path=code_change.file_path,
                applied=True,
                strategy="git-apply-3way",
            )

        error = (check.stderr or three_way.stderr or "git apply failed").strip()
        logger.warning("Patch failed for %s: %s", code_change.file_path, error)
        return PatchResult(
            file_path=code_change.file_path,
            applied=False,
            error=error,
            failed_patch=code_change.patch,
            full_file_content=self._read_if_exists(target),
        )

    def apply_all(
        self, workspace_path: str, code_changes: list[CodeChange]
    ) -> list[PatchResult]:
        """Apply each change in order, returning one result per change."""
        results = [self.apply_patch(workspace_path, c) for c in code_changes]
        logger.info(
            "Applied %d/%d patch(es)", sum(r.applied for r in results), len(results)
        )
        return results

    def rollback_all(self, workspace_path: str) -> None:
        """Restore the workspace to the pristine clone.

        Reverts tracked files and removes untracked/created files so each
        retry iteration applies its diffs against a clean tree.
        """
        self._run_git(["checkout", "--", "."], workspace_path)
        self._run_git(["clean", "-fd"], workspace_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_target(workspace_path: str, file_path: str) -> Path | None:
        """Resolve ``file_path`` within the workspace; reject path traversal."""
        root = Path(workspace_path).resolve()
        candidate = (root / file_path).resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate

    @staticmethod
    def _normalize(patch: str) -> str:
        """Strip a stray surrounding markdown fence and ensure trailing newline."""
        text = _FENCE_RE.sub("", patch.strip())
        if not text.endswith("\n"):
            text += "\n"
        return text

    @staticmethod
    def _read_if_exists(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            logger.warning("Failed to read file for failure context: %s", path, exc_info=True)
            return None

    @staticmethod
    def _run(args: list[str], patch: str, cwd: str) -> subprocess.CompletedProcess[str]:
        """Run ``git <args>`` feeding ``patch`` via stdin."""
        return subprocess.run(
            ["git", *args],
            input=patch,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    @staticmethod
    def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
        """Run ``git <args>`` with no stdin (used for rollback)."""
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=cwd,
        )


patch_executor = PatchExecutor()
