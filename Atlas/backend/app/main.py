"""Minimal FastAPI entrypoint for the standalone Atlas backend.

Phase 3 scope: expose a ``/health`` endpoint that proves the app boots and
the configuration is loadable, plus a small ``/health/upstream`` endpoint
that pings Zoom Agentic AI's ``/health`` route through the shared HTTP
base client (so wiring is verifiable without any business logic).

Nothing here imports Zoom Agentic AI internals.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, status

from app.api.atlas import router as atlas_router
from app.api.health import router as health_router
from app.api.insights import router as insights_router
from app.api.meetings import router as meetings_router
from app.api.questions import router as questions_router
from app.api.retrieval import router as retrieval_router
from app.api.transcripts import router as transcripts_router
from app.core.config.settings import get_settings, reset_settings
from app.core.logging import configure_logging

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    """Factory used by the ASGI server and tests."""
    settings = get_settings()
    configure_logging(settings.atlas_log_level)

    app = FastAPI(
        title="Standalone Atlas",
        description="Thick client for the Zoom Agentic AI REST API. "
        "Does not import Zoom Agentic AI internals.",
        version="0.1.0",
    )

    app.include_router(health_router, tags=["health"])
    app.include_router(meetings_router)
    app.include_router(transcripts_router)
    app.include_router(questions_router)
    app.include_router(insights_router)
    app.include_router(retrieval_router)
    app.include_router(atlas_router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "standalone-atlas", "status": "ok"}

    return app


app = create_app()


def reset_app() -> None:
    """Test hook - drop cached settings/app so a fresh app uses new env vars."""
    global app
    reset_settings()
    app = create_app()
