"""GitHub webhook handler."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from src.api.routes.analyze import JOB_STORE, _run_job
from src.config import get_settings
from src.models.pr_analysis import PRAnalysisRequest

router = APIRouter(prefix="/webhook", tags=["Webhooks"])
logger = structlog.get_logger(__name__)
BACKGROUND_TASKS = set()


@router.post(
    "/github",
    responses={
        400: {"description": "Invalid JSON"},
        401: {"description": "Invalid signature"},
    },
)
async def github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
):
    """Receive GitHub PR webhook events and enqueue analysis jobs."""
    settings = get_settings()

    # Read raw body
    body_bytes = await request.body()

    # Verify signature
    webhook_secret = str(settings.github_webhook_secret)
    expected = (
        "sha256="
        + hmac.new(
            webhook_secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(expected, x_hub_signature_256 or ""):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON
    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    # Check event type
    if x_github_event != "pull_request":
        return {"skipped": True, "reason": "not a pull_request event"}

    # Check action
    action = payload.get("action", "")
    if action not in ("opened", "synchronize"):
        return {"skipped": True, "reason": f"action '{action}' ignored"}

    # Build request
    pr = payload["pull_request"]
    analysis_request = PRAnalysisRequest(
        repo_full_name=payload["repository"]["full_name"],
        pr_number=pr["number"],
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        pr_title=pr["title"],
        pr_description=pr.get("body", ""),
        author=pr["user"]["login"],
        changed_files=[f["filename"] for f in pr.get("changed_files", [])],
    )

    # Enqueue job
    import asyncio
    from uuid import uuid4

    analysis_id = str(uuid4())
    JOB_STORE[analysis_id] = {"status": "queued", "result": None, "error": None}
    task = asyncio.create_task(_run_job(analysis_id, analysis_request))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)

    return {
        "queued": True,
        "analysis_id": analysis_id,
        "pr": pr["number"],
    }
