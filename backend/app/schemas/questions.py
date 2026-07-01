"""Question API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class QuestionOut(BaseModel):
    id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    question_text: str
    question_type: str
    options: list
    correct_answer: str
    explanation: str
    difficulty: str
    is_valid: bool
    is_duplicate: bool
    duplicate_of: str | None = None
    category: str | None = None
    bloom_taxonomy: str | None = None
    educational_score: float | None = None
    relevance_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionListOut(BaseModel):
    items: list[QuestionOut]
    total: int
    offset: int
    limit: int
