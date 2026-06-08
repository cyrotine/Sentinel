from __future__ import annotations

from pydantic import BaseModel


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
        self._url = url
        self._api_key = api_key

    async def upsert(self, collection: str, vectors: list[Vector]) -> None:
        raise NotImplementedError

    async def search(
        self,
        collection: str,
        query: list[float],
        limit: int = 10,
    ) -> list[SearchResult]:
        raise NotImplementedError

    async def create_collection(self, collection: str, vector_size: int) -> None:
        raise NotImplementedError
