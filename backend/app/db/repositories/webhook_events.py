import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.webhook_event import WebhookEvent


def get_existing_event(
    db: Session, zoom_event_id: str | None, request_body_sha256: str
) -> WebhookEvent | None:
    conditions = [WebhookEvent.request_body_sha256 == request_body_sha256]
    if zoom_event_id:
        conditions.append(WebhookEvent.zoom_event_id == zoom_event_id)
    return db.scalar(select(WebhookEvent).where(or_(*conditions)).limit(1))


def get_existing_event_for_update(
    db: Session, zoom_event_id: str | None, request_body_sha256: str
) -> WebhookEvent | None:
    conditions = [WebhookEvent.request_body_sha256 == request_body_sha256]
    if zoom_event_id:
        conditions.append(WebhookEvent.zoom_event_id == zoom_event_id)
    return db.scalar(
        select(WebhookEvent).where(or_(*conditions)).limit(1).with_for_update()
    )


def create_event(
    db: Session,
    *,
    event_type: str,
    zoom_event_id: str | None,
    request_body_sha256: str,
    payload: dict,
    headers: dict,
    status: str = "received",
) -> WebhookEvent:
    event = WebhookEvent(
        event_type=event_type,
        zoom_event_id=zoom_event_id,
        request_body_sha256=request_body_sha256,
        payload=payload,
        headers=headers,
        status=status,
    )
    db.add(event)
    db.flush()
    return event


def mark_processed(db: Session, event: WebhookEvent, *, meeting_id=None, status: str = "processed") -> None:
    event.status = status
    event.meeting_id = meeting_id
    event.processed_at = datetime.now(UTC)
    db.flush()


def mark_failed(db: Session, event: WebhookEvent, error_message: str) -> None:
    event.status = "failed"
    event.error_message = error_message
    event.processed_at = datetime.now(UTC)
    db.flush()


def mark_processing(db: Session, event: WebhookEvent) -> None:
    event.status = "processing"
    db.flush()


def get_by_id(db: Session, event_id: uuid.UUID) -> WebhookEvent | None:
    return db.get(WebhookEvent, event_id)


def list_events(
    db: Session,
    *,
    event_type: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
    order_desc: bool = True,
) -> tuple[list[WebhookEvent], int]:
    query = select(WebhookEvent)
    count_query = select(func.count()).select_from(WebhookEvent)

    if event_type is not None:
        query = query.where(WebhookEvent.event_type == event_type)
        count_query = count_query.where(WebhookEvent.event_type == event_type)
    if status is not None:
        query = query.where(WebhookEvent.status == status)
        count_query = count_query.where(WebhookEvent.status == status)

    order_col = WebhookEvent.received_at.desc() if order_desc else WebhookEvent.received_at.asc()
    query = query.order_by(order_col).offset(offset).limit(limit)

    rows = db.scalars(query).all()
    total = db.scalar(count_query)
    return rows, total


def count_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(WebhookEvent.status, func.count(WebhookEvent.id))
        .group_by(WebhookEvent.status)
    ).all()
    return {row[0]: row[1] for row in rows}
