from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories import file_repo, ingestion_repo, issue_repo, repository_repo
from app.schemas.repository import (
    FileListOut,
    IngestionRunOut,
    IngestionTriggeredOut,
    IssueListOut,
    RepositoryCreate,
    RepositoryCreatedOut,
    RepositoryOut,
    RepositoryStats,
)
import app.services.repository_service as repository_service
from app.services.ingestion_service import ingestion_service as _ingestion_service
from forge_github.client import GitHubClient
from app.config import settings

router = APIRouter(prefix="/repositories", tags=["repositories"])


async def _build_repository_out(db: AsyncSession, repo) -> RepositoryOut:
    latest = await ingestion_repo.get_latest_for_repo(db, repo.id)
    total_files, _ = await file_repo.list_for_repo(db, repo.id, limit=0)
    total_chunks = await file_repo.count_chunks_for_repo(db, repo.id)
    open_issues = await issue_repo.count_open_for_repo(db, repo.id)
    return RepositoryOut(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        description=repo.description,
        github_url=repo.github_url,
        default_branch=repo.default_branch,
        created_at=repo.created_at,
        stats=RepositoryStats(
            total_files=total_files,
            total_chunks=total_chunks,
            open_issues=open_issues,
        ),
        latest_ingestion=IngestionRunOut.model_validate(latest) if latest else None,
    )


@router.post("", status_code=202, response_model=RepositoryCreatedOut)
async def register_repository(
    body: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
) -> RepositoryCreatedOut:
    owner, name = body.parse_owner_name()

    gh = GitHubClient(settings.github_token)
    try:
        gh_repo = await gh.get_repository(owner, name)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not fetch repository from GitHub: {exc}")

    repo = await repository_service.get_or_create_repository(db, gh_repo, body.github_pat)
    run = await ingestion_repo.create(db, repo.id)

    asyncio.create_task(
        _ingestion_service.start(repo.id, run.id, owner, name)
    )

    return RepositoryCreatedOut(
        repository_id=repo.id,
        ingestion_run_id=run.id,
        status="pending",
    )


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(db: AsyncSession = Depends(get_db)) -> list[RepositoryOut]:
    repos = await repository_service.list_repositories(db)
    return [await _build_repository_out(db, r) for r in repos]


@router.get("/{repository_id}", response_model=RepositoryOut)
async def get_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RepositoryOut:
    repo = await repository_service.get_repository(db, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return await _build_repository_out(db, repo)


@router.get("/{repository_id}/files", response_model=FileListOut)
async def list_files(
    repository_id: uuid.UUID,
    language: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> FileListOut:
    repo = await repository_service.get_repository(db, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    total, files = await file_repo.list_for_repo(db, repository_id, language, limit, offset)
    return FileListOut(total=total, files=files)  # type: ignore[arg-type]


@router.get("/{repository_id}/ingestion", response_model=IngestionRunOut)
async def get_ingestion_status(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> IngestionRunOut:
    repo = await repository_service.get_repository(db, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    run = await ingestion_repo.get_latest_for_repo(db, repository_id)
    if not run:
        raise HTTPException(status_code=404, detail="No ingestion run found")
    return IngestionRunOut.model_validate(run)


@router.get("/{repository_id}/issues", response_model=IssueListOut)
async def list_issues(
    repository_id: uuid.UUID,
    state: str = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> IssueListOut:
    repo = await repository_service.get_repository(db, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    total, issues = await issue_repo.list_for_repo(db, repository_id, state, limit, offset)
    return IssueListOut(total=total, issues=issues)  # type: ignore[arg-type]


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = await repository_service.get_repository(db, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Remove Qdrant collection — ignore if it never got created
    try:
        from forge_vector_store.store import VectorStore
        vs = VectorStore(settings.qdrant_url, settings.qdrant_api_key or None)
        await vs.delete_collection(f"repo_{repository_id}")
    except Exception:
        pass

    await repository_repo.delete_by_id(db, repository_id)


@router.post("/{repository_id}/ingest", status_code=202, response_model=IngestionTriggeredOut)
async def retrigger_ingestion(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> IngestionTriggeredOut:
    repo = await repository_service.get_repository(db, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    run = await ingestion_repo.create(db, repository_id)
    asyncio.create_task(
        _ingestion_service.start(repository_id, run.id, repo.owner, repo.name)
    )
    return IngestionTriggeredOut(ingestion_run_id=run.id, status="pending")
