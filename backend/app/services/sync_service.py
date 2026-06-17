from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.db.repositories import sync as sync_repo
from app.db.repositories import zoom_accounts as zoom_account_repo
from app.db.session import SessionLocal
from app.integrations.zoom.client_multi import get_zoom_api_client_from_db

logger = get_logger(__name__)


@dataclass
class AccountSyncResult:
    history_id: uuid.UUID | None = None
    meetings_discovered: int = 0
    transcripts_discovered: int = 0
    transcripts_queued: int = 0
    error: str | None = None


@dataclass
class AllSyncResult:
    accounts_processed: int = 0
    total_meetings: int = 0
    total_transcripts: int = 0
    total_queued: int = 0
    errors: list[str] = field(default_factory=list)


class SyncService:
    def run_sync_for_account(self, zoom_account_id: uuid.UUID, *, sync_type: str = "manual") -> AccountSyncResult:
        db = SessionLocal()
        result = AccountSyncResult()
        try:
            account = zoom_account_repo.get_by_id(db, zoom_account_id)
            if account is None:
                result.error = f"Zoom account not found: {zoom_account_id}"
                return result

            if not account.enabled:
                result.error = f"Zoom account is disabled: {account.account_name}"
                return result

            sync_entry = sync_repo.create_sync_history(
                db, zoom_account_id=account.id, sync_type=sync_type
            )
            result.history_id = sync_entry.id

            zoom_client = get_zoom_api_client_from_db(db, account.id)

            meetings_result = self._discover_meetings(db, zoom_client, account.id)
            transcripts_result = self._discover_transcripts(db, zoom_client)
            queue_result = self._queue_new_transcripts(db)

            result.meetings_discovered = meetings_result
            result.transcripts_discovered = transcripts_result
            result.transcripts_queued = queue_result

            sync_repo.complete_sync_history(
                db, sync_entry,
                meetings_discovered=meetings_result,
                transcripts_discovered=transcripts_result,
                transcripts_queued=queue_result,
            )
            sync_repo.update_last_sync_status(db, account.id, status="completed")
            zoom_account_repo.update_last_sync(db, account.id)
            db.commit()

            logger.info(
                "sync.account_completed",
                extra={
                    "account_id": str(account.id),
                    "meetings": meetings_result,
                    "transcripts": transcripts_result,
                    "queued": queue_result,
                },
            )

        except Exception as exc:
            db.rollback()
            result.error = str(exc)
            logger.exception(
                "sync.account_error",
                extra={"account_id": str(zoom_account_id)},
            )
            try:
                sync_entry_local = sync_repo.create_sync_history(
                    db, zoom_account_id=zoom_account_id, sync_type=sync_type
                )
                sync_repo.complete_sync_history(
                    db, sync_entry_local,
                    error_message=str(exc),
                )
                sync_repo.update_last_sync_status(db, zoom_account_id, status="failed", error=str(exc))
                db.commit()
            except Exception:
                db.rollback()
        finally:
            db.close()

        return result

    def run_sync_all_enabled(self) -> AllSyncResult:
        db = SessionLocal()
        result = AllSyncResult()
        try:
            accounts = zoom_account_repo.list_enabled(db)
            for account in accounts:
                try:
                    account_result = self.run_sync_for_account(account.id)
                    result.accounts_processed += 1
                    result.total_meetings += account_result.meetings_discovered
                    result.total_transcripts += account_result.transcripts_discovered
                    result.total_queued += account_result.transcripts_queued
                    if account_result.error:
                        result.errors.append(f"{account.account_name}: {account_result.error}")
                except Exception as exc:
                    result.errors.append(f"{account.account_name}: {exc}")
                    logger.exception(
                        "sync.all_account_error",
                        extra={"account_id": str(account.id)},
                    )
        finally:
            db.close()
        return result

    def run_auto_sync(self) -> None:
        db = SessionLocal()
        try:
            configs = sync_repo.list_auto_sync_enabled(db)
            if not configs:
                return

            from datetime import UTC, datetime, timedelta

            for config in configs:
                account = zoom_account_repo.get_by_id(db, config.zoom_account_id)
                if account is None or not account.enabled:
                    continue

                if config.last_sync_at is not None:
                    next_sync = config.last_sync_at + timedelta(minutes=config.sync_interval_minutes)
                    if datetime.now(UTC) < next_sync:
                        continue

                try:
                    self.run_sync_for_account(account.id, sync_type="automatic")
                except Exception as exc:
                    logger.exception(
                        "auto_sync.account_error",
                        extra={"account_id": str(account.id)},
                    )
        finally:
            db.close()

    def _discover_meetings(self, db, zoom_client, account_id: uuid.UUID) -> int:
        from app.services.meeting_discovery_service import MeetingDiscoveryService
        from datetime import UTC, datetime, timedelta

        service = MeetingDiscoveryService(db, zoom_client=zoom_client)
        lookback = 365
        from_date = (datetime.now(UTC) - timedelta(days=lookback)).strftime("%Y-%m-%d")
        to_date = datetime.now(UTC).strftime("%Y-%m-%d")

        try:
            result = service.discover_meetings(from_date=from_date, to_date=to_date)
            from app.db.models.meeting import Meeting
            from sqlalchemy import select, update

            new_meetings = [d for d in result.discovered if d.is_new]
            for d in new_meetings:
                if d.meeting_id:
                    db.execute(
                        update(Meeting).where(Meeting.id == d.meeting_id).values(zoom_account_id=account_id)
                    )
            db.flush()
            return result.new_meetings
        except Exception as exc:
            logger.exception(
                "sync.discover_meetings_error",
                extra={
                    "error": str(exc),
                    "exc_type": type(exc).__name__,
                    "exc_module": type(exc).__module__,
                },
            )
            return 0

    def _discover_transcripts(self, db, zoom_client) -> int:
        from app.services.transcript_discovery_service import TranscriptDiscoveryService

        service = TranscriptDiscoveryService(db, zoom_client=zoom_client)
        try:
            results = service.discover_for_all_meetings(only_without_transcripts=True)
            return sum(r.new_transcripts for r in results)
        except Exception as exc:
            logger.warning("sync.discover_transcripts_error", extra={"error": str(exc)})
            return 0

    def _queue_new_transcripts(self, db) -> int:
        from app.services.job_queue_service import JobQueueService
        from app.db.models.transcript import Transcript
        from app.db.models.processing_run import ProcessingRun
        from sqlalchemy import select

        active_run_subq = (
            select(ProcessingRun.transcript_id)
            .where(
                ProcessingRun.status.in_(["pending", "queued", "running", "retrying"])
            )
            .correlate(Transcript)
        )

        stmt = select(Transcript.id).where(
            Transcript.status.in_(["metadata_received", "downloaded"]),
            ~Transcript.id.in_(active_run_subq),
        )
        transcript_ids = db.scalars(stmt).all()

        if not transcript_ids:
            return 0

        queue_service = JobQueueService()
        queued = 0
        for tid in transcript_ids:
            try:
                queue_service.enqueue(db, transcript_id=tid, priority=0)
                queued += 1
            except Exception:
                pass
        db.commit()
        return queued
