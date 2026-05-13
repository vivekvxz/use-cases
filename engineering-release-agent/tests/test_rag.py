"""Tests for RAG pipeline and vector store."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.rag.pipeline import RAGPipeline
from src.rag.store import VectorStore


class TestVectorStore:
    """Tests for VectorStore."""

    @patch("src.rag.store.chromadb.PersistentClient")
    def test_upsert_chunks(self, mock_client):
        """upsert() stores chunks and embeddings."""
        # Mock the ChromaDB client
        mock_collection = MagicMock()
        mock_client.return_value.get_or_create_collection.return_value = mock_collection

        store = VectorStore()

        # Test upsert
        count = store.upsert(
            chunks=["chunk1", "chunk2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            metadatas=[
                {"source": "test1", "chunk_index": 0},
                {"source": "test2", "chunk_index": 0},
            ],
        )

        assert count == 2

    @patch("src.rag.store.chromadb.PersistentClient")
    def test_query_returns_results(self, mock_client):
        """query() retrieves results by similarity."""
        # Mock the ChromaDB client
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"source": "test"}]],
            "distances": [[0.1]],
        }
        mock_client.return_value.get_or_create_collection.return_value = mock_collection

        store = VectorStore()

        results = store.query(embedding=[0.1, 0.2])
        assert isinstance(results, list)

    @patch("src.rag.store.chromadb.PersistentClient")
    def test_delete_collection(self, mock_client):
        """delete_collection() removes a collection."""
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance

        store = VectorStore()
        store.delete_collection()

        # Should call delete_collection on client
        assert mock_client_instance.delete_collection.called


class TestRAGPipeline:
    """Tests for RAGPipeline."""

    def test_pipeline_initializes(self):
        """RAGPipeline initializes successfully."""
        pipeline = RAGPipeline()
        assert pipeline is not None

    def test_clear_collection(self):
        """clear_collection() clears the vector store."""
        pipeline = RAGPipeline()
        # Should not raise error
        pipeline.clear_collection()
