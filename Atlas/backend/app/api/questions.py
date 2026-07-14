"""Questions router.

Thin FastAPI layer that delegates to
:meth:`AtlasQuestionService.get_question`.

    GET /questions/{question_id}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.services import AtlasServiceContainer, get_container

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/{question_id}")
def get_question(
    question_id: str,
    container: AtlasServiceContainer = Depends(get_container),
) -> Any:
    """``GET /questions/{question_id}`` -> proxied to Zoom Agentic AI."""
    return container.question_service().get_question(question_id)
