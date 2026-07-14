"""Insights router.

Thin FastAPI layer that delegates to :class:`AtlasTranscriptService`
(every insight endpoint is per-transcript; the service exposes a 1:1 method
for each). No business logic, no Zoom imports.

All routes share the prefix ``/transcripts/{transcript_id}`` so they mirror
the baseline's ``/api/v1/transcripts/{transcript_id}/<insight>`` layout.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/transcripts", tags=["insights"])


def _svc(container: AtlasServiceContainer) -> Any:
    return container.transcript_service()


@router.get("/{transcript_id}/summary")
def get_summary(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_summary(transcript_id)


@router.get("/{transcript_id}/key-concepts")
def get_key_concepts(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_key_concepts(transcript_id)


@router.get("/{transcript_id}/action-items")
def get_action_items(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_action_items(transcript_id)


@router.get("/{transcript_id}/decisions")
def get_decisions(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_decisions(transcript_id)


@router.get("/{transcript_id}/recommendations")
def get_recommendations(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_recommendations(transcript_id)


@router.get("/{transcript_id}/outputs")
def get_outputs(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_outputs(transcript_id)


@router.get("/{transcript_id}/outputs/count")
def get_output_counts(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_output_counts(transcript_id)


@router.get("/{transcript_id}/learning-outcomes")
def get_learning_outcomes(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_learning_outcomes(transcript_id)


@router.get("/{transcript_id}/topics")
def get_topics(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_topics(transcript_id)


@router.get("/{transcript_id}/key-takeaways")
def get_key_takeaways(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_key_takeaways(transcript_id)


@router.get("/{transcript_id}/full-insights")
def get_full_insights(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    return _svc(container).get_full_insights(transcript_id)
