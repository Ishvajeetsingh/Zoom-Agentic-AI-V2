import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WebhookEventListItem(BaseModel):
    id: uuid.UUID
    event_type: str
    zoom_event_id: str | None = None
    meeting_id: uuid.UUID | None = None
    status: str
    error_message: str | None = None
    received_at: datetime
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class WebhookEventDetailOut(WebhookEventListItem):
    request_body_sha256: str
    payload: dict = Field(default_factory=dict)
    headers: dict = Field(default_factory=dict)
    processing_run_ids: list[uuid.UUID] = Field(default_factory=list)


class WebhookEventListOut(BaseModel):
    items: list[WebhookEventListItem]
    total: int
    offset: int
    limit: int


class WebhookEventStatusCounts(BaseModel):
    status_counts: dict[str, int]
