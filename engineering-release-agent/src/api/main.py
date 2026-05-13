"""FastAPI application factory."""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console
from rich.panel import Panel

from src.api.routes.analyze import router as analyze_router
from src.api.routes.review import router as review_router
from src.api.routes.webhook import router as webhook_router
from src.audit.init_db import init_db
from src.config import get_settings

logger = structlog.get_logger(__name__)
console = Console()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    settings = get_settings()

    # Startup
    await init_db()
    console.print(
        Panel(
            f"[bold cyan]Engineering Release Agent[/bold cyan]\n"
            f"LLM:  {settings.llm_provider} "
            f"({'ollama: ' + settings.ollama_model if settings.use_ollama else 'openai: ' + settings.openai_model})\n"
            f"DB:   {settings.sqlite_db_path}\n"
            f"RAG:  {settings.chroma_persist_dir}\n"
            f"Docs: [link=http://localhost:8000/docs]http://localhost:8000/docs[/link]",
            title="🚀 Agent Started",
            border_style="green",
        )
    )

    yield

    # Shutdown
    logger.info("agent_shutdown")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    application = FastAPI(
        title="Engineering Release Agent",
        description="AI agent that analyses PR diffs and produces actionable release feedback",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    application.include_router(analyze_router)
    application.include_router(webhook_router)
    application.include_router(review_router)

    # Health check
    @application.get("/health")
    async def health_check():
        """Health check endpoint."""
        settings = get_settings()
        return {
            "status": "ok",
            "version": "0.1.0",
            "environment": settings.environment,
            "llm_provider": settings.llm_provider,
        }

    return application


app = create_app()
