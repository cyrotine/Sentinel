from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.repositories import ingestion_repo, repository_repo
from app.models.ingestion_run import IngestionRun
from forge_github.client import Repository as GitHubRepository


async def get_or_create_repository(
    session: AsyncSession,
    gh_repo: GitHubRepository,
) -> Repository:
    existing = await repository_repo.get_by_github_id(session, int(gh_repo.github_id))
    if existing:
        return existing
    return await repository_repo.create(
        session,
        github_id=int(gh_repo.github_id),
        owner=gh_repo.owner,
        name=gh_repo.name,
        full_name=gh_repo.full_name,
        description=gh_repo.description,
        default_branch=gh_repo.default_branch,
        github_url=gh_repo.html_url,
    )


async def get_repository(session: AsyncSession, repository_id: uuid.UUID) -> Repository | None:
    return await repository_repo.get_by_id(session, repository_id)


async def list_repositories(session: AsyncSession) -> list[Repository]:
    return await repository_repo.list_all(session)


async def get_latest_ingestion(
    session: AsyncSession, repository_id: uuid.UUID
) -> IngestionRun | None:
    return await ingestion_repo.get_latest_for_repo(session, repository_id)
