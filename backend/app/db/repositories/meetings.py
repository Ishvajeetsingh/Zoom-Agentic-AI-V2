import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.meeting import Meeting
from app.db.models.question import Question
from app.db.models.transcript import Transcript


def get_by_zoom_uuid(
    db: Session,
    zoom_uuid: str | None,
) -> Meeting | None:
    if not zoom_uuid:
        return None

    return db.scalar(
        select(Meeting).where(
            Meeting.zoom_uuid == zoom_uuid
        )
    )


def upsert_zoom_meeting(
    db: Session,
    meeting_data: dict,
) -> Meeting:
    meeting = get_by_zoom_uuid(
        db,
        meeting_data.get("zoom_uuid"),
    )

    if meeting is None:
        meeting = Meeting()
        db.add(meeting)

    for key, value in meeting_data.items():
        setattr(meeting, key, value)

    db.flush()

    return meeting


def list_meetings(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    order_by: str = "created_at",
    order_desc: bool = False,
    source: str | None = None,
) -> tuple[list[Meeting], int]:

    query = select(Meeting)

    count_query = (
        select(func.count())
        .select_from(Meeting)
    )

    # Optional source filtering.
    #
    # Normal/full application:
    # source=None -> all meetings
    #
    # Public portfolio:
    # source="zoom" -> sanitized Zoom showcase only
    if source:
        query = query.where(
            Meeting.source == source
        )

        count_query = count_query.where(
            Meeting.source == source
        )

    order_column = getattr(
        Meeting,
        order_by,
        Meeting.created_at,
    )

    query = query.order_by(
        order_column.desc()
        if order_desc
        else order_column.asc()
    )

    query = (
        query
        .offset(offset)
        .limit(limit)
    )

    rows = db.scalars(query).all()

    total = (
        db.scalar(count_query)
        or 0
    )

    return rows, total


def get_meeting_detail(
    db: Session,
    meeting_id: uuid.UUID,
) -> dict | None:

    meeting = db.get(
        Meeting,
        meeting_id,
    )

    if meeting is None:
        return None

    transcript_count = db.scalar(
        select(func.count())
        .select_from(Transcript)
        .where(
            Transcript.meeting_id
            == meeting_id
        )
    )

    question_count = db.scalar(
        select(func.count())
        .select_from(Question)
        .where(
            Question.meeting_id
            == meeting_id
        )
    )

    return {
        "id": meeting.id,
        "source": meeting.source,
        "zoom_meeting_id":
            meeting.zoom_meeting_id,
        "zoom_uuid":
            meeting.zoom_uuid,
        "account_id":
            meeting.account_id,
        "host_id":
            meeting.host_id,
        "host_email":
            meeting.host_email,
        "topic":
            meeting.topic,
        "start_time":
            meeting.start_time,
        "timezone":
            meeting.timezone,
        "duration_minutes":
            meeting.duration_minutes,
        "participant_count":
            meeting.participant_count,
        "transcript_count":
            transcript_count,
        "question_count":
            question_count,
        "created_at":
            meeting.created_at,
        "updated_at":
            meeting.updated_at,
    }