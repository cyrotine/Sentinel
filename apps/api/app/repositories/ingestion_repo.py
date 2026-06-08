from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion_run import IngestionRun

_STUCK_STATUSES = ("cloning", "analyzing", "embedding", "pending")


async def create(session: AsyncSession, repository_id: uuid.UUID) -> IngestionRun:
    run = IngestionRun(repository_id=repository_id, status="pending")
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_latest_for_repo(
    session: AsyncSession, repository_id: uuid.UUID
) -> IngestionRun | None:
    result = await session.execute(
        select(IngestionRun)
        .where(IngestionRun.repository_id == repository_id)
        .order_by(IngestionRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    **kwargs: object,
) -> None:
    values: dict[str, object] = {"status": status, **kwargs}
    await session.execute(
        update(IngestionRun).where(IngestionRun.id == run_id).values(**values)
    )
    await session.commit()


async def increment_processed(session: AsyncSession, run_id: uuid.UUID, count: int) -> None:
    from sqlalchemy import text

    await session.execute(
        text(
            "UPDATE ingestion_runs SET processed_files = processed_files + :count WHERE id = :id"
        ),
        {"count": count, "id": str(run_id)},
    )
    await session.commit()


async def reset_stuck_runs(session: AsyncSession) -> None:
    """Called on startup to mark any non-terminal runs as failed."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(IngestionRun)
        .where(IngestionRun.status.in_(_STUCK_STATUSES))
        .values(status="failed", error="Server restarted during ingestion", completed_at=now)
    )
    await session.commit()
