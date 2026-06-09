from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun

# Statuses that are not terminal — a run left in one of these after a crash is stuck.
_STUCK_STATUSES = ("pending", "running")
_TERMINAL_STATUSES = ("completed", "failed")


async def create(
    session: AsyncSession,
    repository_id: uuid.UUID,
    target_issue_id: uuid.UUID | None = None,
) -> AgentRun:
    run = AgentRun(
        repository_id=repository_id,
        target_issue_id=target_issue_id,
        status="pending",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_by_id(session: AsyncSession, run_id: uuid.UUID) -> AgentRun | None:
    result = await session.execute(select(AgentRun).where(AgentRun.id == run_id))
    return result.scalar_one_or_none()


async def list_for_repo(
    session: AsyncSession,
    repository_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[AgentRun]]:
    base = select(AgentRun)
    if repository_id is not None:
        base = base.where(AgentRun.repository_id == repository_id)

    count_result = await session.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_result.scalar_one()

    result = await session.execute(
        base.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
    )
    return total, list(result.scalars().all())


async def update_status(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    **kwargs: object,
) -> None:
    values: dict[str, object] = {"status": status, **kwargs}
    await session.execute(
        update(AgentRun).where(AgentRun.id == run_id).values(**values)
    )
    await session.commit()


async def reset_stuck_runs(session: AsyncSession) -> None:
    """Called on startup to mark any non-terminal runs as failed."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(AgentRun)
        .where(AgentRun.status.in_(_STUCK_STATUSES))
        .values(status="failed", error="Server restarted during agent run", completed_at=now)
    )
    await session.commit()