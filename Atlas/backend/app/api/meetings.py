"""Meetings router.

Thin FastAPI layer that delegates to :class:`AtlasMeetingService`.
No business logic, no Zoom imports.

    GET /meetings
    GET /meetings/{meeting_id}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("")
def list_meetings(
    request: Request,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /meetings`` -> proxied to Zoom Agentic AI."""
    return container.meeting_service().list_meetings(
        extra=dict(request.query_params)
    )


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /meetings/{meeting_id}`` -> proxied to Zoom Agentic AI."""
    return container.meeting_service().get_meeting(meeting_id)
