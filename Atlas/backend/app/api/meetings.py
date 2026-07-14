"""Meetings router.

Thin FastAPI layer that delegates to :class:`AtlasMeetingService`.
No business logic, no Zoom imports.

    GET /meetings
    GET /meetings/{meeting_id}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("")
def list_meetings(
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /meetings`` -> proxied to Zoom Agentic AI."""
    return container.meeting_service().list_meetings(
        page=page, page_size=page_size
    )


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /meetings/{meeting_id}`` -> proxied to Zoom Agentic AI."""
    return container.meeting_service().get_meeting(meeting_id)
