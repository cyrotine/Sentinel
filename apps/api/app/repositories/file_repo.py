from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository_file import RepositoryFile

if TYPE_CHECKING:
    from forge_repository_analysis.analyzer import FileNode


# 5 columns per row — stay well under PostgreSQL's 32767 bind parameter limit
_UPSERT_BATCH_SIZE = 500


async def upsert_files(
    session: AsyncSession,
    repository_id: uuid.UUID,
    files: list[FileNode],
) -> int:
    if not files:
        return 0
    rows = [
        {
            "repository_id": repository_id,
            "path": f.path,
            "language": f.language,
            "size_bytes": f.size,
            "chunk_count": len(f.chunks),
        }
        for f in files
    ]
    for i in range(0, len(rows), _UPSERT_BATCH_SIZE):
        batch = rows[i : i + _UPSERT_BATCH_SIZE]
        stmt = insert(RepositoryFile).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_repository_file_path",
            set_={
                "language": stmt.excluded.language,
                "size_bytes": stmt.excluded.size_bytes,
                "chunk_count": stmt.excluded.chunk_count,
            },
        )
        await session.execute(stmt)
    await session.commit()
    return len(rows)


async def list_for_repo(
    session: AsyncSession,
    repository_id: uuid.UUID,
    language: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[RepositoryFile]]:
    base = select(RepositoryFile).where(RepositoryFile.repository_id == repository_id)
    if language:
        base = base.where(RepositoryFile.language == language)

    count_result = await session.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_result.scalar_one()

    result = await session.execute(
        base.order_by(RepositoryFile.path).limit(limit).offset(offset)
    )
    return total, list(result.scalars().all())


async def count_chunks_for_repo(session: AsyncSession, repository_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(RepositoryFile.chunk_count), 0)).where(
            RepositoryFile.repository_id == repository_id
        )
    )
    return int(result.scalar_one())
