"""Health endpoints for the standalone Atlas backend.

    GET /health            -> local liveness (configuration loadable)
    GET /health/upstream   -> reach Zoom Agentic AI's /health via the shared
                              HTTP base client (verifies ATLAS_API_BASE_URL)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.clients.base_http_client import BaseHTTPClient, AtlasAPIError
from app.core.config.settings import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    """Local liveness: configuration is loadable."""
    s = get_settings()
    return {
        "service": "standalone-atlas",
        "status": "ok",
        "upstream": s.atlas_api_base_url,
        "timeout": s.atlas_api_timeout,
        "max_retries": s.atlas_api_max_retries,
    }


@router.get("/health/upstream")
def upstream_health() -> dict[str, object]:
    """Ping Zoom Agentic AI's ``GET /api/v1/health`` via the HTTP base client.

    This validates the ``ATLAS_API_BASE_URL`` + auth wiring at runtime
    without any business logic or Zoom imports.
    """
    client = BaseHTTPClient()
    try:
        body = client.get("/health")
    except AtlasAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream Zoom Agentic AI unreachable: {exc}",
        ) from exc
    return {"upstream": "ok", "body": body}
