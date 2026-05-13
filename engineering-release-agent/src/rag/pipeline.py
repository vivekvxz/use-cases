"""RAG pipeline for ingesting documents into ChromaDB."""

from __future__ import annotations

from pathlib import Path

import structlog

from src.ingestion.chunker import DiffChunker
from src.ingestion.embedder import Embedder
from src.rag.store import VectorStore

logger = structlog.get_logger(__name__)


class RAGPipeline:
    """Ingest documents into local ChromaDB knowledge base."""

    SUPPORTED_EXTENSIONS = {".md", ".txt", ".py", ".rst"}

    def __init__(self) -> None:
        """Initialize RAG pipeline components."""
        self._chunker = DiffChunker()
        self._embedder = Embedder()
        self._store = VectorStore()

    async def ingest_document(
        self,
        content: str,
        doc_type: str,
        source: str,
        metadata: dict | None = None,
    ) -> int:
        """Chunk, embed, and store a document in ChromaDB.

        Args:
            content: Document content
            doc_type: Document type (e.g., "design_doc", "runbook")
            source: Source identifier (e.g., file path)
            metadata: Optional additional metadata

        Returns:
            Number of chunks ingested
        """
        # Chunk content
        chunks = self._chunker.chunk(content, chunk_size=800, overlap=100)
        if not chunks:
            return 0

        # Embed chunks
        embeddings = await self._embedder.embed(chunks)

        # Build metadata
        metadatas = []
        for chunk_idx, chunk in enumerate(chunks):
            chunk_metadata = {
                "doc_type": doc_type,
                "source": source,
                "chunk_index": chunk_idx,
                "total_chunks": len(chunks),
            }
            if metadata:
                chunk_metadata.update(metadata)
            metadatas.append(chunk_metadata)

        # Upsert to store
        count = self._store.upsert(chunks, embeddings, metadatas)
        logger.info(
            "document_ingested", source=source, doc_type=doc_type, chunk_count=count
        )
        return count

    async def ingest_file(self, file_path: str, doc_type: str) -> int:
        """Read a file from disk and ingest it into the knowledge base.

        Args:
            file_path: Path to file
            doc_type: Document type

        Returns:
            Number of chunks ingested
        """
        path = Path(file_path)
        if path.suffix not in self.SUPPORTED_EXTENSIONS:
            return 0

        content = path.read_text(encoding="utf-8")
        return await self.ingest_document(content, doc_type, source=file_path)

    async def ingest_directory(
        self, dir_path: str, doc_type: str = "design_doc"
    ) -> int:
        """Recursively ingest all supported files from a directory.

        Args:
            dir_path: Directory path
            doc_type: Document type for all files

        Returns:
            Total number of chunks ingested
        """
        total_count = 0
        path = Path(dir_path)

        for file_path in path.rglob("*"):
            if file_path.suffix in self.SUPPORTED_EXTENSIONS:
                count = await self.ingest_file(str(file_path), doc_type)
                total_count += count

        logger.info(
            "directory_ingested",
            dir_path=dir_path,
            doc_type=doc_type,
            total_chunks=total_count,
        )
        return total_count

    def clear_collection(self) -> bool:
        """Delete the ChromaDB collection and recreate it empty."""
        self._store.delete_collection()
        return True
