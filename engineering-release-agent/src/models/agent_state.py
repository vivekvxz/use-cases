"""LangGraph state schema for the release agent."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from src.models.pr_analysis import (
    DesignFeedback,
    PRAnalysisRequest,
    RiskFlag,
    RiskLevel,
)


class AgentState(TypedDict):
    """LangGraph state for the release agent pipeline."""

    # ── Input (set once at graph entry) ───────────────────────────────────
    request: PRAnalysisRequest

    # ── Populated by ingest_node ──────────────────────────────────────────
    diff_content: str  # raw unified diff text from GitHub
    ticket_context: str  # formatted Jira ticket summaries (or empty)
    rag_context: str  # retrieved architecture docs from ChromaDB
    lint_results: str  # pylint + pyflakes output summary

    # ── LangGraph message accumulator ─────────────────────────────────────
    messages: Annotated[list, add_messages]

    # ── Agent bookkeeping ─────────────────────────────────────────────────
    current_node: str  # used for conditional routing between nodes
    iteration_count: int

    # ── Outputs built up across nodes ─────────────────────────────────────
    risk_flags: list[RiskFlag]
    design_feedback: DesignFeedback | None
    release_summary: str
    improvement_suggestions: list[str]
    overall_risk_level: RiskLevel | None

    # ── Human-in-the-loop ─────────────────────────────────────────────────
    requires_human_review: bool
    human_decision: str | None  # "approve" | "reject" | "escalate"
    human_notes: str | None

    # ── Error handling ────────────────────────────────────────────────────
    error: str | None
    tokens_used: int
