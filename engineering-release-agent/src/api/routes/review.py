"""Human-in-the-loop review endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.agent.hitl import HITLManager
from src.config import get_settings

router = APIRouter(prefix="/review", tags=["Human Review"])


class DecisionRequest(BaseModel):
    """Decision request body."""

    decision: str
    reviewer: str
    notes: str = ""


@router.get("/pending", responses={401: {"description": "Invalid API key"}})
async def get_pending_reviews(x_api_key: Annotated[str, Header()]):
    """List all pending HITL reviews (requires internal API key)."""
    settings = get_settings()
    if x_api_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return HITLManager().get_pending()


@router.post(
    "/{analysis_id}/decision",
    responses={
        400: {"description": "Invalid decision"},
        404: {"description": "Analysis not found"},
    },
)
async def submit_decision(analysis_id: str, body: DecisionRequest):
    """Submit a human approval/rejection for a paused analysis."""
    try:
        hitl_manager = HITLManager()
        hitl_manager.submit_decision(
            analysis_id, body.decision, body.reviewer, body.notes
        )
        return {
            "status": "decision_recorded",
            "analysis_id": analysis_id,
            "decision": body.decision,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis not found") from exc
