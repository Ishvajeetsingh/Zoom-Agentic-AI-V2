"""Atlas meeting service.

Orchestrates Zoom Agentic AI ``/meetings`` endpoints via
:class:`MeetingClient`. Pure pass-through — no business logic.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.clients.meeting_client import MeetingClient
from app.services._helpers import coerce_mapping


class AtlasMeetingService:
    """Compose meeting-level REST responses from Zoom Agentic AI."""

    def __init__(self, meeting_client: MeetingClient) -> None:
        self._meetings = meeting_client

    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------
    def list_meetings(
        self,
        *,
        page: int | None = None,
        page_size: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        return self._meetings.list_meetings(
            page=page, page_size=page_size, extra=extra
        )

    def get_meeting(self, meeting_id: str) -> Any:
        return self._meetings.get_meeting(meeting_id)

    # ------------------------------------------------------------------
    # Convenience: meeting + its ranked questions in one round trip client-
    # side (composition over HTTP). Ranking logic still lives in the baseline.
    # ------------------------------------------------------------------
    def get_meeting_with_ranked_questions(
        self,
        meeting_id: str,
        *,
        top_k: int | None = None,
        category: str | None = None,
        ranking_client: "Any",
    ) -> dict[str, Any]:
        """Fetch a meeting and its professor-ranked questions in one call.

        ``ranking_client`` is expected to be a :class:`RankingClient`
        instance. It is injected (rather than imported on this service) so
        the orchestration layer is the only thing that knows which client
        graph to assemble.
        """
        meeting = coerce_mapping(self._meetings.get_meeting(meeting_id))
        ranked = ranking_client.get_meeting_ranked_questions(
            meeting_id, top_k=top_k, category=category
        )
        return {"meeting": meeting, "ranked_questions": ranked}
