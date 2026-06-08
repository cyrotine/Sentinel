from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CodeEmbedder:
    def __init__(self, api_key: str, model: str = "models/text-embedding-004") -> None:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self._embeddings = GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key)
        self._vector_size: int | None = None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = await self._embeddings.aembed_documents(texts)
        if self._vector_size is None and result:
            self._vector_size = len(result[0])
            logger.info("Detected embedding vector size: %d", self._vector_size)
        return result

    async def vector_size(self) -> int:
        """Returns the actual output dimension by embedding a probe string."""
        if self._vector_size is None:
            probe = await self._embeddings.aembed_documents(["probe"])
            self._vector_size = len(probe[0])
            logger.info("Detected embedding vector size: %d", self._vector_size)
        return self._vector_size
