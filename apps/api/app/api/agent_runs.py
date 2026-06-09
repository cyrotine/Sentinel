from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories import agent_run_repo, repository_repo
from app.schemas.agent_run import (
    AgentRunCreate,
    AgentRunCreatedOut,
    AgentRunListOut,
    AgentRunOut,
)
from app.services.brain_service import brain_service

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.post("", status_code=202, response_model=AgentRunCreatedOut)
async def create_agent_run(
    body: AgentRunCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentRunCreatedOut:
    repo = await repository_repo.get_by_id(db, body.repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    run = await agent_run_repo.create(db, body.repository_id, body.target_issue_id)

    asyncio.create_task(brain_service.start(run.id))

    return AgentRunCreatedOut(run_id=run.id, status=run.status)


@router.get("", response_model=AgentRunListOut)
async def list_agent_runs(
    repository_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AgentRunListOut:
    total, runs = await agent_run_repo.list_for_repo(db, repository_id, limit, offset)
    return AgentRunListOut(
        total=total,
        runs=[AgentRunOut.model_validate(r) for r in runs],
    )


@router.get("/{run_id}", response_model=AgentRunOut)
async def get_agent_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentRunOut:
    run = await agent_run_repo.get_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return AgentRunOut.model_validate(run)