"""Retrieval router.

Thin FastAPI layer that delegates to
:meth:`AtlasQuestionService.search` (which in turn proxies
``POST /api/v1/retrieval/search`` on Zoom Agentic AI).

    POST /retrieval/search
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class RetrievalSearchRequest(BaseModel):
    """Body for ``POST /retrieval/search``. Mirrors the baseline's
    ``RetrievalRequest`` schema (``meeting_id`` + ``query`` + optional
    ``top_k``). No defaults are invented here — anything the client omits
    is omitted from the upstream body too.
    """

    meeting_id: str
    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=200)


@router.post("/search")
def search(
    body: RetrievalSearchRequest,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``POST /retrieval/search`` -> proxied to Zoom Agentic AI.

    The embedding + similarity ranking are owned by the baseline
    (``EmbeddingService`` + ``SemanticRetrievalService``). Atlas only
    transports the request and the response.
    """
    return container.question_service().search(
        body.meeting_id, body.query, top_k=body.top_k
    )
