from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository


async def get_by_github_id(session: AsyncSession, github_id: int) -> Repository | None:
    result = await session.execute(select(Repository).where(Repository.github_id == github_id))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, repository_id: uuid.UUID) -> Repository | None:
    result = await session.execute(select(Repository).where(Repository.id == repository_id))
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[Repository]:
    result = await session.execute(select(Repository).order_by(Repository.created_at.desc()))
    return list(result.scalars().all())


async def delete_by_id(session: AsyncSession, repository_id: uuid.UUID) -> bool:
    repo = await get_by_id(session, repository_id)
    if not repo:
        return False
    await session.delete(repo)
    await session.commit()
    return True


async def create(
    session: AsyncSession,
    *,
    github_id: int,
    owner: str,
    name: str,
    full_name: str,
    description: str | None,
    default_branch: str,
    github_url: str,
    github_pat: str | None = None,
) -> Repository:
    repo = Repository(
        github_id=github_id,
        owner=owner,
        name=name,
        full_name=full_name,
        description=description,
        default_branch=default_branch,
        github_url=github_url,
        github_pat=github_pat,
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)
    return repo


async def update_pat(
    session: AsyncSession, repository_id: uuid.UUID, github_pat: str | None
) -> None:
    """Refresh the stored PAT for an existing repository.

    No-op when ``github_pat`` is falsy so existing callers that omit a PAT
    never clobber a previously stored token.
    """
    if not github_pat:
        return
    repo = await get_by_id(session, repository_id)
    if repo is not None:
        repo.github_pat = github_pat
        await session.commit()
