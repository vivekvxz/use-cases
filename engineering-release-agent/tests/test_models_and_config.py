"""Tests for audit logging and models."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.audit.logger import AuditLog, AuditLogger
from src.models.pr_analysis import (
    DesignFeedback,
    PRAnalysisRequest,
    PRAnalysisResult,
    RiskFlag,
    RiskLevel,
)


class TestAuditLogging:
    """Tests for audit logging functionality."""

    def test_audit_log_model(self):
        """AuditLog model creates valid records."""
        log = AuditLog(
            analysis_id="test_123",
            event_type="analysis_started",
            payload={"repo": "test/repo", "pr": 1},
            actor="system",
        )

        assert log.analysis_id == "test_123"
        assert log.event_type == "analysis_started"
        assert log.actor == "system"

    @pytest.mark.asyncio
    async def test_audit_logger_log_writes_entry(self):
        """AuditLogger.log stores and refreshes a log entry."""
        session = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda entry: setattr(entry, "id", 10))
        logger = AuditLogger(session)

        log_id = await logger.log(
            event_type="analysis_completed",
            payload={"analysis_id": "a-1", "status": "ok"},
            actor="system",
        )

        assert log_id == 10
        assert session.add.called
        assert session.commit.called

    @pytest.mark.asyncio
    async def test_audit_logger_get_logs(self):
        """AuditLogger.get_logs returns normalized dict records."""
        session = AsyncMock()
        row = MagicMock()
        row.id = 1
        row.event_type = "analysis_started"
        row.payload = json.dumps({"analysis_id": "a-1"})
        row.created_at = MagicMock()
        row.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        row.actor = "agent"

        scalar_result = MagicMock()
        scalar_result.all.return_value = [row]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalar_result
        session.execute.return_value = exec_result
        logger = AuditLogger(session)
        logs = await logger.get_logs("a-1")

        assert len(logs) == 1
        assert logs[0]["event_type"] == "analysis_started"
        assert logs[0]["payload"]["analysis_id"] == "a-1"


class TestPRAnalysisModels:
    """Tests for PR analysis data models."""

    def test_design_feedback_model(self):
        """DesignFeedback model matches structured feedback schema."""
        feedback = DesignFeedback(
            summary="Good design with minor concerns",
            strengths=["clear abstractions"],
            concerns=["missing retries"],
            suggestions=["add exponential backoff"],
        )

        assert feedback.summary.startswith("Good design")
        assert len(feedback.suggestions) == 1

    def test_pr_analysis_result_with_no_flags(self):
        """PRAnalysisResult handles no risk flags."""
        request = PRAnalysisRequest(
            repo_full_name="test/repo",
            pr_number=1,
            base_sha="abcdef",
            head_sha="123456",
            pr_title="Test",
            pr_description="Desc",
            author="tester",
            changed_files=["src/main.py"],
        )

        feedback = DesignFeedback(
            summary="No major concerns",
            strengths=[],
            concerns=[],
            suggestions=[],
        )

        result = PRAnalysisResult(
            request=request,
            risk_flags=[],
            design_feedback=feedback,
            release_summary="No issues found",
            improvement_suggestions=[],
            overall_risk_level=RiskLevel.LOW,
            confidence_score=0.9,
            requires_human_review=False,
            agent_iterations=1,
            tokens_used=100,
        )

        assert len(result.risk_flags) == 0
        assert result.overall_risk_level == RiskLevel.LOW

    def test_risk_flag_model(self):
        """RiskFlag stores risk metadata with current field names."""
        flag = RiskFlag(
            risk_level=RiskLevel.MEDIUM,
            feedback_type="security",
            title="Auth validation missing",
            description="Token not validated in middleware",
            confidence=0.8,
        )
        assert flag.risk_level == RiskLevel.MEDIUM
        assert 0.0 <= flag.confidence <= 1.0


class TestConfiguration:
    """Tests for configuration management."""

    def test_get_settings_singleton(self):
        """get_settings() returns cached singleton."""
        from src.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_llm_provider_lowercase_value(self):
        """Computed llm_provider returns lowercase backend name."""
        from src.config import get_settings

        provider = get_settings().llm_provider
        assert provider in ["openai", "ollama"]

    def test_thresholds_accept_string_values(self):
        """Threshold fields parse string values from environment-like inputs."""
        from src.config import Settings

        settings = Settings(
            use_ollama=True,
            hitl_risk_threshold="0.80",
            confidence_threshold="0.60",
        )

        assert settings.hitl_risk_threshold == pytest.approx(0.8)
        assert settings.confidence_threshold == pytest.approx(0.6)

    def test_thresholds_reject_non_numeric_values(self):
        """Threshold fields fail validation for non-numeric values."""
        from src.config import Settings

        with pytest.raises(ValueError, match="Threshold must be a number"):
            Settings(
                use_ollama=True,
                hitl_risk_threshold="not-a-number",
                confidence_threshold=0.6,
            )
