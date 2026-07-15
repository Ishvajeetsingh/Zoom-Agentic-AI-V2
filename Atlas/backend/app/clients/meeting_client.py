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
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """``GET /api/v1/meetings`` - paginated meeting list."""
        return self.get("/meetings", params=extra or None)

    def get_meeting(self, meeting_id: str) -> Any:
        """``GET /api/v1/meetings/{meeting_id}`` - single meeting detail."""
        return self.get(f"/meetings/{meeting_id}")
