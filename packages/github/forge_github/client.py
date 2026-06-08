from __future__ import annotations

from pydantic import BaseModel


class Repository(BaseModel):
    id: str
    owner: str
    name: str
    full_name: str
    description: str | None = None
    default_branch: str = "main"


class Issue(BaseModel):
    id: str
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[str] = []


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._token = token

    async def get_repository(self, owner: str, name: str) -> Repository:
        raise NotImplementedError

    async def get_issues(self, owner: str, name: str) -> list[Issue]:
        raise NotImplementedError

    async def create_pull_request(
        self,
        owner: str,
        name: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> str:
        raise NotImplementedError
