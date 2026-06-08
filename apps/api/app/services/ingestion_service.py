from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import git
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.repositories import file_repo, ingestion_repo, issue_repo
from forge_github.client import GitHubClient
from forge_repository_analysis.analyzer import RepositoryAnalyzer
from forge_repository_analysis.embedder import CodeEmbedder
from forge_vector_store.store import Vector, VectorStore

logger = logging.getLogger(__name__)


def _chunk_id(repository_id: uuid.UUID, file_path: str, chunk_index: int) -> str:
    raw = f"{repository_id}:{file_path}:{chunk_index}"
    digest = hashlib.sha256(raw.encode()).digest()[:16]
    return str(uuid.UUID(bytes=digest))


def _clone_url(owner: str, name: str, token: str) -> str:
    if token:
        return f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    return f"https://github.com/{owner}/{name}.git"


class IngestionService:
    async def start(
        self,
        repository_id: uuid.UUID,
        ingestion_run_id: uuid.UUID,
        owner: str,
        name: str,
    ) -> None:
        clone_path = Path(settings.clone_base_dir) / str(repository_id)

        async with AsyncSessionLocal() as session:
            try:
                await ingestion_repo.update_status(
                    session,
                    ingestion_run_id,
                    "cloning",
                    started_at=datetime.now(timezone.utc),
                )

                gh = GitHubClient(settings.github_token)
                issues = await gh.get_issues(owner, name)

                clone_path.parent.mkdir(parents=True, exist_ok=True)
                if clone_path.exists():
                    shutil.rmtree(clone_path)

                logger.info("Cloning %s/%s", owner, name)
                git.Repo.clone_from(
                    _clone_url(owner, name, settings.github_token),
                    str(clone_path),
                    depth=1,
                )

                await ingestion_repo.update_status(session, ingestion_run_id, "analyzing")

                analyzer = RepositoryAnalyzer()
                analysis = await analyzer.analyze(str(clone_path), str(repository_id))

                await file_repo.upsert_files(session, repository_id, analysis.files)
                await issue_repo.upsert_issues(session, repository_id, issues)

                total = len(analysis.files)
                await ingestion_repo.update_status(
                    session, ingestion_run_id, "embedding", total_files=total
                )

                if settings.google_api_key:
                    await self._embed(session, repository_id, ingestion_run_id, analysis.files)
                else:
                    logger.warning(
                        "OPENAI_API_KEY not set — skipping embedding for repository %s",
                        repository_id,
                    )

                shutil.rmtree(clone_path, ignore_errors=True)

                await ingestion_repo.update_status(
                    session,
                    ingestion_run_id,
                    "completed",
                    completed_at=datetime.now(timezone.utc),
                    processed_files=total,
                )
                logger.info("Ingestion completed for repository %s", repository_id)

            except Exception as exc:
                logger.exception("Ingestion failed for repository %s", repository_id)
                shutil.rmtree(clone_path, ignore_errors=True)
                async with AsyncSessionLocal() as err_session:
                    await ingestion_repo.update_status(
                        err_session,
                        ingestion_run_id,
                        "failed",
                        error=str(exc),
                        completed_at=datetime.now(timezone.utc),
                    )

    async def _embed(
        self,
        session: AsyncSession,
        repository_id: uuid.UUID,
        ingestion_run_id: uuid.UUID,
        files: list,
    ) -> None:

        embedder = CodeEmbedder(settings.google_api_key, settings.embedding_model)
        vector_store = VectorStore(settings.qdrant_url, settings.qdrant_api_key or None)
        collection = f"repo_{repository_id}"

        # Delete stale collection so a model change never causes a dim mismatch
        try:
            await vector_store.delete_collection(collection)
        except Exception:
            pass

        actual_size = await embedder.vector_size()
        await vector_store.create_collection(collection, vector_size=actual_size)

        processed = 0
        batch_texts: list[str] = []
        batch_meta: list[dict[str, object]] = []
        batch_ids: list[str] = []

        async def _flush() -> None:
            nonlocal processed
            if not batch_texts:
                return
            vectors_data = await embedder.embed_batch(batch_texts)
            vectors = [
                Vector(id=bid, vector=vec, payload=meta)
                for bid, vec, meta in zip(batch_ids, vectors_data, batch_meta)
            ]
            await vector_store.upsert(collection, vectors)
            processed += len(vectors)
            await ingestion_repo.update_status(
                session, ingestion_run_id, "embedding", processed_files=processed
            )
            batch_texts.clear()
            batch_meta.clear()
            batch_ids.clear()

        for file_node in files:
            if not file_node.chunks:
                continue
            for chunk in file_node.chunks:
                content = str(chunk.get("content", ""))
                if not content.strip():
                    continue
                chunk_index = int(chunk.get("chunk_index", 0))
                batch_texts.append(content)
                batch_ids.append(_chunk_id(repository_id, file_node.path, chunk_index))
                batch_meta.append({
                    "repository_id": str(repository_id),
                    "file_path": file_node.path,
                    "language": file_node.language or "",
                    "chunk_index": chunk_index,
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0),
                    "content": content,
                })
                if len(batch_texts) >= 100:
                    await _flush()

        await _flush()


ingestion_service = IngestionService()
