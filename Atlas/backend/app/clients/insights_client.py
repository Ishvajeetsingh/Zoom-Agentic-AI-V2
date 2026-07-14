"""Typed client for Zoom Agentic AI insights routes.

The insights router shares the ``transcripts`` prefix with the transcripts
router (verified in ``backend/app/api/router.py``), so every insight path
looks like ``/api/v1/transcripts/{transcript_id}/<insight>``.

Endpoints exposed:

    GET /api/v1/transcripts/{transcript_id}/summary
    GET /api/v1/transcripts/{transcript_id}/key-concepts
    GET /api/v1/transcripts/{transcript_id}/action-items
    GET /api/v1/transcripts/{transcript_id}/outputs
    GET /api/v1/transcripts/{transcript_id}/outputs/count
    GET /api/v1/transcripts/{transcript_id}/key-takeaways
    GET /api/v1/transcripts/{transcript_id}/learning-outcomes
    GET /api/v1/transcripts/{transcript_id}/topics
    GET /api/v1/transcripts/{transcript_id}/decisions
    GET /api/v1/transcripts/{transcript_id}/recommendations
    GET /api/v1/transcripts/{transcript_id}/full-insights
"""
from __future__ import annotations

from app.clients.base_http_client import BaseHTTPClient


class InsightsClient(BaseHTTPClient):
    """HTTP client for the per-transcript insight endpoints exposed by
    Zoom Agentic AI. Each method is a 1:1 GET wrapper.
    """

    def get_summary(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/summary")

    def get_key_concepts(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/key-concepts")

    def get_action_items(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/action-items")

    def get_outputs(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/outputs")

    def get_output_counts(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/outputs/count")

    def get_key_takeaways(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/key-takeaways")

    def get_learning_outcomes(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/learning-outcomes")

    def get_topics(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/topics")

    def get_decisions(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/decisions")

    def get_recommendations(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/recommendations")

    def get_full_insights(self, transcript_id: str) -> "object":
        return self.get(f"/transcripts/{transcript_id}/full-insights")
