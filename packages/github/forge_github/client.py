from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class Repository(BaseModel):
    id: str
    owner: str
    name: str
    full_name: str
    description: str | None = None
    default_branch: str = "main"
    github_id: int = 0
    clone_url: str = ""
    html_url: str = ""


class Issue(BaseModel):
    id: str
    github_issue_id: int
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[str] = []


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            base_url=_GITHUB_API,
            timeout=30.0,
        )

    async def _get(self, client: httpx.AsyncClient, url: str, **params: object) -> httpx.Response:
        resp = await client.get(url, params=params or None)
        if resp.status_code == 429 or (resp.status_code == 403 and "rate limit" in resp.text.lower()):
            retry_after = int(resp.headers.get("Retry-After", "60"))
            logger.warning("GitHub rate limit hit; retrying after %ds", retry_after)
            await asyncio.sleep(retry_after)
            resp = await client.get(url, params=params or None)
        resp.raise_for_status()
        return resp

    async def get_repository(self, owner: str, name: str) -> Repository:
        async with self._client() as client:
            resp = await self._get(client, f"/repos/{owner}/{name}")
        data = resp.json()
        return Repository(
            id=str(data["id"]),
            github_id=data["id"],
            owner=data["owner"]["login"],
            name=data["name"],
            full_name=data["full_name"],
            description=data.get("description"),
            default_branch=data.get("default_branch", "main"),
            clone_url=data.get("clone_url", ""),
            html_url=data.get("html_url", ""),
        )

    async def get_issues(self, owner: str, name: str) -> list[Issue]:
        issues: list[Issue] = []
        page = 1
        async with self._client() as client:
            while True:
                resp = await self._get(
                    client,
                    f"/repos/{owner}/{name}/issues",
                    state="open",
                    per_page=100,
                    page=page,
                )
                batch = resp.json()
                if not batch:
                    break
                for item in batch:
                    # Skip pull requests (GitHub returns PRs in /issues)
                    if item.get("pull_request"):
                        continue
                    issues.append(
                        Issue(
                            id=str(item["id"]),
                            github_issue_id=item["id"],
                            number=item["number"],
                            title=item["title"],
                            body=item.get("body"),
                            state=item["state"],
                            labels=[label["name"] for label in item.get("labels", [])],
                        )
                    )
                # Check Link header for next page
                link = resp.headers.get("Link", "")
                if 'rel="next"' not in link:
                    break
                page += 1
        return issues

    async def get_file_tree(self, owner: str, name: str, sha: str) -> list[dict[str, object]]:
        async with self._client() as client:
            resp = await self._get(
                client,
                f"/repos/{owner}/{name}/git/trees/{sha}",
                recursive=1,
            )
        data = resp.json()
        return data.get("tree", [])

    async def create_pull_request(
        self,
        owner: str,
        name: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> tuple[str, int]:
        """Open a pull request and return ``(html_url, number)``."""
        async with self._client() as client:
            resp = await client.post(
                f"/repos/{owner}/{name}/pulls",
                json={"title": title, "body": body, "head": head, "base": base},
            )
            resp.raise_for_status()
        data = resp.json()
        return data["html_url"], data["number"]
