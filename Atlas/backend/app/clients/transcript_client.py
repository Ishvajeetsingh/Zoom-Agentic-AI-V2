"""Typed client for Zoom Agentic AI ``/transcripts`` routes.

Endpoints (verified against the baseline router):

    GET /api/v1/transcripts
    GET /api/v1/transcripts/{transcript_id}
    GET /api/v1/transcripts/{transcript_id}/questions

    (Other transcript sub-actions are intentionally NOT exposed here - they
    are pipeline mutation endpoints owned by the baseline. Standalone Atlas
    only consumes read paths for now.)
"""
from __future__ import annotations

from typing import Any, Mapping

from app.clients.base_http_client import BaseHTTPClient


class TranscriptClient(BaseHTTPClient):
    """HTTP client for the transcript read endpoints exposed by Zoom Agentic AI."""

    def list_transcripts(
        self,
        *,
        meeting_id: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """``GET /api/v1/transcripts``"""
        params: dict[str, Any] = {}
        if meeting_id is not None:
            params["meeting_id"] = meeting_id
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if extra:
            params.update(extra)
        return self.get("/transcripts", params=params or None)

    def get_transcript(self, transcript_id: str) -> Any:
        """``GET /api/v1/transcripts/{transcript_id}``"""
        return self.get(f"/transcripts/{transcript_id}")

    def get_questions(self, transcript_id: str) -> Any:
        """``GET /api/v1/transcripts/{transcript_id}/questions``"""
        return self.get(f"/transcripts/{transcript_id}/questions")
