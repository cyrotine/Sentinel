from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class Vector(BaseModel):
    id: str
    payload: dict[str, object]
    vector: list[float]


class SearchResult(BaseModel):
    id: str
    score: float
    payload: dict[str, object]


class VectorStore:
    def __init__(self, url: str, api_key: str | None = None) -> None:
        from qdrant_client import AsyncQdrantClient

        self._client = AsyncQdrantClient(url=url, api_key=api_key)

    async def create_collection(self, collection: str, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}
        if collection not in existing:
            await self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", collection)

    async def upsert(self, collection: str, vectors: list[Vector]) -> None:
        from qdrant_client.models import PointStruct

        for i in range(0, len(vectors), BATCH_SIZE):
            batch = vectors[i : i + BATCH_SIZE]
            points = [
                PointStruct(id=v.id, vector=v.vector, payload=v.payload)
                for v in batch
            ]
            await self._client.upsert(collection_name=collection, points=points)

    async def search(
        self,
        collection: str,
        query: list[float],
        limit: int = 10,
    ) -> list[SearchResult]:
        results = await self._client.search(
            collection_name=collection,
            query_vector=query,
            limit=limit,
        )
        return [
            SearchResult(
                id=str(r.id),
                score=r.score,
                payload=r.payload or {},
            )
            for r in results
        ]

    async def delete_collection(self, collection: str) -> None:
        await self._client.delete_collection(collection_name=collection)
        logger.info("Deleted Qdrant collection: %s", collection)
