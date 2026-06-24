from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, name) from a GitHub repo URL."""
    parsed = urlparse(url.strip().rstrip("/"))
    if parsed.hostname not in ("github.com", "www.github.com"):
        raise ValueError("URL must be a github.com repository URL")
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) < 2:
        raise ValueError("URL must include owner and repository name")
    return parts[0], parts[1]


class RepositoryCreate(BaseModel):
    github_url: str
    github_pat: str | None = Field(default=None, exclude=True)

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        _parse_github_url(v)
        return v

    def parse_owner_name(self) -> tuple[str, str]:
        return _parse_github_url(self.github_url)


class RepositoryCreatedOut(BaseModel):
    repository_id: uuid.UUID
    ingestion_run_id: uuid.UUID
    status: str


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    total_files: int | None
    processed_files: int
    error: str | None
    warning: str | None
    started_at: datetime | None
    completed_at: datetime | None


class RepositoryStats(BaseModel):
    total_files: int
    total_chunks: int
    open_issues: int


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner: str
    name: str
    full_name: str
    description: str | None
    github_url: str
    default_branch: str
    created_at: datetime
    stats: RepositoryStats
    latest_ingestion: IngestionRunOut | None


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
    language: str | None
    size_bytes: int
    chunk_count: int


class FileListOut(BaseModel):
    total: int
    files: list[FileOut]


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    title: str
    body: str | None
    state: str
    labels: list[str]


class IssueListOut(BaseModel):
    total: int
    issues: list[IssueOut]


class IngestionTriggeredOut(BaseModel):
    ingestion_run_id: uuid.UUID
    status: str
