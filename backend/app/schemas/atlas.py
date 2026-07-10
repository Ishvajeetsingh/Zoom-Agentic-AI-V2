"""Atlas (Meeting Intelligence Assistant) API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageIn(BaseModel):
    role: str
    content: str


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    id: uuid.UUID
    session_id: str | None = None
    meeting_id: uuid.UUID | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    meeting_id: uuid.UUID | None = None
    title: str | None = None
    session_id: str | None = None


class ConversationUpdate(BaseModel):
    title: str | None = None
    meeting_id: uuid.UUID | None = None
    session_id: str | None = None


class ConversationListOut(BaseModel):
    items: list[ConversationSummary]
    total: int
    offset: int
    limit: int
