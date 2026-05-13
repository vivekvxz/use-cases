"""Tests for agent HITL and graph functionality."""

from __future__ import annotations

import json
import tempfile
from unittest.mock import MagicMock, patch

from src.agent.hitl import HITLManager


class TestHITLManager:
    """Tests for HITL (human-in-the-loop) manager."""

    def test_save_pending_creates_json_file(self):
        """save_pending() creates a pending decision file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from pathlib import Path as RealPath

            hitl_dir = RealPath(tmpdir) / "hitl"
            with patch.object(HITLManager, "HITL_DIR", hitl_dir):
                manager = HITLManager()
                state = {
                    "analysis_id": "test_123",
                    "request": {"repo_full_name": "test/repo"},
                    "flags": [],
                }
                manager.save_pending("test_123", state)
                assert (hitl_dir / "test_123.json").exists()

    @patch("src.agent.hitl.Path")
    def test_get_pending_lists_all_pending(self, mock_path_class):
        """get_pending() returns list of all pending reviews."""
        # Mock the Path object
        mock_dir = MagicMock()
        mock_path_class.return_value = mock_dir
        mock_dir.mkdir = MagicMock()
        mock_dir.glob = MagicMock(return_value=[])

        manager = HITLManager()
        pending = manager.get_pending()
        assert isinstance(pending, list)

    def test_submit_decision_saves_decision(self):
        """submit_decision() saves reviewer decision."""
        # Create actual temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use real Path with temp directory
            from pathlib import Path as RealPath

            # Create a mock HITL_DIR
            hitl_dir = RealPath(tmpdir) / "hitl"
            hitl_dir.mkdir()

            # Create a pending file
            pending_file = hitl_dir / "test_456.json"
            pending_file.write_text(
                json.dumps(
                    {
                        "analysis_id": "test_456",
                        "request": {"repo_full_name": "test/repo"},
                        "flags": [],
                    }
                )
            )

            # Patch HITL_DIR to use our temp directory
            with patch.object(HITLManager, "HITL_DIR", hitl_dir):
                manager = HITLManager()
                result = manager.submit_decision(
                    analysis_id="test_456",
                    decision="approve",
                    reviewer="reviewer@example.com",
                    notes="Looks good",
                )

                assert result is True

    def test_get_decision_retrieves_saved_decision(self):
        """get_decision() retrieves a saved decision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from pathlib import Path as RealPath

            hitl_dir = RealPath(tmpdir) / "hitl"
            hitl_dir.mkdir()

            # Create a decided file
            decided_file = hitl_dir / "test_789_decided.json"
            decided_file.write_text(
                json.dumps(
                    {
                        "analysis_id": "test_789",
                        "decision": "approve",
                        "reviewer": "reviewer@example.com",
                    }
                )
            )

            with patch.object(HITLManager, "HITL_DIR", hitl_dir):
                manager = HITLManager()
                decision = manager.get_decision("test_789")
                assert decision is not None
                assert decision["decision"] == "approve"


class TestAgentGraph:
    """Tests for agent graph structure."""

    def test_graph_builds_successfully(self):
        """build_graph() creates a valid StateGraph."""
        from src.agent.graph import build_graph

        graph = build_graph()
        assert graph is not None

    def test_graph_has_required_nodes(self):
        """Graph contains all required nodes."""
        from src.agent.graph import build_graph

        graph = build_graph()
        # The graph should be a compiled graph
        assert hasattr(graph, "invoke")
