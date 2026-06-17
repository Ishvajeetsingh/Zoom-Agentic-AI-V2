import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.processing_run import ProcessingRun

logger = get_logger(__name__)

VALID_RUN_STATUSES = {
    "pending", "queued", "running", "completed", "completed_with_warnings", "failed",
    "cancelled", "retrying",
}

PIPELINE_STEPS = [
    "download", "parse", "clean", "chunk", "generate",
    "generate_learning_outputs", "synthesize",
]

RETRY_BACKOFF_BASE_SECONDS = 2.0
RETRY_BACKOFF_MAX_SECONDS = 300.0


def create_run(
    db: Session,
    *,
    transcript_id: uuid.UUID,
    meeting_id: uuid.UUID | None = None,
    webhook_event_id: uuid.UUID | None = None,
    priority: int = 0,
    max_retries: int = 3,
) -> ProcessingRun:
    run = ProcessingRun(
        transcript_id=transcript_id,
        meeting_id=meeting_id,
        webhook_event_id=webhook_event_id,
        status="pending",
        total_steps=len(PIPELINE_STEPS),
        step_results=[],
        priority=priority,
        max_retries=max_retries,
    )
    db.add(run)
    db.flush()
    return run


def get_by_id(db: Session, run_id: uuid.UUID) -> ProcessingRun | None:
    return db.get(ProcessingRun, run_id)


def list_runs(
    db: Session,
    *,
    transcript_id: uuid.UUID | None = None,
    meeting_id: uuid.UUID | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
    order_desc: bool = True,
) -> tuple[list[ProcessingRun], int]:
    query = select(ProcessingRun)
    count_query = select(func.count()).select_from(ProcessingRun)

    if transcript_id is not None:
        query = query.where(ProcessingRun.transcript_id == transcript_id)
        count_query = count_query.where(ProcessingRun.transcript_id == transcript_id)
    if meeting_id is not None:
        query = query.where(ProcessingRun.meeting_id == meeting_id)
        count_query = count_query.where(ProcessingRun.meeting_id == meeting_id)
    if status is not None:
        query = query.where(ProcessingRun.status == status)
        count_query = count_query.where(ProcessingRun.status == status)

    order_col = ProcessingRun.created_at.desc() if order_desc else ProcessingRun.created_at.asc()
    query = query.order_by(order_col).offset(offset).limit(limit)

    rows = db.scalars(query).all()
    total = db.scalar(count_query)
    return rows, total


def mark_running(db: Session, run: ProcessingRun) -> None:
    run.status = "running"
    run.started_at = datetime.now(UTC)
    run.picked_at = datetime.now(UTC)
    db.flush()


def mark_step_completed(
    db: Session,
    run: ProcessingRun,
    *,
    step_name: str,
    result: dict | None = None,
) -> None:
    run.steps_completed += 1
    run.current_step = step_name
    step_entry = {"step": step_name, "status": "completed", "completed_at": datetime.now(UTC).isoformat()}
    if result:
        step_entry.update(result)
    run.step_results = list(run.step_results or []) + [step_entry]
    db.flush()


def mark_step_failed(
    db: Session,
    run: ProcessingRun,
    *,
    step_name: str,
    error: str,
) -> None:
    run.current_step = step_name
    step_entry = {"step": step_name, "status": "failed", "error": error, "failed_at": datetime.now(UTC).isoformat()}
    run.step_results = list(run.step_results or []) + [step_entry]
    db.flush()


def mark_completed(
    db: Session,
    run: ProcessingRun,
    *,
    questions_generated: int = 0,
    model_used: str | None = None,
) -> None:
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    if run.started_at:
        run.total_duration_seconds = (run.completed_at - run.started_at).total_seconds()
    run.questions_generated = questions_generated
    run.model_used = model_used
    run.locked_by = None
    run.locked_at = None
    db.flush()


def mark_completed_with_warnings(
    db: Session,
    run: ProcessingRun,
    *,
    questions_generated: int = 0,
    model_used: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    run.status = "completed_with_warnings"
    run.completed_at = datetime.now(UTC)
    if run.started_at:
        run.total_duration_seconds = (run.completed_at - run.started_at).total_seconds()
    run.questions_generated = questions_generated
    run.model_used = model_used
    if warnings:
        step_entry = {
            "step": "pipeline",
            "status": "completed_with_warnings",
            "warnings": list(warnings),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        run.step_results = list(run.step_results or []) + [step_entry]
    run.locked_by = None
    run.locked_at = None
    db.flush()


def mark_failed(
    db: Session,
    run: ProcessingRun,
    *,
    error_message: str,
) -> None:
    run.status = "failed"
    run.error_message = error_message
    run.completed_at = datetime.now(UTC)
    if run.started_at:
        run.total_duration_seconds = (run.completed_at - run.started_at).total_seconds()
    run.locked_by = None
    run.locked_at = None
    db.flush()


def mark_queued(db: Session, run: ProcessingRun) -> None:
    run.status = "queued"
    run.queued_at = datetime.now(UTC)
    db.flush()


def mark_retrying(db: Session, run: ProcessingRun) -> None:
    run.status = "retrying"
    run.retry_count += 1
    run.next_retry_at = _compute_next_retry(run.retry_count)
    run.locked_by = None
    run.locked_at = None
    run.completed_at = None
    run.error_message = None
    db.flush()


def mark_cancelled(db: Session, run: ProcessingRun) -> None:
    run.status = "cancelled"
    run.cancelled_at = datetime.now(UTC)
    run.locked_by = None
    run.locked_at = None
    if run.started_at and not run.completed_at:
        run.completed_at = datetime.now(UTC)
        run.total_duration_seconds = (run.completed_at - run.started_at).total_seconds()
    db.flush()


def lock_for_worker(db: Session, run: ProcessingRun, worker_id: str) -> None:
    run.locked_by = worker_id
    run.locked_at = datetime.now(UTC)
    db.flush()


def release_lock(db: Session, run: ProcessingRun) -> None:
    run.locked_by = None
    run.locked_at = None
    db.flush()


def reset_for_retry(db: Session, run: ProcessingRun) -> None:
    run.status = "queued"
    run.completed_at = None
    run.error_message = None
    run.locked_by = None
    run.locked_at = None
    db.flush()


def dequeue_next(db: Session, worker_id: str) -> ProcessingRun | None:
    eligible_statuses = ["queued", "retrying"]
    now = datetime.now(UTC)

    subq = (
        select(ProcessingRun.id)
        .where(
            ProcessingRun.status.in_(eligible_statuses),
            ProcessingRun.locked_by.is_(None),
        )
        .order_by(
            ProcessingRun.priority.desc(),
            ProcessingRun.queued_at.asc(),
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run_id = db.scalar(subq)
    if run_id is None:
        return None

    run = db.get(ProcessingRun, run_id)
    if run is None:
        return None

    if run.status == "retrying" and run.next_retry_at and run.next_retry_at > now:
        db.rollback()
        return None

    lock_for_worker(db, run, worker_id)
    mark_running(db, run)
    db.flush()
    return run


def count_by_status(db: Session) -> dict[str, int]:
    query = (
        select(ProcessingRun.status, func.count(ProcessingRun.id))
        .group_by(ProcessingRun.status)
    )
    rows = db.execute(query).all()
    return {row[0]: row[1] for row in rows}


def get_avg_duration(db: Session, status_filter: str = "completed") -> float | None:
    result = db.scalar(
        select(func.avg(ProcessingRun.total_duration_seconds))
        .where(ProcessingRun.status == status_filter, ProcessingRun.total_duration_seconds.isnot(None))
    )
    return float(result) if result is not None else None


def get_failure_rate(db: Session, hours: int = 24) -> float:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    total = db.scalar(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.created_at >= cutoff)
    ) or 0
    if total == 0:
        return 0.0
    failed = db.scalar(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.created_at >= cutoff, ProcessingRun.status == "failed")
    ) or 0
    return failed / total


def _compute_next_retry(retry_count: int) -> datetime:
    delay = min(
        RETRY_BACKOFF_BASE_SECONDS * (2 ** (retry_count - 1)),
        RETRY_BACKOFF_MAX_SECONDS,
    )
    return datetime.now(UTC) + timedelta(seconds=delay)
