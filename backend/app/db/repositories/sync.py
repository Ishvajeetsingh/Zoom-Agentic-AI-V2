import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.sync import SyncConfig, SyncHistory


def get_sync_config_by_account(db: Session, zoom_account_id: uuid.UUID) -> SyncConfig | None:
    return db.scalar(select(SyncConfig).where(SyncConfig.zoom_account_id == zoom_account_id))


def upsert_sync_config(db: Session, *, zoom_account_id: uuid.UUID, auto_sync_enabled: bool | None = None, sync_interval_minutes: int | None = None, lookback_days: int | None = None, auto_process: bool | None = None) -> SyncConfig:
    config = get_sync_config_by_account(db, zoom_account_id)
    if config is None:
        config = SyncConfig(
            zoom_account_id=zoom_account_id,
            auto_sync_enabled=auto_sync_enabled or False,
            sync_interval_minutes=sync_interval_minutes or 60,
            lookback_days=lookback_days or 30,
            auto_process=auto_process if auto_process is not None else True,
        )
        db.add(config)
    else:
        if auto_sync_enabled is not None:
            config.auto_sync_enabled = auto_sync_enabled
        if sync_interval_minutes is not None:
            config.sync_interval_minutes = sync_interval_minutes
        if lookback_days is not None:
            config.lookback_days = lookback_days
        if auto_process is not None:
            config.auto_process = auto_process
    db.flush()
    return config


def list_auto_sync_enabled(db: Session) -> list[SyncConfig]:
    return list(db.scalars(select(SyncConfig).where(SyncConfig.auto_sync_enabled.is_(True))).all())


def update_last_sync_status(db: Session, zoom_account_id: uuid.UUID, *, status: str, error: str | None = None) -> None:
    db.execute(
        update(SyncConfig).where(SyncConfig.zoom_account_id == zoom_account_id).values(
            last_sync_at=datetime.now(UTC),
            last_sync_status=status,
            last_sync_error=error,
        )
    )
    db.flush()


def create_sync_history(db: Session, *, zoom_account_id: uuid.UUID, sync_type: str) -> SyncHistory:
    entry = SyncHistory(
        zoom_account_id=zoom_account_id,
        sync_type=sync_type,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(entry)
    db.flush()
    return entry


def complete_sync_history(db: Session, entry: SyncHistory, *, meetings_discovered: int = 0, transcripts_discovered: int = 0, transcripts_queued: int = 0, error_message: str | None = None) -> None:
    now = datetime.now(UTC)
    entry.status = "failed" if error_message else "completed"
    entry.meetings_discovered = meetings_discovered
    entry.transcripts_discovered = transcripts_discovered
    entry.transcripts_queued = transcripts_queued
    entry.error_message = error_message
    entry.completed_at = now
    entry.duration_seconds = (now - entry.started_at).total_seconds() if entry.started_at else None
    db.flush()


def list_sync_history(db: Session, *, zoom_account_id: uuid.UUID | None = None, offset: int = 0, limit: int = 50) -> tuple[list[SyncHistory], int]:
    from sqlalchemy import func
    stmt = select(SyncHistory)
    count_stmt = select(func.count()).select_from(SyncHistory)
    if zoom_account_id:
        stmt = stmt.where(SyncHistory.zoom_account_id == zoom_account_id)
        count_stmt = count_stmt.where(SyncHistory.zoom_account_id == zoom_account_id)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(SyncHistory.started_at.desc()).offset(offset).limit(limit)).all()
    return list(rows), total
