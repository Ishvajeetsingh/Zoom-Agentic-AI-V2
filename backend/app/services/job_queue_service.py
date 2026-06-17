from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.processing_run import ProcessingRun
from app.db.repositories import failures as failure_repo
from app.db.repositories import runs as run_repo
from app.db.repositories import transcripts as transcript_repo
from app.db.session import SessionLocal
from app.services.processing_orchestrator_service import (
    OrchestrationError,
    ProcessingOrchestratorService,
)

logger = get_logger(__name__)


class JobQueueError(AppError):
    pass


@dataclass
class EnqueueResult:
    run_id: uuid.UUID
    transcript_id: uuid.UUID
    status: str
    priority: int
    queued_at: datetime | None = None
    webhook_event_id: uuid.UUID | None = None


@dataclass
class BatchEnqueueResult:
    enqueued: list[EnqueueResult] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class JobQueueService:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self._shutdown_event = threading.Event()
        self._workers: list[threading.Thread] = []

    def enqueue(
        self,
        db: Session,
        *,
        transcript_id: uuid.UUID,
        meeting_id: uuid.UUID | None = None,
        webhook_event_id: uuid.UUID | None = None,
        priority: int = 0,
        max_retries: int = 3,
    ) -> EnqueueResult:
        transcript = transcript_repo.get_by_id(db, transcript_id)
        if transcript is None:
            raise JobQueueError(f"Transcript not found: {transcript_id}")

        if transcript.status == "completed":
            raise JobQueueError(f"Transcript {transcript_id} already completed")

        active_statuses = {"pending", "queued", "running", "retrying"}
        existing = db.scalar(
            select(ProcessingRun.id).where(
                ProcessingRun.transcript_id == transcript_id,
                ProcessingRun.status.in_(active_statuses),
            )
        )
        if existing is not None:
            raise JobQueueError(
                f"Transcript {transcript_id} already has an active run ({existing})"
            )

        run = run_repo.create_run(
            db,
            transcript_id=transcript_id,
            meeting_id=meeting_id or transcript.meeting_id,
            webhook_event_id=webhook_event_id,
            priority=priority,
            max_retries=max_retries,
        )
        run_repo.mark_queued(db, run)
        db.commit()

        logger.info(
            "job_queue.enqueued",
            extra={"run_id": str(run.id), "transcript_id": str(transcript_id), "priority": priority},
        )

        return EnqueueResult(
            run_id=run.id,
            transcript_id=transcript_id,
            status=run.status,
            priority=run.priority,
            queued_at=run.queued_at,
            webhook_event_id=run.webhook_event_id,
        )

    def batch_enqueue(
        self,
        db: Session,
        *,
        transcript_ids: list[uuid.UUID],
        priority: int = 0,
        max_retries: int = 3,
    ) -> BatchEnqueueResult:
        result = BatchEnqueueResult()

        for tid in transcript_ids:
            try:
                enqueue_result = self.enqueue(
                    db, transcript_id=tid, priority=priority, max_retries=max_retries,
                )
                result.enqueued.append(enqueue_result)
            except JobQueueError as exc:
                result.skipped.append({"transcript_id": str(tid), "reason": str(exc)})
            except SQLAlchemyError as exc:
                db.rollback()
                result.errors.append(f"transcript {tid}: database error - {exc}")
            except Exception as exc:
                db.rollback()
                result.errors.append(f"transcript {tid}: {exc}")

        return result

    def retry_run(self, db: Session, run_id: uuid.UUID) -> EnqueueResult:
        run = run_repo.get_by_id(db, run_id)
        if run is None:
            raise JobQueueError(f"Processing run not found: {run_id}")

        if run.status not in ("failed", "cancelled"):
            raise JobQueueError(f"Run {run_id} has status '{run.status}' - only failed/cancelled runs can be retried")

        if run.retry_count >= run.max_retries:
            raise JobQueueError(
                f"Run {run_id} has exceeded max retries ({run.max_retries})"
            )

        run_repo.mark_retrying(db, run)
        db.commit()

        logger.info(
            "job_queue.retry_scheduled",
            extra={
                "run_id": str(run_id),
                "retry_count": run.retry_count,
                "max_retries": run.max_retries,
                "next_retry_at": str(run.next_retry_at),
            },
        )

        return EnqueueResult(
            run_id=run.id,
            transcript_id=run.transcript_id,
            status=run.status,
            priority=run.priority,
            queued_at=run.queued_at,
        )

    def cancel_run(self, db: Session, run_id: uuid.UUID) -> None:
        run = run_repo.get_by_id(db, run_id)
        if run is None:
            raise JobQueueError(f"Processing run not found: {run_id}")

        if run.status in ("completed", "cancelled"):
            raise JobQueueError(f"Run {run_id} cannot be cancelled (status: {run.status})")

        run_repo.mark_cancelled(db, run)

        transcript = transcript_repo.get_by_id(db, run.transcript_id)
        if transcript and transcript.status not in ("completed", "completed_with_warnings", "failed", "generation_failed"):
            transcript_repo.mark_cancelled(db, transcript)

        db.commit()

        logger.info("job_queue.cancelled", extra={"run_id": str(run_id), "transcript_status": transcript.status if transcript else None})

    def process_next(self) -> bool:
        db = SessionLocal()
        try:
            run = run_repo.dequeue_next(db, self._worker_id)
            if run is None:
                return False

            logger.info(
                "job_queue.worker_picked",
                extra={"run_id": str(run.id), "worker_id": self._worker_id},
            )

            self._process_run(db, run)
            return True
        except Exception:
            logger.exception("job_queue.worker_error")
            db.rollback()
            return False
        finally:
            db.close()

    def _process_run(self, db: Session, run) -> None:
        try:
            service = ProcessingOrchestratorService(db)
            result = service.process_transcript(run.transcript_id, existing_run_id=run.id)

            db.refresh(run)

            if run.status in ("completed", "completed_with_warnings"):
                logger.info(
                    "job_queue.run_completed",
                    extra={"run_id": str(run.id), "status": run.status},
                )
                return

            if result.status == "failed" and run.retry_count < run.max_retries:
                failure_repo.record_failure(
                    db,
                    run_id=run.id,
                    step=run.current_step or "unknown",
                    error_message=result.error_message or "Pipeline failed",
                    retry_eligible=True,
                    retry_number=run.retry_count,
                )
                run_repo.mark_retrying(db, run)
                db.commit()
                logger.info(
                    "job_queue.auto_retry_scheduled",
                    extra={"run_id": str(run.id), "retry_count": run.retry_count},
                )
            elif result.status == "completed_with_warnings":
                run_repo.mark_completed(db, run, questions_generated=result.questions_generated, model_used=result.model_used)
                db.commit()
                logger.info(
                    "job_queue.run_completed_with_warnings",
                    extra={"run_id": str(run.id), "questions_generated": result.questions_generated},
                )
            else:
                logger.info(
                    "job_queue.run_completed",
                    extra={"run_id": str(run.id), "status": result.status},
                )
        except OrchestrationError as exc:
            db.rollback()
            run_fresh = run_repo.get_by_id(db, run.id)
            if run_fresh is not None:
                failure_repo.record_failure(
                    db,
                    run_id=run_fresh.id,
                    step=run_fresh.current_step or "unknown",
                    error_message=str(exc),
                    error_type=type(exc).__name__,
                    retry_eligible=run_fresh.retry_count < run_fresh.max_retries,
                    retry_number=run_fresh.retry_count,
                )

                if run_fresh.retry_count < run_fresh.max_retries:
                    run_repo.mark_retrying(db, run_fresh)
                    db.commit()
                    logger.info(
                        "job_queue.auto_retry_on_error",
                        extra={"run_id": str(run_fresh.id), "retry_count": run_fresh.retry_count},
                    )
                else:
                    run_repo.mark_failed(db, run_fresh, error_message=str(exc))
                    db.commit()
                    logger.warning(
                        "job_queue.max_retries_exceeded",
                        extra={"run_id": str(run_fresh.id)},
                    )
        except Exception as exc:
            db.rollback()
            run_fresh = run_repo.get_by_id(db, run.id)
            if run_fresh is not None:
                run_repo.mark_failed(db, run_fresh, error_message=str(exc))
                failure_repo.record_failure(
                    db,
                    run_id=run_fresh.id,
                    step=run_fresh.current_step or "unknown",
                    error_message=str(exc),
                    error_type=type(exc).__name__,
                    retry_eligible=False,
                    retry_number=run_fresh.retry_count,
                )
                db.commit()

    def start_workers(self, num_workers: int = 2, poll_interval: float = 5.0) -> None:
        if self._workers:
            logger.warning("job_queue.workers_already_running")
            return

        self._shutdown_event.clear()

        for i in range(num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                args=(poll_interval,),
                name=f"job-queue-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

        logger.info(
            "job_queue.workers_started",
            extra={"num_workers": num_workers, "poll_interval": poll_interval},
        )

    def stop_workers(self, timeout: float = 30.0) -> None:
        self._shutdown_event.set()
        for t in self._workers:
            t.join(timeout=timeout)
        self._workers.clear()
        logger.info("job_queue.workers_stopped")

    @property
    def is_running(self) -> bool:
        return not self._shutdown_event.is_set() and len(self._workers) > 0

    def _worker_loop(self, poll_interval: float) -> None:
        logger.info("job_queue.worker_started", extra={"worker_id": self._worker_id})
        while not self._shutdown_event.is_set():
            try:
                processed = self.process_next()
                if not processed:
                    self._shutdown_event.wait(poll_interval)
            except Exception:
                logger.exception("job_queue.worker_loop_error")
                self._shutdown_event.wait(poll_interval)
