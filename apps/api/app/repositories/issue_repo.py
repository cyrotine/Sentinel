from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue import Issue

if TYPE_CHECKING:
    from forge_github.client import Issue as GitHubIssue


# 7 columns per row — stay well under PostgreSQL's 32767 bind parameter limit
_UPSERT_BATCH_SIZE = 500


async def upsert_issues(
    session: AsyncSession,
    repository_id: uuid.UUID,
    issues: list[GitHubIssue],
) -> int:
    if not issues:
        return 0
    rows = [
        {
            "repository_id": repository_id,
            "github_issue_id": issue.github_issue_id,
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "labels": issue.labels,
        }
        for issue in issues
    ]
    for i in range(0, len(rows), _UPSERT_BATCH_SIZE):
        batch = rows[i : i + _UPSERT_BATCH_SIZE]
        stmt = insert(Issue).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_issues_github_issue_id",
            set_={
                "title": stmt.excluded.title,
                "body": stmt.excluded.body,
                "state": stmt.excluded.state,
                "labels": stmt.excluded.labels,
            },
        )
        await session.execute(stmt)
    await session.commit()
    return len(rows)


async def list_for_repo(
    session: AsyncSession,
    repository_id: uuid.UUID,
    state: str = "open",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Issue]]:
    base = select(Issue).where(Issue.repository_id == repository_id, Issue.state == state)

    count_result = await session.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_result.scalar_one()

    result = await session.execute(
        base.order_by(Issue.number.asc()).limit(limit).offset(offset)
    )
    return total, list(result.scalars().all())


async def count_open_for_repo(session: AsyncSession, repository_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).where(
            Issue.repository_id == repository_id, Issue.state == "open"
        )
    )
    return int(result.scalar_one())
