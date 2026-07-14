"""Typed client for Zoom Agentic AI ranked-questions routes.

Both endpoints are exposed by the Phase 2 ``atlas_proxy`` router (verified
in ``backend/app/api/v1/atlas_proxy.py``); they sit at the v1 *root*, not
under ``/meetings`` or ``/transcripts`` routers.

    GET /api/v1/meetings/{meeting_id}/ranked-questions
    GET /api/v1/transcripts/{transcript_id}/ranked-questions

Query parameters supported by both:
    top_k    (int, optional, 1..100)
    category (str, optional)

The ranking itself is owned by Zoom Agentic AI's ``ProfessorRankingService``
(unchanged); this client only transports its output.
"""
from __future__ import annotations

from typing import Any

from app.clients.base_http_client import BaseHTTPClient


class RankingClient(BaseHTTPClient):
    """HTTP client for professor-ranked questions endpoints."""

    def get_meeting_ranked_questions(
        self,
        meeting_id: str,
        *,
        top_k: int | None = None,
        category: str | None = None,
    ) -> Any:
        """``GET /api/v1/meetings/{meeting_id}/ranked-questions``"""
        params = self._build_params(top_k=top_k, category=category)
        return self.get(
            f"/meetings/{meeting_id}/ranked-questions", params=params or None
        )

    def get_transcript_ranked_questions(
        self,
        transcript_id: str,
        *,
        top_k: int | None = None,
        category: str | None = None,
    ) -> Any:
        """``GET /api/v1/transcripts/{transcript_id}/ranked-questions``"""
        params = self._build_params(top_k=top_k, category=category)
        return self.get(
            f"/transcripts/{transcript_id}/ranked-questions", params=params or None
        )

    @staticmethod
    def _build_params(top_k: int | None, category: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if top_k is not None:
            params["top_k"] = top_k
        if category is not None:
            params["category"] = category
        return params
