"""Vector store wrapper for ChromaDB."""

from __future__ import annotations

import chromadb

from src.config import get_settings


class VectorStore:
    """Persistent ChromaDB vector store."""

    COLLECTION_NAME = "release_agent_kb"
    BATCH_SIZE = 100

    def __init__(self) -> None:
        """Initialize ChromaDB client and collection."""
        settings = get_settings()
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(self.COLLECTION_NAME)

    def upsert(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> int:
        """Upsert text chunks with their embeddings into ChromaDB.

        Args:
            chunks: List of text chunks
            embeddings: List of embedding vectors
            metadatas: List of metadata dicts

        Returns:
            Total count upserted
        """
        # Generate IDs from source and chunk index
        ids = []
        for metadata in metadatas:
            source = (
                metadata.get("source", "unknown").replace("/", "_").replace(" ", "_")
            )
            chunk_idx = metadata.get("chunk_index", 0)
            ids.append(f"{source}_{chunk_idx}")

        # Upsert in batches
        for i in range(0, len(chunks), self.BATCH_SIZE):
            batch_chunks = chunks[i : i + self.BATCH_SIZE]
            batch_embeddings = embeddings[i : i + self.BATCH_SIZE]
            batch_metadatas = metadatas[i : i + self.BATCH_SIZE]
            batch_ids = ids[i : i + self.BATCH_SIZE]

            self._collection.upsert(
                documents=batch_chunks,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )

        return len(chunks)

    def query(
        self, embedding: list[float], n_results: int = 5, where: dict | None = None
    ) -> list[dict]:
        """Retrieve the most relevant chunks by vector similarity.

        Args:
            embedding: Query vector
            n_results: Number of results to return
            where: Optional metadata filter

        Returns:
            List of dicts with content, metadata, distance
        """
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
            where=where,
        )

        # Zip and filter results
        output = []
        if results and results["documents"]:
            for content, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                if distance <= 1.0:  # MAX_DISTANCE
                    output.append(
                        {"content": content, "metadata": metadata, "distance": distance}
                    )

        # Sort by distance ascending
        return sorted(output, key=lambda x: x["distance"])

    def count(self) -> int:
        """Return total number of vectors stored in the collection."""
        return self._collection.count()

    def delete_collection(self) -> None:
        """Delete and recreate the collection."""
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.create_collection(self.COLLECTION_NAME)
