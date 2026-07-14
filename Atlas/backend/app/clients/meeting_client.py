"""Typed client for Zoom Agentic AI ``/meetings`` routes.

Endpoints (verified against the baseline router):

    GET /api/v1/meetings
    GET /api/v1/meetings/{meeting_id}

This client contains no business logic and no Zoom imports.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.clients.base_http_client import BaseHTTPClient


class MeetingClient(BaseHTTPClient):
    """HTTP client for the meeting endpoints exposed by Zoom Agentic AI."""

    def list_meetings(
        self,
        *,
        page: int | None = None,
        page_size: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """``GET /api/v1/meetings`` - paginated meeting list."""
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if extra:
            params.update(extra)
        return self.get("/meetings", params=params or None)

    def get_meeting(self, meeting_id: str) -> Any:
        """``GET /api/v1/meetings/{meeting_id}`` - single meeting detail."""
        return self.get(f"/meetings/{meeting_id}")
