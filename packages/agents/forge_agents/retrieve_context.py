"""Retrieve Context agent for Sentinel Brain.

Performs semantic search against the Qdrant vector store to find code chunks
relevant to the selected issue. This is a **deterministic retrieval agent**,
not an LLM-powered agent.

Design:
    - The agent receives a search query (built from the selected issue)
      and uses the ``CodeEmbedder`` to produce an embedding vector.
    - The vector is passed to ``VectorStore.search()`` to find the top-k
      most similar code chunks.
    - Results are converted to :class:`RetrievedChunk` models for downstream
      consumption by the Planner and Developer agents.
    - The agent does NOT access databases, GitHub, or the filesystem.
    - It operates entirely through the existing ``forge_vector_store`` and
      ``forge_repository_analysis`` abstraction layers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from forge_workflows.state import RetrievedChunk

if TYPE_CHECKING:
    from forge_repository_analysis.embedder import CodeEmbedder
    from forge_vector_store.store import VectorStore

logger = logging.getLogger(__name__)


class RetrieveContextAgent:
    """Retrieves relevant code chunks from Qdrant via semantic search.

    This is a deterministic retrieval agent — no LLM is involved.

    Args:
        embedder: A :class:`CodeEmbedder` instance for query embedding.
        vector_store: A :class:`VectorStore` instance for Qdrant search.
    """

    name: str = "retrieve_context"

    def __init__(
        self,
        embedder: CodeEmbedder,
        vector_store: VectorStore,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    async def retrieve(
        self,
        *,
        collection: str,
        query: str,
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        """Search for code chunks relevant to the given query.

        Args:
            collection: Qdrant collection name (e.g. ``repo_{uuid}``).
            query: The search query text (typically issue title + body).
            limit: Maximum number of chunks to return.

        Returns:
            A list of :class:`RetrievedChunk`, ordered by relevance (highest
            similarity first).
        """
        if not query.strip():
            logger.warning("Empty search query — returning no chunks")
            return []

        logger.info(
            "Embedding query and searching collection=%s  limit=%d",
            collection,
            limit,
        )
        logger.debug("Search query: %s", query[:200])

        # Embed the search query
        try:
            vectors = await self._embedder.embed_batch([query])
            if not vectors or not vectors[0]:
                logger.warning("Embedder returned empty vector — returning no chunks")
                return []
            query_vector = vectors[0]
        except Exception:
            logger.exception("Failed to embed search query")
            return []

        # Search Qdrant
        try:
            results = await self._vector_store.search(
                collection=collection,
                query=query_vector,
                limit=limit,
            )
        except Exception:
            logger.exception("Qdrant search failed for collection %s", collection)
            return []

        if not results:
            logger.info("No results returned from Qdrant for collection %s", collection)
            return []

        # Convert SearchResult → RetrievedChunk
        chunks: list[RetrievedChunk] = []
        for r in results:
            payload = r.payload
            try:
                chunk = RetrievedChunk(
                    file_path=str(payload.get("file_path", "")),
                    content=str(payload.get("content", "")),
                    start_line=int(payload.get("start_line", 0)),
                    end_line=int(payload.get("end_line", 0)),
                    language=str(payload.get("language", "")),
                    score=r.score,
                )
                chunks.append(chunk)
            except Exception:
                logger.warning(
                    "Failed to convert search result id=%s to RetrievedChunk",
                    r.id,
                )

        logger.info(
            "Retrieved %d chunks from %s (query: %s...)",
            len(chunks),
            collection,
            query[:60],
        )

        return chunks
