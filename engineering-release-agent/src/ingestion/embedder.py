"""Embedder for text using OpenAI or Ollama."""

from __future__ import annotations

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings

logger = structlog.get_logger(__name__)


class Embedder:
    """Embed text using OpenAI or Ollama."""

    def __init__(self) -> None:
        """Initialize embedder with configured LLM backend."""
        settings = get_settings()
        if settings.use_ollama:
            from langchain_community.embeddings import OllamaEmbeddings

            self._embeddings = OllamaEmbeddings(
                model="nomic-embed-text",
                base_url=settings.ollama_base_url,
            )
            self.BATCH_SIZE = 50
        else:
            from langchain_openai import OpenAIEmbeddings

            self._embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=settings.openai_api_key,
            )
            self.BATCH_SIZE = 100

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8)
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts in batches.

        Args:
            texts: List of strings to embed

        Returns:
            List of float vectors
        """
        all_embeddings = []
        total_batches = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        for batch_num, i in enumerate(range(0, len(texts), self.BATCH_SIZE)):
            batch = texts[i : i + self.BATCH_SIZE]
            logger.info(
                "embedding_batch",
                batch_num=batch_num + 1,
                total_batches=total_batches,
                batch_size=len(batch),
            )
            embeddings = await self._embeddings.aembed_documents(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single string for query-time retrieval.

        Args:
            text: String to embed

        Returns:
            Float vector
        """
        return await self._embeddings.aembed_query(text)
