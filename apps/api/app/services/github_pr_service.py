"""GitHub Pull Request service for Sentinel Brain.

Opens a real pull request on GitHub from the branch pushed by ``GitService``,
using the user's PAT. This is the final "Act" step of the critical path
(clone → patch → commit+push → open PR).

Design (mirrors ``git_service.py``):
    - Thin async wrapper around :class:`forge_github.client.GitHubClient`.
    - No database, no LLM, no filesystem access.
    - The PAT is supplied by the caller (``BrainService``) and is never logged.
    - Instantiated once as a module-level singleton: ``github_pr_service``.

This service runs *after* the LangGraph pipeline completes so the PAT never
enters ``SentinelState`` (which is streamed and partially persisted).
"""

from __future__ import annotations

import logging

from forge_github.client import GitHubClient

logger = logging.getLogger(__name__)


class GitHubPRService:
    """Creates a real GitHub pull request via the REST API.

    Pure async service — no database, no LLM, no filesystem.
    """

    async def create_pull_request(
        self,
        *,
        full_name: str,
        pat: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> tuple[str, int]:
        """Open a pull request and return ``(html_url, number)``.

        Args:
            full_name: Repository identifier in ``owner/name`` form.
            pat: Personal Access Token with ``repo`` scope for write access.
            title: Pull request title.
            body: Markdown pull request body.
            head: The branch to merge from — the name actually pushed to the
                remote (``GitResult.branch``), not the draft's slug.
            base: The target branch to merge into (e.g. ``main``).

        Returns:
            A ``(html_url, number)`` tuple from the GitHub API response.

        Raises:
            ValueError: If ``full_name`` is not in ``owner/name`` form.
            httpx.HTTPStatusError: On a non-2xx GitHub API response. Callers
                are responsible for isolating these failures.
        """
        owner, _, name = full_name.partition("/")
        if not owner or not name:
            raise ValueError(f"full_name must be 'owner/name', got {full_name!r}")

        gh = GitHubClient(pat)
        html_url, number = await gh.create_pull_request(
            owner,
            name,
            title=title,
            body=body,
            head=head,
            base=base,
        )
        logger.info("Opened PR #%d for %s (%s → %s)", number, full_name, head, base)
        return html_url, number


github_pr_service = GitHubPRService()
