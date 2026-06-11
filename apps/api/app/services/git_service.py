"""Git service for Sentinel Brain.

Commits the patched workspace files onto a fresh feature branch and pushes
to the GitHub remote using the user's PAT.

Design (mirrors ``workspace_manager.py``):
    - Pure git utility — no LLM, no database, no HTTP framework, no ``app.*``
      model imports.
    - Synchronous; BrainService wraps calls in ``asyncio.to_thread``.
    - A failed commit or push is a *reported outcome* (:class:`GitResult` with
      ``committed``/``pushed`` = False and ``error`` set). Never raises on an
      expected git failure.
    - The PAT and authenticated remote URL are never logged.
    - Instantiated once as a module-level singleton: ``git_service``.

This service runs *after* the LangGraph pipeline completes so that the PAT
never enters ``SentinelState`` (which is streamed and partially persisted).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import git

from forge_workflows.state import GitResult

logger = logging.getLogger(__name__)

_BOT_NAME = "Forge Bot"
_BOT_EMAIL = "forge-bot@users.noreply.github.com"

# Matches the PAT inside an x-access-token: authenticated URL so it can be
# redacted in error messages before they reach logs or persisted state.
_PAT_RE = re.compile(r"x-access-token:[^@]+@")


class GitService:
    """Commits and pushes the patched workspace to the GitHub remote.

    Pure filesystem + git utility — no LLM, no database, no HTTP.
    """

    def commit_and_push(
        self,
        *,
        workspace_path: str,
        branch_name: str,
        commit_message: str,
        files: list[str],
        github_url: str,
        pat: str | None,
    ) -> GitResult:
        """Create a branch, commit the supplied files, and push to the remote.

        Args:
            workspace_path: Absolute path to the cloned repository root.
            branch_name: Name of the feature branch to create.
            commit_message: Full commit message (subject + optional body).
            files: Repo-relative paths to stage (from ``PatchResult.file_path``).
            github_url: HTTPS remote URL of the repository.
            pat: Personal Access Token for push auth; ``None`` for public repos.

        Returns:
            A :class:`GitResult`. On failure, ``error`` is populated and
            ``committed``/``pushed`` reflect the actual outcome. Never raises
            on expected git failures.
        """
        if not files:
            return GitResult(
                branch=branch_name,
                committed=False,
                pushed=False,
                error="No files to commit — all patches failed or none were applied.",
            )

        committed = False
        commit_sha: str | None = None
        pushed = False
        error: str | None = None

        try:
            self.create_branch(workspace_path, branch_name)
        except git.GitCommandError as exc:
            return GitResult(
                branch=branch_name,
                committed=False,
                pushed=False,
                error=self._redact(str(exc)),
            )

        try:
            commit_sha = self.commit_changes(workspace_path, commit_message, files)
            committed = True
        except git.GitCommandError as exc:
            error = self._redact(str(exc))
            logger.warning("Git commit failed for branch %s: %s", branch_name, error)
            return GitResult(
                branch=branch_name,
                committed=False,
                pushed=False,
                files_committed=[],
                error=error,
            )

        try:
            self.push_branch(workspace_path, github_url, pat, branch_name)
            pushed = True
        except git.GitCommandError as exc:
            error = self._redact(str(exc))
            logger.warning("Git push failed for branch %s: %s", branch_name, error)

        return GitResult(
            branch=branch_name,
            committed=committed,
            commit_sha=commit_sha,
            pushed=pushed,
            files_committed=list(files) if committed else [],
            error=error,
        )

    def create_branch(self, workspace_path: str, branch_name: str) -> None:
        """Create and check out a new feature branch in the workspace."""
        repo = git.Repo(workspace_path)
        repo.git.checkout("-b", branch_name)
        logger.info("Created branch %s", branch_name)

    def commit_changes(
        self, workspace_path: str, message: str, files: list[str]
    ) -> str:
        """Stage ``files`` and commit; returns the commit SHA."""
        repo = git.Repo(workspace_path)
        actor = git.Actor(_BOT_NAME, _BOT_EMAIL)
        repo.index.add(files)
        commit = repo.index.commit(message, author=actor, committer=actor)
        logger.info("Committed %d file(s) as %s", len(files), commit.hexsha[:8])
        return commit.hexsha

    def push_branch(
        self,
        workspace_path: str,
        github_url: str,
        pat: str | None,
        branch_name: str,
    ) -> None:
        """Push ``branch_name`` to the authenticated remote (fast-forward only)."""
        auth_url = self._authenticated_url(github_url, pat)
        repo = git.Repo(workspace_path)
        repo.git.push(auth_url, f"{branch_name}:{branch_name}")
        logger.info("Pushed branch %s to remote", branch_name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _authenticated_url(github_url: str, pat: str | None) -> str:
        """Inject the PAT into an HTTPS remote URL.

        Mirrors ``WorkspaceManager._authenticated_url`` — uses the
        ``x-access-token:{pat}@host`` form so private repos can be pushed.
        """
        parsed = urlparse(github_url.rstrip("/"))
        path = parsed.path.rstrip("/")
        if not path.endswith(".git"):
            path += ".git"
        if pat:
            return f"https://x-access-token:{pat}@{parsed.netloc}{path}"
        return f"https://{parsed.netloc}{path}"

    @staticmethod
    def _redact(text: str) -> str:
        """Strip any PAT embedded in an error message before it is logged/stored."""
        return _PAT_RE.sub("x-access-token:[REDACTED]@", text)


git_service = GitService()
