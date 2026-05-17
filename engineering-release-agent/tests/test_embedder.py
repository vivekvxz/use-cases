"""Tests for embedding runtime behavior."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_embedder_missing_ollama_model_message():
    """Embedder raises actionable error when Ollama embedding model is missing."""
    from src.ingestion.embedder import Embedder

    class FakeEmbeddings:
        async def aembed_documents(self, _batch):
            raise Exception('HTTP code: 404, {"error":"model "nomic-embed-text" not found"}')

    embedder = object.__new__(Embedder)
    embedder.BATCH_SIZE = 10
    embedder._settings = type("SettingsStub", (), {"use_ollama": True, "ollama_embed_model": "nomic-embed-text"})()
    embedder._embeddings = FakeEmbeddings()

    with pytest.raises(RuntimeError, match="ollama pull nomic-embed-text"):
        await embedder.embed(["hello world"])