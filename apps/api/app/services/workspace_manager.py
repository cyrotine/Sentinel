from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse

import git

from app.config import settings

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Clones a repository to an isolated, per-run workspace on the API host.

    The LangGraph pipeline operates on real files read from disk; this service
    owns the clone/path-resolution/cleanup lifecycle. Workspaces are keyed by
    the agent run id so they never collide across runs (or with ingestion
    clones, which are keyed by repository id under the same base directory).
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    def workspace_path(self, run_id: str) -> Path:
        return self._base_dir / run_id

    async def clone(self, run_id: str, github_url: str, pat: str | None) -> str:
        """Clone the repo into an isolated workspace. Returns the workspace path."""
        workspace = self.workspace_path(run_id)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

        clone_url = self._authenticated_url(github_url, pat)
        logger.info("Cloning %s into workspace %s", github_url, workspace)
        # GitPython is synchronous — run in a thread to avoid blocking the loop.
        await asyncio.to_thread(
            git.Repo.clone_from, clone_url, str(workspace), depth=1
        )
        return str(workspace)

    def cleanup(self, run_id: str) -> None:
        shutil.rmtree(self.workspace_path(run_id), ignore_errors=True)

    @staticmethod
    def _authenticated_url(github_url: str, pat: str | None) -> str:
        """Inject the PAT into an HTTPS clone URL.

        Mirrors ``IngestionService._clone_url`` — uses the
        ``x-access-token:{pat}@host`` form so private repos can be cloned.
        """
        parsed = urlparse(github_url.rstrip("/"))
        path = parsed.path.rstrip("/")
        if not path.endswith(".git"):
            path += ".git"
        if pat:
            return f"https://x-access-token:{pat}@{parsed.netloc}{path}"
        return f"https://{parsed.netloc}{path}"


workspace_manager = WorkspaceManager(settings.clone_base_dir)
