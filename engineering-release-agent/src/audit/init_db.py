"""Async database initialization."""

from __future__ import annotations

import asyncio
import structlog

from sqlalchemy.ext.asyncio import create_async_engine

from src.audit.logger import Base
from src.config import get_settings

logger = structlog.get_logger(__name__)


async def init_db() -> None:
    """Create SQLite tables if they don't already exist."""
    settings = get_settings()
    engine = create_async_engine(settings.sqlite_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_initialised", db_path=settings.sqlite_db_path)


if __name__ == "__main__":
    asyncio.run(init_db())
    print("✅ Database initialised at", get_settings().sqlite_db_path)
