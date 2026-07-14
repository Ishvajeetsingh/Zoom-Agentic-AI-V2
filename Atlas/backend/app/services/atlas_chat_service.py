"""Atlas chat service.

Thin orchestration over :class:`AtlasClient` for the Atlas chat endpoints
exposed by Zoom Agentic AI:

    POST /api/v1/atlas/conversations/{conversation_id}/chat
    POST /api/v1/atlas/conversations/{conversation_id}/chat/stream

Both endpoints ALREADY persist the user's message and the assistant's reply
inside the baseline. This service therefore performs NO local persistence
and NO message storage — it only forwards requests and (for the streaming
route) forwards the upstream SSE frames byte-for-byte without buffering,
re-framing, or regenerating them.

Streaming strategy
------------------
``chat_stream`` opens a raw ``stream=True`` connection via
:meth:`AtlasClient.chat_stream_raw` and returns a generator that yields the
upstream ``data: ...`` frames exactly as the baseline emits them. The
underlying ``requests.Response`` is closed when the generator is exhausted
or explicitly closed (FastAPI's ``StreamingResponse`` calls ``close()`` on
the generator when the downstream client disconnects, which is where we
release the connection).
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping

from app.clients.atlas_client import AtlasClient
from app.core.logging import get_logger

logger = get_logger(__name__)


class AtlasChatService:
    """Compose Atlas chat REST responses from Zoom Agentic AI.

    This service holds no conversation memory and no prompt-building logic.
    Every call is a 1:1 REST pass-through. The baseline owns the LLM, the RAG
    citations, the prompt construction and the persistence of both the user
    message and the assistant reply.
    """

    def __init__(self, atlas_client: AtlasClient) -> None:
        self._atlas = atlas_client

    # ------------------------------------------------------------------
    # Non-streaming chat (the baseline stores the exchange server-side).
    # ------------------------------------------------------------------
    def chat(self, conversation_id: str, *, payload: Mapping[str, Any]) -> Any:
        """``POST /atlas/conversations/{conversation_id}/chat``.

        Returns the parsed JSON assistant reply produced by Zoom Agentic AI.
        No local persistence is performed — the baseline already stores the
        user message and the assistant message.
        """
        return self._atlas.chat(conversation_id, payload=payload)

    # ------------------------------------------------------------------
    # Streaming chat — raw SSE passthrough.
    # ------------------------------------------------------------------
    def chat_stream(
        self, conversation_id: str, *, payload: Mapping[str, Any]
    ) -> Iterator[bytes]:
        """``POST /atlas/conversations/{conversation_id}/chat/stream``.

        Opens a streaming connection to the baseline and yields SSE frames
        exactly as the baseline emits them (``data: {json}\\n\\n``). The
        generator:

        - Does NOT buffer the full response.
        - Does NOT parse or rewrite the JSON payloads.
        - Does NOT regenerate or re-frame the SSE events.
        - Does NOT persist anything locally (the baseline persists the
          finalized assistant message in the ``finally`` block of its own
          generator — see ``atlas.py:chat_with_llm_stream``).
        - Releases the upstream HTTP connection when iteration completes or
          the generator is closed (client disconnect).

        Yields ``bytes`` so the downstream FastAPI ``StreamingResponse`` can
        emit them over the wire without re-encoding. The media type of the
        upstream response is ``text/event-stream`` and we preserve it.
        """
        response = self._atlas.chat_stream_raw(conversation_id, payload=payload)
        try:
            for frame in self._atlas.iter_sse_frames(response):
                yield frame
        finally:
            try:
                response.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup on disconnect
                logger.debug(
                    "atlas_chat.stream_close_failed",
                    extra={"conversation_id": conversation_id},
                )
