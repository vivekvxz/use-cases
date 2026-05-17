"""Jira ticket fetcher."""

from __future__ import annotations

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from jira.exceptions import JIRAError

from src.config import get_settings

logger = structlog.get_logger(__name__)


class JiraFetcher:
    """Fetch Jira ticket details."""

    def __init__(self) -> None:
        """Initialize Jira fetcher."""
        settings = get_settings()
        self._jira_enabled = settings.jira_enabled

        if not self._jira_enabled:
            self._client = None
            logger.info("jira_disabled_by_config")
            return

        if settings.jira_configured:
            from jira import JIRA

            self._client = JIRA(
                server=settings.jira_server,
                basic_auth=(settings.jira_email, settings.jira_api_token),
            )
            logger.info("jira_connected", server=settings.jira_server)
        else:
            self._client = None
            logger.warning(
                "jira_enabled_but_not_configured",
                hint="Set JIRA_SERVER, JIRA_EMAIL, JIRA_API_TOKEN when JIRA_ENABLED=true",
            )

    @retry(
        stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5)
    )
    async def fetch_tickets(self, ticket_ids: list[str]) -> list[dict]:
        """Fetch structured ticket data from Jira.

        Args:
            ticket_ids: List of ticket IDs

        Returns:
            List of ticket dicts
        """
        if self._client is None:
            if not self._jira_enabled:
                return []
            return [
                {
                    "note": (
                        "Jira enabled but not configured. "
                        "Set JIRA_SERVER, JIRA_EMAIL, JIRA_API_TOKEN in .env"
                    )
                }
            ]

        tickets = []
        for ticket_id in ticket_ids:
            try:
                issue = self._client.issue(ticket_id)
                tickets.append(
                    {
                        "id": ticket_id,
                        "summary": issue.fields.summary,
                        "description": issue.fields.description or "",
                        "status": issue.fields.status.name,
                        "labels": [label.name for label in issue.fields.labels],
                    }
                )
            except (JIRAError, AttributeError, TypeError, KeyError):
                tickets.append({"id": ticket_id, "error": "not found"})

        return tickets

    def format_for_prompt(self, tickets: list[dict]) -> str:
        """Format ticket list into a readable LLM prompt section.

        Args:
            tickets: List of ticket dicts

        Returns:
            Formatted string for LLM
        """
        if not tickets:
            return "No ticket context available."

        lines = []
        for ticket in tickets:
            if "error" in ticket:
                lines.append(f"- [{ticket['id']}]: Not found")
            elif "note" in ticket:
                lines.append(f"- {ticket['note']}")
            else:
                lines.append(f"## [{ticket['id']}] {ticket['summary']}")
                lines.append(f"**Status:** {ticket['status']}")
                if ticket["description"]:
                    lines.append(f"{ticket['description']}")
                if ticket["labels"]:
                    lines.append(f"**Labels:** {', '.join(ticket['labels'])}")
                lines.append("")

        return "\n".join(lines)
