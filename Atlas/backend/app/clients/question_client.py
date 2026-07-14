"""Typed client for Zoom Agentic AI ``/questions`` routes.

Endpoints (verified against the baseline router):

    GET /api/v1/questions/{question_id}
"""
from __future__ import annotations

from app.clients.base_http_client import BaseHTTPClient


class QuestionClient(BaseHTTPClient):
    """HTTP client for the question lookup endpoints exposed by Zoom Agentic AI."""

    def get_question(self, question_id: str) -> "object":
        """``GET /api/v1/questions/{question_id}``"""
        return self.get(f"/questions/{question_id}")
