"""Tests for ingestion pipeline."""

from __future__ import annotations

from types import SimpleNamespace

import tiktoken
from github import GithubException

from src.ingestion.chunker import DiffChunker
from src.ingestion.git_parser import GitDiffParser

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


class TestGitDiffParserFallback:
    """Tests for GitHub compare fallback behavior."""

    def test_build_diff_from_pull_files(self):
        """Fallback builds unified diff from pull file patches."""
        file1 = SimpleNamespace(
            filename="src/app.py",
            status="modified",
            patch="@@ -1 +1 @@\n-print('old')\n+print('new')",
        )
        file2 = SimpleNamespace(
            filename="assets/logo.png",
            status="modified",
            patch=None,
        )
        pull = SimpleNamespace(get_files=lambda: [file1, file2])
        repo = SimpleNamespace(get_pull=lambda _pr: pull)

        diff = GitDiffParser._build_diff_from_pull_files(repo, 1)
        assert "diff --git a/src/app.py b/src/app.py" in diff
        assert "+print('new')" in diff
        assert "Binary files a/assets/logo.png and b/assets/logo.png differ" in diff

    async def test_fetch_diff_fallbacks_on_compare_404(self):
        """fetch_diff uses pull-files fallback when compare endpoint returns 404."""

        class DummyEncoder:
            def encode(self, text: str) -> list[int]:
                return [0] * len(text)

        parser = object.__new__(GitDiffParser)
        parser.MAX_TOKENS = 100_000
        parser._encoder = DummyEncoder()

        file1 = SimpleNamespace(
            filename="src/app.py",
            status="modified",
            patch="@@ -1 +1 @@\n-print('old')\n+print('new')",
        )
        pull = SimpleNamespace(get_files=lambda: [file1])

        class RepoStub:
            def compare(self, _base, _head):
                raise GithubException(404, {"message": "Not Found"}, None)

            def get_pull(self, _pr):
                return pull

        parser._gh = SimpleNamespace(get_repo=lambda _name: RepoStub())

        diff = await parser.fetch_diff("vivekvxz/use-cases", "abc1234", "def5678", 1)
        assert "diff --git a/src/app.py b/src/app.py" in diff
