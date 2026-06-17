import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.processing_failure import ProcessingFailure

logger = get_logger(__name__)


def record_failure(
    db: Session,
    *,
    run_id: uuid.UUID,
    step: str,
    error_message: str,
    error_type: str | None = None,
    stack_trace: str | None = None,
    retry_eligible: bool = True,
    retry_number: int = 0,
) -> ProcessingFailure:
    failure = ProcessingFailure(
        run_id=run_id,
        step=step,
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
        retry_eligible=retry_eligible,
        retry_number=retry_number,
    )
    db.add(failure)
    db.flush()
    return failure


def get_by_run_id(db: Session, run_id: uuid.UUID) -> list[ProcessingFailure]:
    rows = db.scalars(
        select(ProcessingFailure)
        .where(ProcessingFailure.run_id == run_id)
        .order_by(ProcessingFailure.occurred_at.asc())
    ).all()
    return list(rows)


def get_by_id(db: Session, failure_id: uuid.UUID) -> ProcessingFailure | None:
    return db.get(ProcessingFailure, failure_id)


def count_failures_by_step(db: Session, hours: int = 24) -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    rows = db.execute(
        select(ProcessingFailure.step, func.count(ProcessingFailure.id))
        .where(ProcessingFailure.occurred_at >= cutoff)
        .group_by(ProcessingFailure.step)
    ).all()
    return {row[0]: row[1] for row in rows}


def count_retry_eligible(db: Session, run_id: uuid.UUID) -> int:
    result = db.scalar(
        select(func.count(ProcessingFailure.id))
        .where(
            ProcessingFailure.run_id == run_id,
            ProcessingFailure.retry_eligible.is_(True),
        )
    )
    return result or 0
