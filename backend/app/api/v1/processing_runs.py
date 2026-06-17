import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.db.repositories import failures as failure_repo
from app.db.repositories import metrics as metrics_repo
from app.db.repositories import runs as run_repo
from app.db.repositories import transcripts as transcript_repo
from app.schemas.processing_runs import (
    BatchEnqueueRequest,
    BatchEnqueueResponse,
    EnqueueResultOut,
    ProcessingFailureOut,
    ProcessingRunCreate,
    ProcessingRunDetailOut,
    ProcessingRunEnqueue,
    ProcessingRunListItem,
    ProcessingRunListOut,
    ProcessingRunResultOut,
    ProcessingRunStatusOut,
)
from app.services.job_queue_service import JobQueueError, JobQueueService
from app.services.processing_orchestrator_service import OrchestrationError, ProcessingOrchestratorService

router = APIRouter()
logger = get_logger(__name__)

_queue_service = JobQueueService()


@router.get("", response_model=ProcessingRunListOut)
def list_processing_runs(
    transcript_id: uuid.UUID | None = Query(None),
    meeting_id: uuid.UUID | None = Query(None),
    run_status: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> ProcessingRunListOut:
    if run_status is not None and run_status not in run_repo.VALID_RUN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {sorted(run_repo.VALID_RUN_STATUSES)}",
        )

    rows, total = run_repo.list_runs(
        db,
        transcript_id=transcript_id,
        meeting_id=meeting_id,
        status=run_status,
        offset=offset,
        limit=limit,
        order_desc=(order == "desc"),
    )

    items = [ProcessingRunListItem.model_validate(r) for r in rows]
    return ProcessingRunListOut(items=items, total=total, offset=offset, limit=limit)


@router.get("/metrics", response_model=dict)
def get_queue_metrics(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict:
    return metrics_repo.get_queue_metrics(db, hours=hours)


@router.get("/{run_id}", response_model=ProcessingRunDetailOut)
def get_processing_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProcessingRunDetailOut:
    run = run_repo.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing run not found")
    detail = ProcessingRunDetailOut.model_validate(run)
    failures = failure_repo.get_by_run_id(db, run_id)
    detail.failures = [ProcessingFailureOut.model_validate(f) for f in failures]
    return detail


@router.get("/{run_id}/status", response_model=ProcessingRunStatusOut)
def get_processing_run_status(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProcessingRunStatusOut:
    run = run_repo.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing run not found")
    return ProcessingRunStatusOut.model_validate(run)


@router.get("/{run_id}/failures", response_model=list)
def get_processing_run_failures(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list:
    run = run_repo.get_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing run not found")
    failures = failure_repo.get_by_run_id(db, run_id)
    return [ProcessingFailureOut.model_validate(f) for f in failures]


@router.post("", response_model=ProcessingRunResultOut, status_code=status.HTTP_201_CREATED)
def create_and_run_processing(
    body: ProcessingRunCreate,
    db: Session = Depends(get_db),
) -> ProcessingRunResultOut:
    transcript = transcript_repo.get_by_id(db, body.transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    service = ProcessingOrchestratorService(db)
    try:
        result = service.process_transcript(body.transcript_id)
    except OrchestrationError as exc:
        db.rollback()
        logger.warning(
            "processing_run.orchestration_error",
            extra={"transcript_id": str(body.transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning(
            "processing_run.external_error",
            extra={"transcript_id": str(body.transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("processing_run.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist processing run data",
        ) from exc

    run = run_repo.get_by_id(db, result.run_id)
    return ProcessingRunResultOut.model_validate(run)


@router.post("/enqueue", response_model=EnqueueResultOut, status_code=status.HTTP_202_ACCEPTED)
def enqueue_processing_run(
    body: ProcessingRunEnqueue,
    db: Session = Depends(get_db),
) -> EnqueueResultOut:
    try:
        result = _queue_service.enqueue(
            db,
            transcript_id=body.transcript_id,
            meeting_id=body.meeting_id,
            webhook_event_id=body.webhook_event_id,
            priority=body.priority,
            max_retries=body.max_retries,
        )
    except JobQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("processing_run.enqueue.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue processing run",
        ) from exc

    return EnqueueResultOut.model_validate(result)


@router.post("/enqueue/batch", response_model=BatchEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
def batch_enqueue_processing_runs(
    body: BatchEnqueueRequest,
    db: Session = Depends(get_db),
) -> BatchEnqueueResponse:
    try:
        result = _queue_service.batch_enqueue(
            db,
            transcript_ids=body.transcript_ids,
            priority=body.priority,
            max_retries=body.max_retries,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("processing_run.batch_enqueue.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch enqueue processing runs",
        ) from exc

    return BatchEnqueueResponse(
        enqueued=[EnqueueResultOut.model_validate(e) for e in result.enqueued],
        skipped=result.skipped,
        errors=result.errors,
    )


@router.post("/{run_id}/retry", response_model=EnqueueResultOut, status_code=status.HTTP_202_ACCEPTED)
def retry_processing_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> EnqueueResultOut:
    try:
        result = _queue_service.retry_run(db, run_id=run_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("processing_run.retry.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry processing run",
        ) from exc

    return EnqueueResultOut.model_validate(result)


@router.post("/{run_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_processing_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    try:
        _queue_service.cancel_run(db, run_id=run_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("processing_run.cancel.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel processing run",
        ) from exc

    return {"run_id": str(run_id), "status": "cancelled"}


@router.post("/workers/start", status_code=status.HTTP_200_OK)
def start_workers(
    num_workers: int = Query(2, ge=1, le=10),
    poll_interval: float = Query(5.0, ge=1.0, le=60.0),
) -> dict:
    _queue_service.start_workers(num_workers=num_workers, poll_interval=poll_interval)
    return {"status": "started", "num_workers": num_workers, "poll_interval": poll_interval}


@router.post("/workers/stop", status_code=status.HTTP_200_OK)
def stop_workers() -> dict:
    _queue_service.stop_workers()
    return {"status": "stopped"}
