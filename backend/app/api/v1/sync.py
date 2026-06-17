import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.db.repositories import sync as sync_repo
from app.db.repositories import zoom_accounts as zoom_account_repo

router = APIRouter()
logger = get_logger(__name__)


class SyncConfigUpdate(BaseModel):
    auto_sync_enabled: bool | None = None
    sync_interval_minutes: int | None = Field(None, ge=5, le=1440)
    lookback_days: int | None = Field(None, ge=1, le=365)
    auto_process: bool | None = None


class SyncConfigOut(BaseModel):
    id: uuid.UUID
    zoom_account_id: uuid.UUID
    auto_sync_enabled: bool
    sync_interval_minutes: int
    lookback_days: int
    auto_process: bool
    last_sync_at: str | None
    last_sync_status: str | None
    last_sync_error: str | None
    created_at: str
    updated_at: str


class SyncHistoryOut(BaseModel):
    id: uuid.UUID
    zoom_account_id: uuid.UUID
    sync_type: str
    status: str
    meetings_discovered: int
    transcripts_discovered: int
    transcripts_queued: int
    error_message: str | None
    started_at: str
    completed_at: str | None
    duration_seconds: float | None


class SyncHistoryListOut(BaseModel):
    items: list[SyncHistoryOut]
    total: int


class SyncNowResponse(BaseModel):
    success: bool
    message: str
    sync_history_id: str | None = None


def _config_to_out(config) -> SyncConfigOut:
    return SyncConfigOut(
        id=config.id,
        zoom_account_id=config.zoom_account_id,
        auto_sync_enabled=config.auto_sync_enabled,
        sync_interval_minutes=config.sync_interval_minutes,
        lookback_days=config.lookback_days,
        auto_process=config.auto_process,
        last_sync_at=str(config.last_sync_at) if config.last_sync_at else None,
        last_sync_status=config.last_sync_status,
        last_sync_error=config.last_sync_error,
        created_at=str(config.created_at),
        updated_at=str(config.updated_at),
    )


def _history_to_out(entry) -> SyncHistoryOut:
    return SyncHistoryOut(
        id=entry.id,
        zoom_account_id=entry.zoom_account_id,
        sync_type=entry.sync_type,
        status=entry.status,
        meetings_discovered=entry.meetings_discovered,
        transcripts_discovered=entry.transcripts_discovered,
        transcripts_queued=entry.transcripts_queued,
        error_message=entry.error_message,
        started_at=str(entry.started_at),
        completed_at=str(entry.completed_at) if entry.completed_at else None,
        duration_seconds=entry.duration_seconds,
    )


@router.get("/config/{account_id}", response_model=SyncConfigOut)
def get_sync_config(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SyncConfigOut:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    config = sync_repo.get_sync_config_by_account(db, account_id)
    if config is None:
        config = sync_repo.upsert_sync_config(db, zoom_account_id=account_id, auto_sync_enabled=False)
        db.commit()
    return _config_to_out(config)


@router.put("/config/{account_id}", response_model=SyncConfigOut)
def update_sync_config(
    account_id: uuid.UUID,
    request: SyncConfigUpdate,
    db: Session = Depends(get_db),
) -> SyncConfigOut:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    config = sync_repo.upsert_sync_config(
        db,
        zoom_account_id=account_id,
        auto_sync_enabled=request.auto_sync_enabled,
        sync_interval_minutes=request.sync_interval_minutes,
        lookback_days=request.lookback_days,
        auto_process=request.auto_process,
    )
    db.commit()
    return _config_to_out(config)


@router.post("/now/{account_id}", response_model=SyncNowResponse)
def sync_now(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SyncNowResponse:
    account = zoom_account_repo.get_by_id(db, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zoom account not found")
    if not account.enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zoom account is disabled")

    from app.services.sync_service import SyncService
    service = SyncService()
    try:
        result = service.run_sync_for_account(account_id)
    except Exception as exc:
        logger.exception("sync_now.error", extra={"account_id": str(account_id)})
        return SyncNowResponse(
            success=False,
            message=f"Sync failed: {exc}",
        )

    return SyncNowResponse(
        success=True,
        message=f"Sync completed: {result.meetings_discovered} meetings, {result.transcripts_discovered} transcripts, {result.transcripts_queued} queued",
        sync_history_id=str(result.history_id) if result.history_id else None,
    )


@router.get("/history", response_model=SyncHistoryListOut)
def list_sync_history(
    account_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SyncHistoryListOut:
    rows, total = sync_repo.list_sync_history(db, zoom_account_id=account_id, offset=offset, limit=limit)
    return SyncHistoryListOut(
        items=[_history_to_out(h) for h in rows],
        total=total,
    )


@router.post("/all", response_model=SyncNowResponse)
def sync_all_enabled(
    db: Session = Depends(get_db),
) -> SyncNowResponse:
    from app.services.sync_service import SyncService
    service = SyncService()
    try:
        result = service.run_sync_all_enabled()
    except Exception as exc:
        logger.exception("sync_all.error")
        return SyncNowResponse(
            success=False,
            message=f"Sync failed: {exc}",
        )

    return SyncNowResponse(
        success=True,
        message=f"Synced {result.accounts_processed} accounts: {result.total_meetings} meetings, {result.total_transcripts} transcripts, {result.total_queued} queued",
    )
