from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.ingestion_run import IngestionRun
    from app.models.issue import Issue
    from app.models.repository_file import RepositoryFile


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    owner: Mapped[str]
    name: Mapped[str]
    full_name: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(default="main")
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        "IngestionRun", back_populates="repository", cascade="all, delete-orphan"
    )
    files: Mapped[list[RepositoryFile]] = relationship(
        "RepositoryFile", back_populates="repository", cascade="all, delete-orphan"
    )
    issues: Mapped[list[Issue]] = relationship(
        "Issue", back_populates="repository", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        "AgentRun", back_populates="repository", cascade="all, delete-orphan"
    )
