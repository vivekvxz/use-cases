"""Analysis endpoint routes."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, model_validator

from src.agent.graph import HITLPauseError, run_agent
from src.models.pr_analysis import PRAnalysisRequest, PRAnalysisResult
from src.config import get_settings
from src.tools.github_pr import fetch_pr_details, parse_github_pr_url

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analyze", tags=["Analysis"])

# In-memory job store — replace with Redis/DB in production
JOB_STORE: dict[str, dict] = {}
BACKGROUND_TASKS: set[asyncio.Task] = set()


class AnalyzeSubmissionRequest(BaseModel):
    """Request body accepted by POST /analyze."""

    pr_url: str | None = Field(
        default=None,
        description=(
            "Optional full GitHub PR URL. If provided, the API parses repo and PR number "
            "automatically. Example: https://github.com/vivekvxz/use-cases/pull/1"
        ),
        examples=["https://github.com/vivekvxz/use-cases/pull/1"],
    )
    repo_full_name: str | None = Field(
        default=None,
        description=(
            "GitHub repository in owner/repo format. Required when pr_url is not provided."
        ),
        examples=["vivekvxz/use-cases"],
    )
    pr_number: int | None = Field(
        default=None,
        gt=0,
        description="Pull request number. Required when pr_url is not provided.",
        examples=[1],
    )
    base_sha: str | None = Field(
        default=None,
        min_length=6,
        description=(
            "Base commit SHA for diff range. If omitted, it is auto-fetched from GitHub."
        ),
        examples=["abc1234"],
    )
    head_sha: str | None = Field(
        default=None,
        min_length=6,
        description=(
            "Head commit SHA for diff range. If omitted, it is auto-fetched from GitHub."
        ),
        examples=["def5678"],
    )
    pr_title: str | None = Field(
        default=None,
        description="PR title. If omitted, fetched from GitHub.",
        examples=["Add retry logic to release analysis pipeline"],
    )
    pr_description: str | None = Field(
        default=None,
        description="PR description/body. If omitted, fetched from GitHub.",
        examples=["Adds exponential backoff and improves failure handling."],
    )
    ticket_ids: list[str] = Field(
        default_factory=list,
        description="Optional Jira/Linear ticket IDs (e.g. ['ENG-123', 'REL-9']).",
        examples=[["ENG-123", "REL-9"]],
    )
    author: str | None = Field(
        default=None,
        description="PR author username. If omitted, fetched from GitHub.",
        examples=["vivekvxz"],
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description=(
            "List of changed files. If omitted or empty, fetched from GitHub for richer context."
        ),
        examples=[["src/api/routes/analyze.py", "README.md"]],
    )

    @model_validator(mode="after")
    def validate_required_identifiers(self) -> "AnalyzeSubmissionRequest":
        """Require either PR URL or repo+PR identifier fields."""
        has_pr_url = bool(self.pr_url)
        has_repo_pr = bool(self.repo_full_name and self.pr_number is not None)

        if not has_pr_url and not has_repo_pr:
            raise ValueError(
                "Provide either pr_url, or both repo_full_name and pr_number"
            )
        return self


class EnqueueAnalysisResponse(BaseModel):
    """Response body for accepted analysis requests."""

    analysis_id: str = Field(description="Server-generated analysis job identifier")
    status: str = Field(description="Initial job status", examples=["queued"])
    poll_url: str = Field(description="Relative URL for polling job status")


def _normalize_submission(submission: AnalyzeSubmissionRequest) -> PRAnalysisRequest:
    """Normalize URL/repo inputs into an internal PRAnalysisRequest."""
    settings = get_settings()

    repo_full_name = submission.repo_full_name
    pr_number = submission.pr_number

    if submission.pr_url:
        parsed_repo, parsed_pr_number = parse_github_pr_url(submission.pr_url)
        repo_full_name = repo_full_name or parsed_repo
        pr_number = pr_number or parsed_pr_number

    if not repo_full_name or pr_number is None:
        raise HTTPException(
            status_code=422,
            detail="Could not resolve repo_full_name and pr_number from request",
        )

    needs_github_fetch = any(
        [
            submission.base_sha is None,
            submission.head_sha is None,
            submission.pr_title is None,
            submission.author is None,
            not submission.changed_files,
            submission.pr_description is None,
        ]
    )

    details = None
    if needs_github_fetch:
        try:
            details = fetch_pr_details(repo_full_name, pr_number, settings.github_token)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise HTTPException(
                status_code=400,
                detail=(
                    "Failed to fetch PR details from GitHub. Check pr_url/repo/pr_number "
                    "and ensure GITHUB_TOKEN is configured."
                ),
            ) from exc

    return PRAnalysisRequest(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        base_sha=submission.base_sha or (details.base_sha if details else ""),
        head_sha=submission.head_sha or (details.head_sha if details else ""),
        pr_title=submission.pr_title or (details.title if details else ""),
        pr_description=(
            submission.pr_description
            if submission.pr_description is not None
            else (details.description if details else "")
        ),
        ticket_ids=submission.ticket_ids,
        author=submission.author or (details.author if details else ""),
        changed_files=submission.changed_files or (details.changed_files if details else []),
    )


async def _run_job(analysis_id: str, request: PRAnalysisRequest) -> None:
    """Background task: run agent and update JOB_STORE."""
    try:
        JOB_STORE[analysis_id]["status"] = "running"
        result = await run_agent(request)
        JOB_STORE[analysis_id]["status"] = "completed"
        JOB_STORE[analysis_id]["result"] = result.model_dump(mode="json")
    except HITLPauseError:
        JOB_STORE[analysis_id]["status"] = "awaiting_human_review"
    except Exception as e:  # pylint: disable=broad-exception-caught
        JOB_STORE[analysis_id]["status"] = "failed"
        JOB_STORE[analysis_id]["error"] = str(e)
        logger.error("job_error", analysis_id=analysis_id, error=str(e))


@router.post(
    "",
    status_code=202,
    response_model=EnqueueAnalysisResponse,
    summary="Submit a PR for analysis",
    description=(
        "Queues an asynchronous PR analysis job and returns an analysis_id immediately. "
        "You may provide either `pr_url` OR (`repo_full_name` + `pr_number`). "
        "Missing PR metadata fields are auto-fetched from GitHub."
    ),
)
async def enqueue_analysis(request: AnalyzeSubmissionRequest):
    """Submit a PR for analysis. Returns immediately; poll GET /analyze/{id}."""
    normalized_request = _normalize_submission(request)
    analysis_id = str(uuid4())
    JOB_STORE[analysis_id] = {"status": "queued", "result": None, "error": None}

    task = asyncio.create_task(_run_job(analysis_id, normalized_request))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)

    return {
        "analysis_id": analysis_id,
        "status": "queued",
        "poll_url": f"/analyze/{analysis_id}",
    }


@router.get("/{analysis_id}", responses={404: {"description": "Analysis not found"}})
async def get_analysis(analysis_id: str):
    """Poll for the status and result of an in-progress or completed analysis."""
    if analysis_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Analysis not found")

    job = JOB_STORE[analysis_id]
    return {
        "analysis_id": analysis_id,
        "status": job["status"],
        "result": job.get("result"),
        "error": job.get("error"),
    }


@router.get(
    "/{analysis_id}/markdown",
    response_class=PlainTextResponse,
    responses={
        400: {"description": "Analysis not yet completed"},
        404: {"description": "Analysis or result not found"},
    },
)
async def get_analysis_markdown(analysis_id: str) -> str:
    """Return Markdown suitable for pasting as a GitHub PR comment."""
    if analysis_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Analysis not found")

    job = JOB_STORE[analysis_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Analysis not yet completed")

    if not job.get("result"):
        raise HTTPException(status_code=404, detail="Result not found")

    result = PRAnalysisResult.model_validate(job["result"])
    return result.to_markdown()
