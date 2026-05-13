"""Audit logging with SQLAlchemy async + SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped

from src.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


class AuditLog(Base):
    """Audit log table."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actor: Mapped[str] = mapped_column(String(100), default="agent")


def get_session_factory() -> async_sessionmaker:
    """Return an async session factory bound to the SQLite database."""
    engine = create_async_engine(get_settings().sqlite_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


class AuditLogger:
    """Log audit events to SQLite."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize audit logger with a session."""
        self._session = session

    async def log(self, event_type: str, payload: dict, actor: str = "agent") -> int:
        """Write an immutable audit event to the SQLite audit_logs table.

        Args:
            event_type: Type of event
            payload: Event payload dict
            actor: Actor performing the action

        Returns:
            ID of the created log entry
        """
        log_entry = AuditLog(
            analysis_id=payload.get("analysis_id", "unknown"),
            event_type=event_type,
            payload=json.dumps(payload),
            actor=actor,
        )
        self._session.add(log_entry)
        await self._session.commit()
        await self._session.refresh(log_entry)
        return log_entry.id

    async def get_logs(self, analysis_id: str) -> list[dict]:
        """Retrieve all audit events for a given analysis, ordered by time.

        Args:
            analysis_id: Analysis ID

        Returns:
            List of log dicts
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.analysis_id == analysis_id)
            .order_by(AuditLog.created_at.asc())
        )
        result = await self._session.execute(stmt)
        logs = result.scalars().all()

        return [
            {
                "id": log.id,
                "event_type": log.event_type,
                "payload": json.loads(log.payload),
                "created_at": log.created_at.isoformat(),
                "actor": log.actor,
            }
            for log in logs
        ]

    async def get_recent_errors(self, hours: int = 24) -> list[dict]:
        """Retrieve error events from the past N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of error log dicts
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            hours=hours
        )
        stmt = (
            select(AuditLog)
            .where((AuditLog.event_type == "error") & (AuditLog.created_at >= cutoff))
            .order_by(AuditLog.created_at.desc())
        )
        result = await self._session.execute(stmt)
        logs = result.scalars().all()

        return [
            {
                "id": log.id,
                "payload": json.loads(log.payload),
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ]
