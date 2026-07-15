"""Typed client for Zoom Agentic AI Atlas conversation/chat routes.

Endpoints (verified against the baseline atlas router under
``/api/v1/atlas``):

    POST   /api/v1/atlas/conversations
    GET    /api/v1/atlas/conversations
    GET    /api/v1/atlas/conversations/{conversation_id}
    PATCH  /api/v1/atlas/conversations/{conversation_id}
    DELETE /api/v1/atlas/conversations/{conversation_id}
    POST   /api/v1/atlas/conversations/{conversation_id}/messages
    POST   /api/v1/atlas/conversations/{conversation_id}/chat
    POST   /api/v1/atlas/conversations/{conversation_id}/chat/stream

Streaming responses ("chat/stream") are returned as raw parsed JSON here
for now - Phase 4 wiring will handle the SSE/upstream stream transport
correctly. The current scaffold only needs the typed surface.
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping

import requests

from app.clients.base_http_client import BaseHTTPClient


class AtlasClient(BaseHTTPClient):
    """HTTP client for the Atlas conversation endpoints exposed by Zoom
    Agentic AI. Every method is a thin 1:1 REST wrapper.
    """

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------
    def list_conversations(
        self,
        *,
        page: int | None = None,
        page_size: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """``GET /api/v1/atlas/conversations``"""
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if extra:
            params.update(extra)
        return self.get("/atlas/conversations", params=params or None)

    def create_conversation(self, *, payload: Mapping[str, Any]) -> Any:
        """``POST /api/v1/atlas/conversations``"""
        return self.post("/atlas/conversations", json_body=dict(payload))

    def get_conversation(self, conversation_id: str) -> Any:
        """``GET /api/v1/atlas/conversations/{conversation_id}``"""
        return self.get(f"/atlas/conversations/{conversation_id}")

    def patch_conversation(
        self, conversation_id: str, *, payload: Mapping[str, Any]
    ) -> Any:
        """``PATCH /api/v1/atlas/conversations/{conversation_id}``"""
        return self.patch(
            f"/atlas/conversations/{conversation_id}", json_body=dict(payload)
        )

    def delete_conversation(self, conversation_id: str) -> Any:
        """``DELETE /api/v1/atlas/conversations/{conversation_id}`` (returns None on 204)."""
        return self.delete(f"/atlas/conversations/{conversation_id}")

    # ------------------------------------------------------------------
    # Messages / chat
    # ------------------------------------------------------------------
    def add_message(
        self, conversation_id: str, *, payload: Mapping[str, Any]
    ) -> Any:
        """``POST /api/v1/atlas/conversations/{conversation_id}/messages``"""
        return self.post(
            f"/atlas/conversations/{conversation_id}/messages",
            json_body=dict(payload),
        )

    def chat(self, conversation_id: str, *, payload: Mapping[str, Any]) -> Any:
        """``POST /api/v1/atlas/conversations/{conversation_id}/chat``"""
        return self.post(
            f"/atlas/conversations/{conversation_id}/chat", json_body=dict(payload)
        )

    def chat_stream(self, conversation_id: str, *, payload: Mapping[str, Any]) -> Any:
        """``POST /api/v1/atlas/conversations/{conversation_id}/chat/stream``

        NOTE: Phase 3 returns parsed JSON. Phase 4 will surface the
        upstream streaming response as an iterator over SSE-style chunks.
        """
        return self.post(
            f"/atlas/conversations/{conversation_id}/chat/stream",
            json_body=dict(payload),
        )

    # ------------------------------------------------------------------
    # Streaming (Phase 5)
    # ------------------------------------------------------------------
    def chat_stream_raw(
        self, conversation_id: str, *, payload: Mapping[str, Any]
    ) -> "requests.Response":
        """Open a raw streaming connection to the baseline's
        ``chat/stream`` endpoint and return the live ``requests.Response``.

        The response is yielded with ``stream=True`` so callers can iterate
        ``response.iter_content`` / ``iter_lines`` without buffering the
        entire body. The connection is NOT closed here — the caller (the
        FastAPI streaming route) is responsible for using it inside a
        ``with`` / ``finally`` block so it is released when the client
        disconnects.

        Raises :class:`AtlasAPIError` on any non-2xx upstream status.
        """
        url = self._url(
            f"/atlas/conversations/{conversation_id}/chat/stream"
        )
        try:
            response = self._session.post(
                url,
                json=dict(payload),
                headers=self._headers(),
                timeout=self.timeout,
                stream=True,
            )
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            from app.clients.base_http_client import AtlasAPIError

            raise AtlasAPIError(
                f"chat/stream transport error: {exc}"
            ) from exc

        if not (200 <= response.status_code < 300):
            body: Any = None
            try:
                body = response.json()
            except ValueError:
                body = response.text
            from app.clients.base_http_client import AtlasAPIError

            raise AtlasAPIError(
                f"chat/stream -> {response.status_code}",
                status_code=response.status_code,
                body=body,
            )
        return response

    @staticmethod
    def iter_sse_frames(
        response: "requests.Response",
    ) -> Iterator[bytes]:
        """Yield raw SSE frames from an upstream streaming response.

        The baseline emits ``data: <json>\\n\\n`` frames; we forward each
        line as-is (including the trailing newline) so the downstream
        client receives byte-identical frames at the same pace the
        baseline produces them. No re-framing, no buffering of multiple
        events, no regeneration.
        """
        # ``iter_lines`` strips the newline; re-append ``\\n\\n`` so we
        # preserve the exact SSE framing the baseline sends. We only
        # forward non-empty lines (SSE comments/pings are empty).
        for raw in response.iter_lines(decode_unicode=False):
            if not raw:
                continue
            if raw.startswith(b"data:"):
                yield raw + b"\n\n"
            else:
                # Unknown frame type: forward verbatim with same framing.
                yield raw + b"\n\n"
