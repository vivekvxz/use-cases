"""Human-in-the-loop pause/resume management."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class HITLManager:
    """File-based human-in-the-loop manager."""

    HITL_DIR = Path("data/hitl")
    VALID_DECISIONS = {"approve", "reject", "escalate"}

    def __init__(self) -> None:
        """Initialize HITL manager."""
        self.HITL_DIR.mkdir(parents=True, exist_ok=True)

    def _json_serialiser(self, obj):  # noqa: ANN001, ANN201
        """Custom JSON serialiser for UUID and datetime objects."""
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")

    def save_pending(self, analysis_id: str, state: dict) -> Path:
        """Serialise and save pending HITL state to a local JSON file.

        Args:
            analysis_id: Analysis ID
            state: State dict

        Returns:
            Path to saved file
        """
        path = self.HITL_DIR / f"{analysis_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, default=self._json_serialiser, indent=2)
        logger.info("hitl_pending_saved", analysis_id=analysis_id, path=str(path))
        return path

    def get_pending(self) -> list[dict]:
        """Return summaries of all pending (undecided) HITL review requests.

        Returns:
            List of pending review summaries
        """
        pending = []
        for path in self.HITL_DIR.glob("*.json"):
            if path.name.endswith("_decided.json"):
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pending.append(
                        {
                            "analysis_id": path.stem,
                            "pr_title": data.get("request", {}).get(
                                "pr_title", "Unknown"
                            ),
                            "risk_level": str(
                                data.get("overall_risk_level", "unknown")
                            ),
                            "created_at": data.get("created_at", "unknown"),
                            "file_path": str(path),
                        }
                    )
            except (OSError, TypeError, json.JSONDecodeError) as e:
                logger.error("hitl_load_error", path=str(path), error=str(e))

        return pending

    def submit_decision(
        self, analysis_id: str, decision: str, reviewer: str, notes: str = ""
    ) -> bool:
        """Record a human decision for a pending review request.

        Args:
            analysis_id: Analysis ID
            decision: "approve" | "reject" | "escalate"
            reviewer: Reviewer name
            notes: Optional notes

        Returns:
            True if successful

        Raises:
            ValueError: If decision is invalid
            FileNotFoundError: If analysis not found
        """
        if decision not in self.VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision: {decision}. Must be one of {self.VALID_DECISIONS}"
            )

        pending_path = self.HITL_DIR / f"{analysis_id}.json"
        if not pending_path.exists():
            raise FileNotFoundError(f"Pending analysis not found: {analysis_id}")

        # Load pending state
        with open(pending_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Add decision
        state["decision"] = decision
        state["reviewer"] = reviewer
        state["notes"] = notes
        state["decided_at"] = datetime.now(timezone.utc).isoformat()

        # Save as decided
        decided_path = self.HITL_DIR / f"{analysis_id}_decided.json"
        with open(decided_path, "w", encoding="utf-8") as f:
            json.dump(state, f, default=self._json_serialiser, indent=2)

        # Delete pending
        pending_path.unlink()

        logger.info(
            "hitl_decision_submitted",
            analysis_id=analysis_id,
            decision=decision,
            reviewer=reviewer,
        )
        return True

    def get_decision(self, analysis_id: str) -> dict | None:
        """Load a submitted decision, or return None if not yet decided.

        Args:
            analysis_id: Analysis ID

        Returns:
            Decision dict or None
        """
        decided_path = self.HITL_DIR / f"{analysis_id}_decided.json"
        if not decided_path.exists():
            return None

        with open(decided_path, "r", encoding="utf-8") as f:
            return json.load(f)
