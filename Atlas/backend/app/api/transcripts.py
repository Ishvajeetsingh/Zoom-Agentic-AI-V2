"""Transcripts router.

Thin FastAPI layer that delegates to
:meth:`AtlasTranscriptService.list_transcripts` /
:meth:`AtlasTranscriptService.get_transcript` /
:meth:`AtlasTranscriptService.get_questions`.

    GET /transcripts
    GET /transcripts/{transcript_id}
    GET /transcripts/{transcript_id}/questions
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


@router.get("")
def list_transcripts(
    meeting_id: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=200),
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /transcripts`` -> proxied to Zoom Agentic AI."""
    return container.transcript_service().list_transcripts(
        meeting_id=meeting_id, page=page, page_size=page_size
    )


@router.get("/{transcript_id}")
def get_transcript(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /transcripts/{transcript_id}`` -> proxied to Zoom Agentic AI."""
    return container.transcript_service().get_transcript(transcript_id)


@router.get("/{transcript_id}/questions")
def get_transcript_questions(
    transcript_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /transcripts/{transcript_id}/questions`` -> proxied to Zoom Agentic AI."""
    return container.transcript_service().get_questions(transcript_id)
