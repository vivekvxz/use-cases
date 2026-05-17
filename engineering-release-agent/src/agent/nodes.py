"""LangGraph agent nodes."""

from __future__ import annotations

import json
import structlog
from rich.console import Console
from rich.panel import Panel

from src.agent.hitl import HITLManager
from src.audit.logger import AuditLogger, get_session_factory
from src.config import get_llm, get_settings
from src.ingestion.git_parser import GitDiffParser
from src.models.agent_state import AgentState
from src.models.pr_analysis import (
    DesignFeedback,
    FeedbackType,
    PRAnalysisResult,
    RiskFlag,
    RiskLevel,
)
from src.agent.prompts import ANALYSIS_PROMPT, RISK_SCORING_PROMPT
from src.tools.code_linter import CodeLinter
from src.tools.jira_fetcher import JiraFetcher
from src.tools.rag_search import RAGSearchTool

logger = structlog.get_logger(__name__)
console = Console()


async def ingest_node(state: AgentState) -> dict:
    """Fetch diff, lint files, pull Jira tickets, and search knowledge base."""
    try:
        request = state["request"]
        logger.info(
            "ingest_node_start", repo=request.repo_full_name, pr=request.pr_number
        )

        # Fetch diff
        git_parser = GitDiffParser()
        diff_content = await git_parser.fetch_diff(
            request.repo_full_name,
            request.base_sha,
            request.head_sha,
            request.pr_number,
        )

        # Extract file contents and lint
        changed_files = request.changed_files or []
        file_contents = git_parser.extract_file_contents(
            request.repo_full_name,
            changed_files,
            request.head_sha,
        )
        linter = CodeLinter()
        lint_output = linter.lint(file_contents)
        lint_results = linter.format_for_prompt(lint_output)

        # Fetch Jira tickets
        jira_fetcher = JiraFetcher()
        tickets = await jira_fetcher.fetch_tickets(request.ticket_ids)
        ticket_context = jira_fetcher.format_for_prompt(tickets)

        # Search knowledge base
        rag_search = RAGSearchTool()
        search_query = f"{request.pr_title} {request.pr_description or ''}"
        rag_results = await rag_search.search(search_query, top_k=5)
        rag_context = rag_search.format_for_prompt(rag_results)

        logger.info(
            "ingest_node_complete", repo=request.repo_full_name, pr=request.pr_number
        )

        return {
            "diff_content": diff_content,
            "ticket_context": ticket_context,
            "rag_context": rag_context,
            "lint_results": lint_results,
            "current_node": "analysis",
        }

    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        logger.error("ingest_node_error", error=str(e))
        return {"error": str(e), "current_node": "error"}


async def analysis_node(state: AgentState) -> dict:
    """Call LLM with all context and extract structured risk findings."""
    try:
        request = state["request"]
        logger.info(
            "analysis_node_start", repo=request.repo_full_name, pr=request.pr_number
        )

        # Build prompt
        prompt = ANALYSIS_PROMPT.format(
            pr_title=request.pr_title,
            author=request.author,
            pr_description=request.pr_description or "",
            diff_content=state.get("diff_content", ""),
            ticket_context=state.get("ticket_context", ""),
            rag_context=state.get("rag_context", ""),
            lint_results=state.get("lint_results", ""),
        )

        # Call LLM
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        response_text = response.content

        # Strip markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        # Parse JSON
        parsed = json.loads(response_text)

        # Construct risk flags
        risk_flags = []
        for flag_data in parsed.get("risk_flags", []):
            risk_flags.append(
                RiskFlag(
                    risk_level=RiskLevel(flag_data["risk_level"]),
                    feedback_type=FeedbackType(flag_data["feedback_type"]),
                    title=flag_data["title"],
                    description=flag_data["description"],
                    file_path=flag_data.get("file_path"),
                    line_range=(
                        tuple(flag_data["line_range"])
                        if flag_data.get("line_range")
                        else None
                    ),
                    suggested_fix=flag_data.get("suggested_fix"),
                    confidence=flag_data.get("confidence", 0.5),
                    source_citations=flag_data.get("source_citations", []),
                )
            )

        # Construct design feedback
        design_feedback = DesignFeedback(
            summary=parsed["design_feedback"]["summary"],
            strengths=parsed["design_feedback"].get("strengths", []),
            concerns=parsed["design_feedback"].get("concerns", []),
            suggestions=parsed["design_feedback"].get("suggestions", []),
        )

        # Count tokens
        tokens_used = 0
        if hasattr(response, "usage_metadata"):
            tokens_used = response.usage_metadata.get("total_tokens", 0)

        logger.info(
            "analysis_node_complete", repo=request.repo_full_name, pr=request.pr_number
        )

        return {
            "risk_flags": risk_flags,
            "design_feedback": design_feedback,
            "release_summary": parsed.get("release_summary", ""),
            "improvement_suggestions": parsed.get("improvement_suggestions", []),
            "tokens_used": tokens_used,
            "current_node": "risk_scoring",
        }

    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        logger.error("analysis_node_error", error=str(e))
        return {"error": str(e), "current_node": "error"}


async def risk_scoring_node(state: AgentState) -> dict:
    """Determine overall PR risk level and whether human review is required."""
    try:
        request = state["request"]
        logger.info(
            "risk_scoring_node_start", repo=request.repo_full_name, pr=request.pr_number
        )

        settings = get_settings()

        # Build risk flags JSON
        risk_flags_json = json.dumps(
            [f.model_dump(mode="json") for f in state.get("risk_flags", [])],
            default=str,
        )

        # Build prompt
        prompt = RISK_SCORING_PROMPT.format(
            risk_flags_json=risk_flags_json,
            hitl_threshold=settings.hitl_risk_threshold,
        )

        # Call LLM
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        response_text = response.content

        # Strip markdown if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        # Parse JSON
        parsed = json.loads(response_text)

        overall_risk_level = RiskLevel(parsed["overall_risk_level"])
        llm_requires_human_review = bool(parsed.get("requires_human_review", False))

        # Enforce HITL policy in code so it does not rely solely on LLM compliance.
        try:
            overall_risk_score = float(parsed.get("overall_risk_score", 0.0))
        except (TypeError, ValueError):
            overall_risk_score = 0.0

        has_critical_flag = any(
            flag.risk_level == RiskLevel.CRITICAL
            for flag in state.get("risk_flags", [])
        )

        requires_human_review = (
            llm_requires_human_review
            or overall_risk_score >= settings.hitl_risk_threshold
            or has_critical_flag
        )

        logger.info(
            "risk_scoring_node_complete",
            repo=request.repo_full_name,
            pr=request.pr_number,
        )

        return {
            "overall_risk_level": overall_risk_level,
            "requires_human_review": requires_human_review,
            "current_node": "hitl_gate",
        }

    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        logger.error("risk_scoring_node_error", error=str(e))
        return {"error": str(e), "current_node": "error"}


def hitl_gate_node(state: AgentState) -> dict:
    """Route: pause for human review OR proceed to finalise."""
    try:
        if state.get("requires_human_review"):
            # Save pending review
            hitl_manager = HITLManager()
            analysis_id = str(state.get("request").repo_full_name.replace("/", "_"))
            hitl_manager.save_pending(analysis_id, dict(state))

            console.print(
                Panel(
                    f"[bold red]⏸ Human Review Required[/bold red]\n"
                    f"Risk Level: {state.get('overall_risk_level')}\n"
                    f"Analysis ID: {analysis_id}\n"
                    f"File: data/hitl/{analysis_id}.json",
                    title="Human Review",
                    border_style="yellow",
                )
            )
            return {"current_node": "awaiting_human"}

        return {"current_node": "finalise"}

    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        logger.error("hitl_gate_node_error", error=str(e))
        return {"error": str(e), "current_node": "error"}


async def finalise_node(state: AgentState) -> dict:
    """Assemble result, log to SQLite, print rich summary."""
    try:
        request = state["request"]
        logger.info(
            "finalise_node_start", repo=request.repo_full_name, pr=request.pr_number
        )

        # Assemble result
        result = PRAnalysisResult(
            request=request,
            risk_flags=state.get("risk_flags", []),
            design_feedback=state.get("design_feedback") or DesignFeedback(summary=""),
            release_summary=state.get("release_summary", ""),
            improvement_suggestions=state.get("improvement_suggestions", []),
            overall_risk_level=state.get("overall_risk_level") or RiskLevel.MEDIUM,
            confidence_score=0.8,
            requires_human_review=state.get("requires_human_review", False),
            agent_iterations=state.get("iteration_count", 1),
            tokens_used=state.get("tokens_used", 0),
        )

        # Log to audit
        session_factory = get_session_factory()
        async with session_factory() as session:
            audit_logger = AuditLogger(session)
            await audit_logger.log(
                "analysis_completed",
                {
                    "analysis_id": str(result.analysis_id),
                    "repo": request.repo_full_name,
                    "pr_number": request.pr_number,
                    "risk_level": result.overall_risk_level.value,
                },
            )

        # Print summary
        console.print(result.to_markdown())

        logger.info(
            "finalise_node_complete", repo=request.repo_full_name, pr=request.pr_number
        )

        return {"current_node": "done"}

    except (KeyError, ValueError, TypeError, RuntimeError) as e:
        logger.error("finalise_node_error", error=str(e))
        return {"error": str(e), "current_node": "error"}


def error_node(state: AgentState) -> dict:
    """Handle errors gracefully with logging and a rich error panel."""
    error_msg = state.get("error", "Unknown error")
    logger.error("error_node", error=error_msg)

    console.print(
        Panel(
            f"[bold red]❌ Analysis Failed[/bold red]\n{error_msg}",
            title="Error",
            border_style="red",
        )
    )

    return {"current_node": "error"}
