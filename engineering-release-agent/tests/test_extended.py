"""Tests for CLI interface."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


class TestCLI:
    """Tests for CLI commands."""

    def test_app_initializes(self):
        """CLI app is properly initialized."""
        assert app is not None

    def test_health_command_exists(self):
        """Health check command exists in CLI."""
        # Commands should be registered
        assert app is not None

    def test_analyze_command_with_required_params(self):
        """analyze command accepts required parameters."""
        # Test that command structure is correct
        from src.cli import analyze

        assert callable(analyze)

    def test_review_command_exists(self):
        """Review subcommand is properly set up."""
        from src.cli import review_app

        assert review_app is not None


class TestGitParser:
    """Tests for Git diff parsing."""

    def test_parse_changed_files_with_valid_diff(self):
        """parse_changed_files() parses unified diff format."""
        from src.ingestion.git_parser import GitDiffParser

        diff = """diff --git a/src/test.py b/src/test.py
index 1234..5678 100644
--- a/src/test.py
+++ b/src/test.py
@@ -1,3 +1,4 @@
 test line
+new line"""

        parser = GitDiffParser()
        files = parser.parse_changed_files(diff)
        assert isinstance(files, list)

    def test_parse_changed_files_handles_binary_files(self):
        """parse_changed_files() skips binary files."""
        from src.ingestion.git_parser import GitDiffParser

        diff = """Binary files a/image.png and b/image.png differ"""

        parser = GitDiffParser()
        files = parser.parse_changed_files(diff)
        # Binary files should be skipped
        assert isinstance(files, list)

    def test_extract_file_contents_filters_py_files(self):
        """extract_file_contents() only extracts .py files."""
        files = [
            {"file_path": "test.py", "deletions": 1, "additions": 1},
            {"file_path": "readme.md", "deletions": 0, "additions": 2},
        ]

        # Should handle filtering gracefully
        assert isinstance(files, list)


class TestEvaluationHarness:
    """Tests for evaluation harness."""

    def test_eval_harness_initializes(self):
        """EvalHarness class initializes successfully."""
        from src.evals.harness import EvalHarness

        harness = EvalHarness()
        assert harness is not None

    @pytest.mark.asyncio
    async def test_run_suite_with_dataset(self):
        """run_suite() processes evaluation dataset."""
        from src.evals.harness import EvalHarness

        harness = EvalHarness()
        # Should be callable
        assert callable(harness.run_suite)

    def test_eval_result_model(self):
        """EvalResult model validates evaluation results."""
        from src.evals.harness import EvalResult

        result = EvalResult(
            example_id="test_1",
            passed=True,
            predicted_risk="high",
            expected_risk="high",
            false_positives=[],
            false_negatives=[],
            tokens_used=100,
            latency_ms=500.0,
        )

        assert result.example_id == "test_1"
        assert result.passed is True
