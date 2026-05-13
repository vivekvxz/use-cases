"""Analysis endpoint routes."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from src.agent.graph import HITLPauseError, run_agent
from src.models.pr_analysis import PRAnalysisRequest, PRAnalysisResult

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analyze", tags=["Analysis"])

# In-memory job store — replace with Redis/DB in production
JOB_STORE: dict[str, dict] = {}
BACKGROUND_TASKS: set[asyncio.Task] = set()


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


@router.post("", status_code=202)
async def enqueue_analysis(request: PRAnalysisRequest):
    """Submit a PR for analysis. Returns immediately; poll GET /analyze/{id}."""
    analysis_id = str(uuid4())
    JOB_STORE[analysis_id] = {"status": "queued", "result": None, "error": None}

    task = asyncio.create_task(_run_job(analysis_id, request))
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
