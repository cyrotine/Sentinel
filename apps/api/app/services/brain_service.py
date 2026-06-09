from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.database import AsyncSessionLocal
from app.repositories import agent_run_repo, file_repo, issue_repo, repository_repo
from forge_repository_analysis.embedder import CodeEmbedder
from forge_vector_store.store import VectorStore
from forge_workflows.graph import build_graph
from forge_workflows.state import BrainInputs, SentinelState

logger = logging.getLogger(__name__)

# Upper bound on LangGraph node executions. The developer↔validator/reviewer
# feedback loops are bounded by ``max_iterations`` via the iteration counter;
# this is a hard backstop against any unexpected cycle.
_RECURSION_LIMIT = 50

# Final-state fields persisted into AgentRun.result.
_RESULT_FIELDS = (
    "selected_issue",
    "plan",
    "code_changes",
    "review",
    "pull_request_draft",
)


def _dump(value: Any) -> Any:
    """Serialize a Pydantic model (or list of them) to JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, list):
        return [_dump(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _status_str(status: Any, fallback: str) -> str:
    """Coerce a SentinelStatus enum (or str) to its string value."""
    if status is None:
        return fallback
    return getattr(status, "value", status)


class BrainService:
    """Owns the boundary between the FastAPI app and the LangGraph pipeline.

    Pre-loads all repository data from Postgres, constructs the pipeline
    dependencies once, and streams the graph while persisting progress to the
    ``agent_runs`` table. The graph itself never touches the database.
    """

    async def start(self, run_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as session:
            try:
                run = await agent_run_repo.get_by_id(session, run_id)
                if run is None:
                    logger.error("AgentRun %s not found — aborting", run_id)
                    return

                repository_id = run.repository_id
                target_issue_id = run.target_issue_id

                await agent_run_repo.update_status(
                    session,
                    run_id,
                    "running",
                    started_at=datetime.now(timezone.utc),
                )

                inputs = await self._load_inputs(session, repository_id)

                graph = build_graph(
                    llm=self._build_llm(),
                    embedder=CodeEmbedder(settings.google_api_key, settings.embedding_model),
                    vector_store=VectorStore(settings.qdrant_url, settings.qdrant_api_key or None),
                ).compile()

                state = SentinelState(
                    repository_id=str(repository_id),
                    target_issue_id=str(target_issue_id) if target_issue_id else None,
                    agent_run_id=str(run_id),
                    inputs=inputs,
                )

                accumulator: dict[str, Any] = {}

                async for chunk in graph.astream(
                    state,
                    {"recursion_limit": _RECURSION_LIMIT},
                    stream_mode="updates",
                ):
                    for node_name, partial in chunk.items():
                        if not isinstance(partial, dict):
                            continue
                        accumulator.update(partial)
                        await agent_run_repo.update_status(
                            session,
                            run_id,
                            _status_str(partial.get("status"), "running"),
                            current_node=node_name,
                        )

                result = {field: _dump(accumulator.get(field)) for field in _RESULT_FIELDS}

                await agent_run_repo.update_status(
                    session,
                    run_id,
                    "completed",
                    current_node=None,
                    result=result,
                    completed_at=datetime.now(timezone.utc),
                )
                logger.info("Agent run %s completed", run_id)

            except Exception as exc:
                logger.exception("Agent run %s failed", run_id)
                async with AsyncSessionLocal() as err_session:
                    await agent_run_repo.update_status(
                        err_session,
                        run_id,
                        "failed",
                        error=str(exc),
                        completed_at=datetime.now(timezone.utc),
                    )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_llm() -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=settings.brain_llm_model,
            google_api_key=settings.google_api_key,
            temperature=0.2,
        )

    @staticmethod
    async def _load_inputs(session: Any, repository_id: uuid.UUID) -> BrainInputs:
        repo = await repository_repo.get_by_id(session, repository_id)
        if repo is None:
            raise ValueError(f"Repository {repository_id} not found")

        total_files, files = await file_repo.list_for_repo(session, repository_id, limit=10000)
        _, issues = await issue_repo.list_for_repo(session, repository_id, state="open", limit=200)

        raw_issues = [
            {
                "issue_id": str(issue.id),
                "number": issue.number,
                "title": issue.title,
                "body": issue.body or "",
                "labels": issue.labels or [],
                "state": issue.state,
            }
            for issue in issues
        ]

        return BrainInputs(
            repo_name=repo.full_name,
            repo_description=repo.description or "",
            file_paths=[f.path for f in files],
            file_languages={f.path: f.language for f in files},
            total_files=total_files,
            raw_issues=raw_issues,
            collection_name=f"repo_{repository_id}",
        )


brain_service = BrainService()