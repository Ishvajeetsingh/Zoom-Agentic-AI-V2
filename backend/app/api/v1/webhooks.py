import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.integrations.zoom.webhook import (
    ZoomWebhookError,
    build_url_validation_response,
    verify_zoom_webhook_request,
)
from app.schemas.webhook_events import (
    WebhookEventDetailOut,
    WebhookEventListItem,
    WebhookEventListOut,
    WebhookEventStatusCounts,
)
from app.services.zoom_webhook_service import ZoomWebhookService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/zoom", status_code=status.HTTP_200_OK)
async def receive_zoom_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("zoom_webhook.invalid_json", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc

    try:
        verify_zoom_webhook_request(headers=request.headers, raw_body=raw_body)
    except ZoomWebhookError as exc:
        logger.warning("zoom_webhook.security_rejected", extra={"reason": str(exc)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ConfigurationError as exc:
        logger.error("zoom_webhook.configuration_error", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Zoom webhook verification is not configured",
        ) from exc

    if payload.get("event") == "endpoint.url_validation":
        logger.info("zoom_webhook.url_validation")
        try:
            return build_url_validation_response(payload)
        except (ZoomWebhookError, ConfigurationError) as exc:
            logger.warning("zoom_webhook.url_validation_failed", extra={"reason": str(exc)})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    service = ZoomWebhookService(db)
    try:
        result = service.handle_event(payload=payload, headers=dict(request.headers), raw_body=raw_body)
        return result
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_webhook.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store Zoom webhook metadata",
        ) from exc
    except ZoomWebhookError as exc:
        db.rollback()
        logger.warning("zoom_webhook.processing_error", extra={"reason": str(exc)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/events", response_model=WebhookEventListOut)
def list_webhook_events(
    event_type: str | None = Query(None),
    event_status: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> WebhookEventListOut:
    from app.db.repositories import webhook_events as webhook_events_repo

    rows, total = webhook_events_repo.list_events(
        db,
        event_type=event_type,
        status=event_status,
        offset=offset,
        limit=limit,
        order_desc=(order == "desc"),
    )
    items = [WebhookEventListItem.model_validate(r) for r in rows]
    return WebhookEventListOut(items=items, total=total, offset=offset, limit=limit)


@router.get("/events/status-counts", response_model=WebhookEventStatusCounts)
def get_webhook_event_status_counts(
    db: Session = Depends(get_db),
) -> WebhookEventStatusCounts:
    from app.db.repositories import webhook_events as webhook_events_repo

    counts = webhook_events_repo.count_by_status(db)
    return WebhookEventStatusCounts(status_counts=counts)


@router.get("/events/{event_id}", response_model=WebhookEventDetailOut)
def get_webhook_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> WebhookEventDetailOut:
    from app.db.models.processing_run import ProcessingRun
    from app.db.repositories import webhook_events as webhook_events_repo
    from sqlalchemy import select

    event = webhook_events_repo.get_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")

    run_ids = db.scalars(
        select(ProcessingRun.id).where(ProcessingRun.webhook_event_id == event_id)
    ).all()

    detail = WebhookEventDetailOut.model_validate(event)
    detail.processing_run_ids = list(run_ids)
    return detail
