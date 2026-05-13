"""PR analysis data models using Pydantic v2."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    """Risk level enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackType(str, Enum):
    """Feedback type enumeration."""

    DESIGN = "design"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    TEST_COVERAGE = "test_coverage"
    BREAKING_CHANGE = "breaking_change"


class PRAnalysisRequest(BaseModel):
    """Input contract — sent to the agent via CLI, API, or GitHub webhook."""

    model_config = ConfigDict(from_attributes=True)

    repo_full_name: str = Field(..., examples=["acme/payments-service"])
    pr_number: int = Field(..., gt=0)
    base_sha: str = Field(..., min_length=6)
    head_sha: str = Field(..., min_length=6)
    pr_title: str
    pr_description: str | None = None
    ticket_ids: list[str] = Field(
        default_factory=list,
        description="Jira/Linear ticket IDs e.g. ['ENG-123']",
    )
    author: str
    changed_files: list[str] = Field(default_factory=list)


class RiskFlag(BaseModel):
    """A single concrete risk identified by the agent."""

    model_config = ConfigDict(from_attributes=True)

    flag_id: UUID = Field(default_factory=uuid4)
    risk_level: RiskLevel
    feedback_type: FeedbackType
    title: str
    description: str
    file_path: str | None = None
    line_range: tuple[int, int] | None = None
    suggested_fix: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_citations: list[str] = Field(default_factory=list)


class DesignFeedback(BaseModel):
    """Structured design review produced by the agent."""

    model_config = ConfigDict(from_attributes=True)

    summary: str
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PRAnalysisResult(BaseModel):
    """Full output of one agent run — stored in SQLite, returned by API."""

    model_config = ConfigDict(from_attributes=True)

    analysis_id: UUID = Field(default_factory=uuid4)
    request: PRAnalysisRequest
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    design_feedback: DesignFeedback
    release_summary: str = Field(description="Plain-English summary for non-engineers")
    improvement_suggestions: list[str] = Field(default_factory=list)
    overall_risk_level: RiskLevel
    confidence_score: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool
    created_at: datetime = Field(default_factory=datetime.utcnow)
    agent_iterations: int = 0
    tokens_used: int = 0

    @staticmethod
    def _risk_emoji(level: RiskLevel) -> str:
        mapping = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴",
        }
        return mapping.get(level, "⚪")

    def _append_design_feedback(self, lines: list[str]) -> None:
        sections = [
            ("Strengths", self.design_feedback.strengths),
            ("Concerns", self.design_feedback.concerns),
            ("Suggestions", self.design_feedback.suggestions),
        ]
        for title, values in sections:
            if not values:
                continue
            lines.append(f"**{title}:**")
            for value in values:
                lines.append(f"- {value}")
            lines.append("")

    def _append_risk_flags(self, lines: list[str]) -> None:
        if not self.risk_flags:
            return
        lines.extend(
            [
                "## Risk Flags",
                "",
                "| Level | Type | Title | File | Fix |",
                "|-------|------|-------|------|-----|",
            ]
        )
        for flag in self.risk_flags:
            file_info = flag.file_path or "—"
            fix_info = (flag.suggested_fix or "—")[:50]
            lines.append(
                f"| {flag.risk_level.value} | {flag.feedback_type.value} | "
                f"{flag.title} | {file_info} | {fix_info} |"
            )
        lines.append("")

    def _append_improvements(self, lines: list[str]) -> None:
        if not self.improvement_suggestions:
            return
        lines.extend(["## Improvement Suggestions", ""])
        for suggestion in self.improvement_suggestions:
            lines.append(f"- {suggestion}")
        lines.append("")

    def to_markdown(self) -> str:
        """Return a Markdown string formatted as a GitHub PR comment."""
        emoji = self._risk_emoji(self.overall_risk_level)
        lines = [
            "# 🤖 Release Agent Analysis",
            "",
            f"{emoji} **Risk Level: {self.overall_risk_level.value.upper()}**",
            "",
            "## Release Summary",
            "",
            self.release_summary,
            "",
            "## Design Feedback",
            "",
        ]

        self._append_design_feedback(lines)
        self._append_risk_flags(lines)
        self._append_improvements(lines)

        lines.append("---")
        lines.append(
            f"_Confidence: {self.confidence_score * 100:.0f}% · "
            f"Tokens: {self.tokens_used} · "
            f"Analysis ID: {self.analysis_id}_"
        )

        return "\n".join(lines)
