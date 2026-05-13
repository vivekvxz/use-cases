"""Tests for ingestion pipeline."""

from __future__ import annotations

import tiktoken

from src.ingestion.chunker import DiffChunker

SAMPLE_DIFF_2_FILES = """diff --git a/src/api/routes.py b/src/api/routes.py
index 111..222 100644
--- a/src/api/routes.py
+++ b/src/api/routes.py
@@ -10,5 +10,10 @@
+def new_endpoint():
+    return {"ok": True}
diff --git a/src/models.py b/src/models.py
index 333..444 100644
--- a/src/models.py
+++ b/src/models.py
@@ -20,3 +20,5 @@
+    field: str = "default"
-    old_field: str = ""
Binary files a/assets/logo.png and b/assets/logo.png differ
"""


class TestDiffChunker:
    """Tests for DiffChunker."""

    def test_chunk_returns_list_of_strings(self, sample_diff):
        """chunk() returns list[str]."""
        chunker = DiffChunker()
        result = chunker.chunk(sample_diff)
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_chunk_each_under_max_tokens(self, sample_diff):
        """All chunks have token count <= chunk_size."""
        chunker = DiffChunker()
        encoder = tiktoken.get_encoding("cl100k_base")
        chunk_size = 500
        result = chunker.chunk(sample_diff, chunk_size=chunk_size)

        for chunk in result:
            token_count = len(encoder.encode(chunk))
            assert token_count <= chunk_size

    def test_chunk_by_file_adds_metadata(self):
        """Each result has file_path, chunk_index, total_chunks, content."""
        chunker = DiffChunker()
        parsed = [
            {
                "file_path": "test.py",
                "additions": 5,
                "deletions": 0,
                "hunks": ["diff content"],
            }
        ]
        result = chunker.chunk_by_file(parsed)

        assert len(result) > 0
        for item in result:
            assert "file_path" in item
            assert "chunk_index" in item
            assert "total_chunks" in item
            assert "content" in item
            assert "token_count" in item

    def test_chunk_empty_text(self):
        """chunk() on empty text returns empty list."""
        chunker = DiffChunker()
        result = chunker.chunk("")
        assert result == []
