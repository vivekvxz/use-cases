"""RAG search tool backed by local ChromaDB."""

from __future__ import annotations

import chromadb

from src.config import get_settings
from src.ingestion.embedder import Embedder


class RAGSearchTool:
    """Search the local architecture knowledge base."""

    COLLECTION_NAME = "release_agent_kb"
    MAX_DISTANCE = 1.0

    def __init__(self) -> None:
        """Initialize RAG search tool."""
        settings = get_settings()
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(self.COLLECTION_NAME)
        self._embedder = Embedder()

    async def search(
        self, query: str, top_k: int = 5, doc_type: str | None = None
    ) -> list[dict]:
        """Embed query and retrieve top_k relevant documents from ChromaDB.

        Args:
            query: Search query
            top_k: Number of results
            doc_type: Optional document type filter

        Returns:
            List of dicts with content, metadata, distance
        """
        vector = await self._embedder.embed_single(query)

        kwargs = {
            "query_embeddings": [vector],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if doc_type:
            kwargs["where"] = {"doc_type": {"$eq": doc_type}}

        results = self._collection.query(**kwargs)

        # Zip and filter results
        output = []
        if results and results["documents"]:
            for content, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                if distance <= self.MAX_DISTANCE:
                    output.append(
                        {"content": content, "metadata": metadata, "distance": distance}
                    )

        return sorted(output, key=lambda x: x["distance"])

    def format_for_prompt(self, results: list[dict]) -> str:
        """Format search results into a readable prompt section.

        Args:
            results: Output from search()

        Returns:
            Formatted string for LLM
        """
        if not results:
            return "No relevant architecture context found."

        lines = []
        for result in results:
            source = result["metadata"].get("source", "Unknown")
            lines.append(f"**Source:** {source}")
            lines.append(result["content"][:500])
            lines.append("")

        return "\n".join(lines)
