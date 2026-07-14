"""Typed client for Zoom Agentic AI semantic retrieval route.

Endpoint (verified against the Phase 2 ``atlas_proxy`` router):

    POST /api/v1/retrieval/search

Request body (matches ``RetrievalRequest`` in ``atlas_proxy``):
    {
      "meeting_id": "<uuid>",
      "query":      "<text>",
      "top_k":      <optional int>
    }

Response matches ``RetrievalSearchOut`` with the deduplicated,
similarity-ranked chunks. The retrieval algorithm itself is owned by Zoom
Agentic AI (``EmbeddingService`` + ``ChunkEmbeddingStore`` +
``SemanticRetrievalService``); this client only transports requests and
responses.
"""
from __future__ import annotations

from typing import Any

from app.clients.base_http_client import BaseHTTPClient


class RetrievalClient(BaseHTTPClient):
    """HTTP client for semantic retrieval over the Zoom Agentic AI baseline."""

    def search(
        self,
        meeting_id: str,
        query: str,
        *,
        top_k: int | None = None,
    ) -> Any:
        """``POST /api/v1/retrieval/search``"""
        if not query:
            raise ValueError("query must not be empty")
        body: dict[str, Any] = {"meeting_id": meeting_id, "query": query}
        if top_k is not None:
            body["top_k"] = top_k
        return self.post("/retrieval/search", json_body=body)
