"""Atlas transcript service.

Orchestrates Zoom Agentic AI ``/transcripts`` and per-transcript insight
endpoints via :class:`TranscriptClient` and :class:`InsightsClient`.
Pure pass-through — no business logic.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.clients.insights_client import InsightsClient
from app.clients.transcript_client import TranscriptClient
from app.services._helpers import coerce_mapping


class AtlasTranscriptService:
    """Compose transcript + insight REST responses from Zoom Agentic AI."""

    def __init__(
        self,
        transcript_client: TranscriptClient,
        insights_client: InsightsClient,
    ) -> None:
        self._transcripts = transcript_client
        self._insights = insights_client

    # ------------------------------------------------------------------
    # Transcripts
    # ------------------------------------------------------------------
    def list_transcripts(
        self,
        *,
        meeting_id: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Any:
        return self._transcripts.list_transcripts(
            meeting_id=meeting_id, page=page, page_size=page_size, extra=extra
        )

    def get_transcript(self, transcript_id: str) -> Any:
        return self._transcripts.get_transcript(transcript_id)

    def get_questions(self, transcript_id: str) -> Any:
        """Stored (non-ranked) questions for a transcript."""
        return self._transcripts.get_questions(transcript_id)

    # ------------------------------------------------------------------
    # Insights (per-transcript GETs)
    # ------------------------------------------------------------------
    def get_summary(self, transcript_id: str) -> Any:
        return self._insights.get_summary(transcript_id)

    def get_key_concepts(self, transcript_id: str) -> Any:
        return self._insights.get_key_concepts(transcript_id)

    def get_action_items(self, transcript_id: str) -> Any:
        return self._insights.get_action_items(transcript_id)

    def get_outputs(self, transcript_id: str) -> Any:
        return self._insights.get_outputs(transcript_id)

    def get_output_counts(self, transcript_id: str) -> Any:
        return self._insights.get_output_counts(transcript_id)

    def get_key_takeaways(self, transcript_id: str) -> Any:
        return self._insights.get_key_takeaways(transcript_id)

    def get_learning_outcomes(self, transcript_id: str) -> Any:
        return self._insights.get_learning_outcomes(transcript_id)

    def get_topics(self, transcript_id: str) -> Any:
        return self._insights.get_topics(transcript_id)

    def get_decisions(self, transcript_id: str) -> Any:
        return self._insights.get_decisions(transcript_id)

    def get_recommendations(self, transcript_id: str) -> Any:
        return self._insights.get_recommendations(transcript_id)

    def get_full_insights(self, transcript_id: str) -> Any:
        return self._insights.get_full_insights(transcript_id)

    # ------------------------------------------------------------------
    # Composition: transcript + all its insights in one call client-side.
    # ------------------------------------------------------------------
    def get_transcript_with_insights(self, transcript_id: str) -> dict[str, Any]:
        """Fetch a transcript and its ``full-insights`` snapshot together.

        ``full-insights`` is the single round-trip endpoint that the
        baseline exposes precisely for this; we just pair it with the
        transcript record — no aggregation logic on our side.
        """
        transcript = coerce_mapping(self._transcripts.get_transcript(transcript_id))
        insights = self._insights.get_full_insights(transcript_id)
        return {"transcript": transcript, "insights": insights}
