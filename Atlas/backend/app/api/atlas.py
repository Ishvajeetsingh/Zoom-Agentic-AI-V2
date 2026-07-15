"""Atlas conversation + chat router.

Thin FastAPI layer that delegates to:

- :class:`AtlasConversationService` for conversation CRUD and messages.
- :class:`AtlasChatService` for chat + chat/stream.

The streaming chat route proxies the upstream SSE stream byte-for-byte via
``StreamingResponse(media_type="text/event-stream")``. It does NOT buffer,
parse, regenerate or reframe the upstream frames and does NOT persist locally
(the baseline already stores both the user message and the finalized
assistant reply).

    POST   /atlas/conversations
    GET    /atlas/conversations
    GET    /atlas/conversations/{conversation_id}
    PATCH  /atlas/conversations/{conversation_id}
    DELETE /atlas/conversations/{conversation_id}
    POST   /atlas/conversations/{conversation_id}/messages
    POST   /atlas/conversations/{conversation_id}/chat
    POST   /atlas/conversations/{conversation_id}/chat/stream
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping

from fastapi import APIRouter, Body, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app.clients.base_http_client import AtlasAPIError
from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/atlas", tags=["atlas"])


# ---------------------------------------------------------------------------
# Bodies are deliberately permissive (``dict[str, Any]``): the schemas are
# owned by the baseline Atlas router, and Atlas must not duplicate them.
# The standalone frontend sends the same raw JSON bodies as the integrated
# frontend; older wrapper payloads are unwrapped for compatibility.
# ---------------------------------------------------------------------------
def _baseline_payload(body: Mapping[str, Any] | None) -> dict[str, Any]:
    if not body:
        return {}
    if set(body.keys()) == {"payload"} and isinstance(body.get("payload"), Mapping):
        return dict(body["payload"])
    return dict(body)


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------
@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: dict[str, Any] = Body(default_factory=dict),
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return container.conversation_service().create_conversation(
        payload=_baseline_payload(body)
    )


@router.get("/conversations")
def list_conversations(
    request: Request,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return container.conversation_service().list_conversations(
        extra=dict(request.query_params)
    )


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return container.conversation_service().get_conversation(conversation_id)


@router.patch("/conversations/{conversation_id}")
def patch_conversation(
    conversation_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return container.conversation_service().patch_conversation(
        conversation_id, payload=_baseline_payload(body)
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Response:
    container.conversation_service().delete_conversation(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    conversation_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """Explicit out-of-band message append.

    NOTE: do NOT call this after ``chat``/``chat_stream`` — the baseline
    chat endpoints already persist the user message server-side.
    """
    return container.conversation_service().add_message(
        conversation_id, payload=_baseline_payload(body)
    )


# ---------------------------------------------------------------------------
# Chat (non-streaming)
# ---------------------------------------------------------------------------
@router.post("/conversations/{conversation_id}/chat")
def chat(
    conversation_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``POST /atlas/conversations/{id}/chat`` -> proxied to Zoom Agentic AI.

    The baseline stores both the user message and the assistant reply; Atlas
    performs no local persistence.
    """
    return container.chat_service().chat(
        conversation_id, payload=_baseline_payload(body)
    )


# ---------------------------------------------------------------------------
# Chat (streaming) — raw SSE passthrough.
# ---------------------------------------------------------------------------
@router.post("/conversations/{conversation_id}/chat/stream")
def chat_stream(
    conversation_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    container: AtlasServiceContainer = Depends(get_container),
) -> StreamingResponse:
    """``POST /atlas/conversations/{id}/chat/stream`` -> raw SSE passthrough.

    Returns the upstream ``text/event-stream`` byte-for-byte:

    - No buffering.
    - No parsing / rewriting of JSON payloads.
    - No regenerating or re-framing of SSE events.
    - No local persistence (the baseline persists the finalized assistant
      reply in its own ``finally`` block).

    The iterator comes straight from
    :meth:`AtlasChatService.chat_stream`, which opens a ``stream=True``
    connection via :meth:`AtlasClient.chat_stream_raw` and yields the
    upstream ``data: ...`` frames exactly as the baseline emits them. The
    underlying ``requests.Response`` is closed when the generator is
    exhausted or closed (FastAPI calls ``close()`` on client disconnect).
    """
    try:
        iterator: Iterator[bytes] = container.chat_service().chat_stream(
            conversation_id, payload=_baseline_payload(body)
        )
    except AtlasAPIError as exc:
        # Surface upstream transport / HTTP errors before streaming starts.
        upstream_code = exc.status_code or status.HTTP_502_BAD_GATEWAY
        return Response(
            status_code=upstream_code,
            content=str(exc),
            media_type="text/plain",
        )
    return StreamingResponse(iterator, media_type="text/event-stream")
