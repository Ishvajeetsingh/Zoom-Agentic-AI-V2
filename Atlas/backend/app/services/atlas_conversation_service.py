"""Atlas conversation service.

Orchestrates Zoom Agentic AI Atlas conversation CRUD + message lookup via
:class:`AtlasClient`. Conversation persistence (DB writes) and message
storage live entirely in the baseline — this service only composes REST
responses.

NOTE: the baseline ``chat`` and ``chat/stream`` endpoints ALREADY persist
both the user's message and the assistant's reply server-side. This
service therefore does NOT call ``add_message`` after chat — that would
duplicate user messages. ``add_message`` is exposed only for explicit
out-of-band message creation (used by future integrations that need to
append a message without invoking the LLM).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.clients.atlas_client import AtlasClient
from app.services._helpers import coerce_mapping


class AtlasConversationService:
    """Compose Atlas conversation REST responses from Zoom Agentic AI."""

    def __init__(self, atlas_client: AtlasClient) -> None:
        self._atlas = atlas_client

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------
    def list_conversations(
        self,
        *,
        meeting_id: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        """``GET /atlas/conversations``.

        Zoom Agentic AI's atlas router honours ``meeting_id``, ``offset`` and
        ``limit`` (see baseline ``atlas.py``). We assemble the right query
        params here; ``page``/``page_size`` are NOT the baseline's contract.
        """
        params: dict[str, Any] = {}
        if meeting_id is not None:
            params["meeting_id"] = meeting_id
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        if extra:
            params.update(extra)
        return self._atlas.list_conversations(extra=params or None)

    def create_conversation(self, *, payload: Mapping[str, Any]) -> Any:
        """``POST /atlas/conversations``."""
        return self._atlas.create_conversation(payload=payload)

    def get_conversation(self, conversation_id: str) -> Any:
        """``GET /atlas/conversations/{conversation_id}``.

        The baseline returns the conversation with its full message history
        inline (``messages`` field) — this is the conversation history.
        """
        return self._atlas.get_conversation(conversation_id)

    def patch_conversation(
        self, conversation_id: str, *, payload: Mapping[str, Any]
    ) -> Any:
        """``PATCH /atlas/conversations/{conversation_id}`` (title update)."""
        return self._atlas.patch_conversation(conversation_id, payload=payload)

    def delete_conversation(self, conversation_id: str) -> Any:
        """``DELETE /atlas/conversations/{conversation_id}``."""
        return self._atlas.delete_conversation(conversation_id)

    # ------------------------------------------------------------------
    # Message lookup / explicit append (NOT used by chat — chat persists
    # server-side in the baseline).
    # ------------------------------------------------------------------
    def get_messages(self, conversation_id: str) -> list[Any]:
        """Conversation history. Reuses ``GET /atlas/conversations/{id}``
        which returns ``messages`` inline.
        """
        detail = coerce_mapping(self._atlas.get_conversation(conversation_id))
        messages = detail.get("messages") or []
        return list(messages)

    def get_message_count(self, conversation_id: str) -> int:
        """Convenience: message count for a conversation."""
        detail = coerce_mapping(self._atlas.get_conversation(conversation_id))
        return int(detail.get("message_count") or 0)

    def add_message(
        self, conversation_id: str, *, payload: Mapping[str, Any]
    ) -> Any:
        """``POST /atlas/conversations/{conversation_id}/messages``.

        Explicit out-of-band append. Do NOT call this after ``chat`` — the
        baseline's chat endpoint already stores the user message.
        """
        return self._atlas.add_message(conversation_id, payload=payload)
