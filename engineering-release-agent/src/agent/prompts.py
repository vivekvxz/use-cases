"""Agent prompts."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PROMPT = """You are a senior software engineering reviewer specialising in release risk analysis.
You have deep expertise in distributed systems, API design, security, and Python best practices.

Rules you must follow:
- Always reference specific files and approximate line numbers for each finding
- Assign a confidence score (0.0–1.0) to each finding
- When uncertain, say so — NEVER invent code that is not in the provided diff
- Every finding must be grounded in evidence from the diff or context provided
- Output ONLY valid JSON — no preamble, no markdown code fences
"""

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            """Analyse the following pull request and return a structured JSON review.

## Pull Request
Title: {pr_title}
Author: {author}
Description: {pr_description}

## Git Diff
{diff_content}

## Jira Ticket Context
{ticket_context}

## Architecture Knowledge Base
{rag_context}

## Lint Results
{lint_results}

Return ONLY this JSON structure (no markdown, no preamble):
{{
  "risk_flags": [
    {{
      "risk_level": "low|medium|high|critical",
      "feedback_type": "design|security|performance|maintainability|test_coverage|breaking_change",
      "title": "Short descriptive title",
      "description": "Detailed description citing specific file and line range",
      "file_path": "path/to/file.py",
      "line_range": [start_line, end_line],
      "suggested_fix": "Concrete code or approach to fix this",
      "confidence": 0.85,
      "source_citations": ["+ line from diff that supports this finding"]
    }}
  ],
  "design_feedback": {{
    "summary": "Overall design assessment in 2-3 sentences",
    "strengths": ["what this PR does well"],
    "concerns": ["genuine design concerns"],
    "suggestions": ["concrete improvements"]
  }},
  "release_summary": "2-3 sentence plain-English summary for non-engineers",
  "improvement_suggestions": ["suggestions for future PRs, not blocking"]
}}
""",
        ),
    ]
)

RISK_SCORING_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            """Given the risk flags below, determine the overall PR risk level.

Risk flags:
{risk_flags_json}

HITL threshold: {hitl_threshold}
Set requires_human_review=true if: overall_risk_score >= {hitl_threshold} OR any flag is "critical".

Return ONLY this JSON (no markdown, no preamble):
{{
  "overall_risk_level": "low|medium|high|critical",
  "overall_risk_score": 0.72,
  "requires_human_review": false,
  "justification": "1-2 sentences explaining the decision"
}}
""",
        ),
    ]
)
