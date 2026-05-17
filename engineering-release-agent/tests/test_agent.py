"""Tests for agent core."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
class TestAgentNodes:
    """Tests for agent nodes."""

    @patch("src.agent.nodes.GitDiffParser")
    @patch("src.agent.nodes.CodeLinter")
    @patch("src.agent.nodes.JiraFetcher")
    @patch("src.agent.nodes.RAGSearchTool")
    async def test_ingest_node_populates_all_fields(
        self,
        mock_rag,
        mock_jira,
        mock_linter,
        mock_git,
        sample_pr_request,
        sample_diff,
    ):
        """ingest_node populates diff_content, ticket_context, rag_context, lint_results."""
        from src.agent.nodes import ingest_node

        # Mock objects
        mock_git.return_value.fetch_diff = AsyncMock(return_value=sample_diff)
        mock_git.return_value.parse_changed_files.return_value = []
        mock_git.return_value.extract_file_contents.return_value = {}

        mock_linter.return_value.lint.return_value = {
            "errors": [],
            "warnings": [],
            "pylint_score": 8.0,
        }
        mock_linter.return_value.format_for_prompt.return_value = "No issues"

        mock_jira.return_value.fetch_tickets = AsyncMock(return_value=[])
        mock_jira.return_value.format_for_prompt.return_value = "No tickets"

        mock_rag.return_value.search = AsyncMock(return_value=[])
        mock_rag.return_value.format_for_prompt.return_value = "No context"

        # Create state
        state = {
            "request": sample_pr_request,
            "diff_content": "",
            "ticket_context": "",
            "rag_context": "",
            "lint_results": "",
            "messages": [],
            "current_node": "ingest",
            "iteration_count": 0,
            "risk_flags": [],
            "design_feedback": None,
            "release_summary": "",
            "improvement_suggestions": [],
            "overall_risk_level": None,
            "requires_human_review": False,
            "human_decision": None,
            "human_notes": None,
            "error": None,
            "tokens_used": 0,
        }

        # Run node
        result = await ingest_node(state)

        assert "diff_content" in result
        assert "ticket_context" in result
        assert "rag_context" in result
        assert "lint_results" in result
        assert result["current_node"] == "analysis"


class TestGraphRouting:
    """Tests for graph routing helpers."""

    def test_route_by_current_node_success(self):
        """Generic router returns current_node when present."""
        from src.agent.graph import _route_by_current_node

        assert _route_by_current_node({"current_node": "analysis"}) == "analysis"

    def test_route_by_current_node_defaults_error(self):
        """Generic router falls back to error when current_node is missing."""
        from src.agent.graph import _route_by_current_node

        assert _route_by_current_node({}) == "error"
