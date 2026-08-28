"""Meeting API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class MeetingListItem(BaseModel):
    id: uuid.UUID
    source: str
    zoom_meeting_id: str | None = None
    zoom_uuid: str | None = None
    topic: str | None = None
    start_time: datetime | None = None
    timezone: str | None = None
    duration_minutes: int | None = None
    participant_count: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class PublicMeetingListItem(BaseModel):
    """
    Safe meeting metadata exposed by the public portfolio demo.

    Intentionally excludes:
    - Zoom meeting ID
    - Zoom UUID
    - Zoom account ID
    - host ID
    - host email
    - participant information
    - transcript contents
    """

    id: uuid.UUID
    source: str
    topic: str | None = None
    start_time: datetime | None = None
    duration_minutes: int | None = None

    model_config = {"from_attributes": True}

class PublicMeetingListOut(BaseModel):
    items: list[PublicMeetingListItem]
    total: int
    offset: int
    limit: int    

class MeetingListOut(BaseModel):
    items: list[MeetingListItem]
    total: int
    offset: int
    limit: int


class MeetingDetailOut(BaseModel):
    id: uuid.UUID
    source: str
    zoom_meeting_id: str | None = None
    zoom_uuid: str | None = None
    account_id: str | None = None
    host_id: str | None = None
    host_email: str | None = None
    topic: str | None = None
    start_time: datetime | None = None
    timezone: str | None = None
    duration_minutes: int | None = None
    participant_count: int | None = None
    transcript_count: int
    question_count: int
    created_at: datetime
    updated_at: datetime
