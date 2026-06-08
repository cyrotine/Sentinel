import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from qdrant_client import QdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.health import router as health_router
from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connected")
    except Exception as exc:
        logger.error("PostgreSQL connection failed: %s", exc)
        raise

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

    yield

    await engine.dispose()


app = FastAPI(
    title="Forge API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router, prefix="/api")
