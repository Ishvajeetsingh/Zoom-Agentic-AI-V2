from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.processing_failure import ProcessingFailure
from app.db.models.processing_run import ProcessingRun
from app.db.repositories import runs as run_repo

logger = get_logger(__name__)


def get_queue_metrics(db: Session, hours: int = 24) -> dict:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    status_counts = run_repo.count_by_status(db)

    total_completed = status_counts.get("completed", 0)
    total_failed = status_counts.get("failed", 0)
    total_queued = status_counts.get("queued", 0) + status_counts.get("pending", 0)
    total_running = status_counts.get("running", 0)
    total_retrying = status_counts.get("retrying", 0)

    avg_duration = run_repo.get_avg_duration(db, "completed")
    avg_failed_duration = run_repo.get_avg_duration(db, "failed")

    failure_rate = run_repo.get_failure_rate(db, hours)

    failure_breakdown = _count_failures_by_step(db, hours)

    recent_total = db.scalar(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.created_at >= cutoff)
    ) or 0

    recent_completed = db.scalar(
        select(func.count(ProcessingRun.id))
        .where(ProcessingRun.created_at >= cutoff, ProcessingRun.status == "completed")
    ) or 0

    throughput = recent_completed / hours if hours > 0 else 0.0

    avg_wait = _avg_queue_wait_time(db, hours)

    return {
        "status_counts": status_counts,
        "queue_depth": total_queued + total_retrying,
        "active_workers": total_running,
        "avg_processing_duration_seconds": avg_duration,
        "avg_failed_duration_seconds": avg_failed_duration,
        "avg_queue_wait_seconds": avg_wait,
        "failure_rate": round(failure_rate, 4),
        "throughput_per_hour": round(throughput, 2),
        "failure_breakdown_by_step": failure_breakdown,
        "total_runs_created_last_n_hours": recent_total,
        "hours_window": hours,
    }


def _count_failures_by_step(db: Session, hours: int) -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = db.execute(
        select(ProcessingFailure.step, func.count(ProcessingFailure.id))
        .where(ProcessingFailure.occurred_at >= cutoff)
        .group_by(ProcessingFailure.step)
    ).all()
    return {row[0]: row[1] for row in rows}


def _avg_queue_wait_time(db: Session, hours: int) -> float | None:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    result = db.scalar(
        select(
            func.avg(
                func.extract("epoch", ProcessingRun.picked_at - ProcessingRun.queued_at)
            )
        ).where(
            ProcessingRun.queued_at >= cutoff,
            ProcessingRun.picked_at.isnot(None),
        )
    )
    return float(result) if result is not None else None
