import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient
from sqlalchemy import text

from app.api.health import router as health_router
from app.config import settings
from app.database import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("PostgreSQL connected")

    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        client.get_collections()
        logger.info("Qdrant connected")
    except Exception as exc:
        logger.error("Qdrant connection failed: %s", exc)
        raise

    # Reset any runs that were left in a non-terminal state from a previous crash
    from app.database import AsyncSessionLocal
    from app.repositories import agent_run_repo, ingestion_repo

    async with AsyncSessionLocal() as session:
        await ingestion_repo.reset_stuck_runs(session)
        await agent_run_repo.reset_stuck_runs(session)

    yield

    await engine.dispose()


app = FastAPI(
    title="Forge API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")

from app.api.repositories import router as repositories_router  # noqa: E402

app.include_router(repositories_router, prefix="/api")

from app.api.agent_runs import router as agent_runs_router  # noqa: E402

app.include_router(agent_runs_router, prefix="/api")

# Trigger reload
