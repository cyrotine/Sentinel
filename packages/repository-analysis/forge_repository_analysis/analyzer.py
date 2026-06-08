from __future__ import annotations

from pydantic import BaseModel, Field


class FileNode(BaseModel):
    path: str
    language: str | None = None
    size: int = 0


class RepositoryAnalysis(BaseModel):
    repository_id: str
    files: list[FileNode] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    total_files: int = 0
    total_size: int = 0


class RepositoryAnalyzer:
    async def analyze(self, path: str, repository_id: str) -> RepositoryAnalysis:
        raise NotImplementedError
