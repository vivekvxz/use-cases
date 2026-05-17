"""LangGraph state graph for the release agent."""

from __future__ import annotations

from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    analysis_node,
    error_node,
    finalise_node,
    hitl_gate_node,
    ingest_node,
    risk_scoring_node,
)
from src.models.agent_state import AgentState
from src.models.pr_analysis import PRAnalysisRequest, PRAnalysisResult


class AgentError(Exception):
    """Raised when the agent encounters an unrecoverable error."""


class HITLPauseError(Exception):
    """Raised when the agent pauses and waits for human review."""


def _route_by_current_node(state: AgentState) -> str:
    """Generic conditional router based on current_node output."""
    return state.get("current_node", "error")


def _route_from_hitl_gate(state: AgentState) -> str:
    """Conditional routing function after hitl_gate_node."""
    return state.get("current_node", "error")


def build_graph():
    """Construct, configure, and compile the LangGraph release agent."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("ingest", ingest_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("risk_scoring", risk_scoring_node)
    graph.add_node("hitl_gate", hitl_gate_node)
    graph.add_node("finalise", finalise_node)
    graph.add_node("error", error_node)

    # Add edges
    graph.add_edge(START, "ingest")

    graph.add_conditional_edges(
        "ingest",
        _route_by_current_node,
        {
            "analysis": "analysis",
            "error": "error",
        },
    )

    graph.add_conditional_edges(
        "analysis",
        _route_by_current_node,
        {
            "risk_scoring": "risk_scoring",
            "error": "error",
        },
    )

    graph.add_conditional_edges(
        "risk_scoring",
        _route_by_current_node,
        {
            "hitl_gate": "hitl_gate",
            "error": "error",
        },
    )

    # Conditional edge from hitl_gate
    graph.add_conditional_edges(
        "hitl_gate",
        _route_from_hitl_gate,
        {
            "finalise": "finalise",
            "awaiting_human": END,
            "error": "error",
        },
    )

    # Edges to end
    graph.add_edge("finalise", END)
    graph.add_edge("error", END)

    # Compile
    return graph.compile(checkpointer=MemorySaver())


release_agent_graph = build_graph()


async def run_agent(request: PRAnalysisRequest) -> PRAnalysisResult:
    """Execute the full agent pipeline for a PR analysis request.

    Args:
        request: PR analysis request

    Returns:
        PRAnalysisResult

    Raises:
        AgentError: On unrecoverable failure
        HITLPauseError: When paused for human review
    """
    # Build initial state
    initial_state = {
        "request": request,
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

    thread_id = (
        f"{request.repo_full_name.replace('/', '_')}_{request.pr_number}_{uuid4().hex[:8]}"
    )
    config = {"configurable": {"thread_id": thread_id}}

    final_state = await release_agent_graph.ainvoke(initial_state, config=config)

    # Handle errors
    if final_state.get("error"):
        raise AgentError(final_state["error"])

    # Handle HITL pause
    if final_state.get("current_node") == "awaiting_human":
        raise HITLPauseError("Analysis paused for human review. Check: data/hitl/")

    # Assemble and return result
    return PRAnalysisResult(
        request=request,
        risk_flags=final_state.get("risk_flags", []),
        design_feedback=final_state.get("design_feedback"),
        release_summary=final_state.get("release_summary", ""),
        improvement_suggestions=final_state.get("improvement_suggestions", []),
        overall_risk_level=final_state.get("overall_risk_level"),
        confidence_score=0.8,
        requires_human_review=final_state.get("requires_human_review", False),
        agent_iterations=final_state.get("iteration_count", 1),
        tokens_used=final_state.get("tokens_used", 0),
    )
