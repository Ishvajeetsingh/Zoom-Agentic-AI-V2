import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ConfigurationError, ExternalServiceError
from app.core.logging import get_logger
from app.db.models.meeting import Meeting
from app.db.models.transcript import Transcript
from app.services.ingestion_service import ZoomIngestionError, ZoomIngestionService
from app.services.job_queue_service import JobQueueError, JobQueueService
from app.services.meeting_discovery_service import MeetingDiscoveryError, MeetingDiscoveryService
from app.services.processing_orchestrator_service import OrchestrationError, ProcessingOrchestratorService
from app.services.transcript_discovery_service import TranscriptDiscoveryError, TranscriptDiscoveryService

router = APIRouter()
logger = get_logger(__name__)

_queue_service = JobQueueService()


class ZoomIngestRequest(BaseModel):
    meeting_uuid: str = Field(..., min_length=1, description="Zoom meeting UUID")


class ZoomIngestResponse(BaseModel):
    meeting_id: str
    transcript_id: str | None
    recording_found: bool
    zoom_meeting_id: str | None
    zoom_uuid: str
    topic: str | None


@router.post("/ingest", response_model=ZoomIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_zoom_meeting(
    request: ZoomIngestRequest,
    db: Session = Depends(get_db),
) -> ZoomIngestResponse:
    service = ZoomIngestionService(db)
    try:
        result = service.ingest_meeting(request.meeting_uuid)
    except ZoomIngestionError as exc:
        db.rollback()
        logger.warning(
            "zoom_ingest.api_error",
            extra={"meeting_uuid": request.meeting_uuid, "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConfigurationError as exc:
        db.rollback()
        logger.error(
            "zoom_ingest.config_error",
            extra={"meeting_uuid": request.meeting_uuid, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Zoom configuration error: {exc}",
        ) from exc
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning(
            "zoom_ingest.external_error",
            extra={"meeting_uuid": request.meeting_uuid, "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_ingest.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist Zoom ingestion data",
        ) from exc

    return ZoomIngestResponse(
        meeting_id=str(result.meeting_id),
        transcript_id=str(result.transcript_id) if result.transcript_id else None,
        recording_found=result.recording_found,
        zoom_meeting_id=result.zoom_meeting_id,
        zoom_uuid=result.zoom_uuid,
        topic=result.topic,
    )


class DiscoverMeetingsRequest(BaseModel):
    user_id: str = Field("me", description="Zoom user ID")
    from_date: str | None = Field(None, description="Start date YYYY-MM-DD")
    to_date: str | None = Field(None, description="End date YYYY-MM-DD")
    lookback_days: int = Field(30, ge=1, le=365, description="Days to look back if from_date not set")


class DiscoverMeetingsResponse(BaseModel):
    total_found: int
    new_meetings: int
    existing_meetings: int
    meetings_with_transcripts: int
    errors: list[str]


@router.post("/discover-meetings", response_model=DiscoverMeetingsResponse)
def discover_meetings(
    request: DiscoverMeetingsRequest,
    db: Session = Depends(get_db),
) -> DiscoverMeetingsResponse:
    service = MeetingDiscoveryService(db)
    try:
        result = service.discover_meetings(
            user_id=request.user_id,
            from_date=request.from_date,
            to_date=request.to_date,
            lookback_days=request.lookback_days,
        )
    except MeetingDiscoveryError as exc:
        db.rollback()
        logger.warning("zoom_discover_meetings.error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning("zoom_discover_meetings.external_error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_discover_meetings.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist discovered meetings",
        ) from exc

    return DiscoverMeetingsResponse(
        total_found=result.total_found,
        new_meetings=result.new_meetings,
        existing_meetings=result.existing_meetings,
        meetings_with_transcripts=result.meetings_with_transcripts,
        errors=result.errors,
    )


class DiscoverTranscriptsResponse(BaseModel):
    meeting_id: str
    zoom_uuid: str
    total_files_scanned: int
    transcripts_found: int
    new_transcripts: int
    existing_transcripts: int
    errors: list[str]


@router.post("/discover-transcripts/{meeting_id}", response_model=DiscoverTranscriptsResponse)
def discover_transcripts_for_meeting(
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DiscoverTranscriptsResponse:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    service = TranscriptDiscoveryService(db)
    try:
        result = service.discover_for_meeting(meeting)
    except TranscriptDiscoveryError as exc:
        db.rollback()
        logger.warning("zoom_discover_transcripts.error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning("zoom_discover_transcripts.external_error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_discover_transcripts.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist discovered transcripts",
        ) from exc

    return DiscoverTranscriptsResponse(
        meeting_id=str(result.meeting_id),
        zoom_uuid=result.zoom_uuid,
        total_files_scanned=result.total_files_scanned,
        transcripts_found=result.transcripts_found,
        new_transcripts=result.new_transcripts,
        existing_transcripts=result.existing_transcripts,
        errors=result.errors,
    )


class DiscoverAllTranscriptsResponse(BaseModel):
    meetings_processed: int
    total_transcripts_found: int
    total_new_transcripts: int
    errors: list[str]


@router.post("/discover-transcripts", response_model=DiscoverAllTranscriptsResponse)
def discover_transcripts_all(
    only_without: bool = Query(True, alias="only_without_transcripts"),
    db: Session = Depends(get_db),
) -> DiscoverAllTranscriptsResponse:
    service = TranscriptDiscoveryService(db)
    try:
        results = service.discover_for_all_meetings(only_without_transcripts=only_without)
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning("zoom_discover_all_transcripts.external_error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_discover_all_transcripts.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist discovered transcripts",
        ) from exc

    total_found = sum(r.transcripts_found for r in results)
    total_new = sum(r.new_transcripts for r in results)
    all_errors = []
    for r in results:
        all_errors.extend(r.errors)

    return DiscoverAllTranscriptsResponse(
        meetings_processed=len(results),
        total_transcripts_found=total_found,
        total_new_transcripts=total_new,
        errors=all_errors,
    )


class OrchestrateRequest(BaseModel):
    transcript_id: uuid.UUID


class OrchestrateResponse(BaseModel):
    run_id: str
    transcript_id: str
    meeting_id: str | None
    status: str
    steps_completed: int
    total_steps: int
    questions_generated: int
    model_used: str | None
    error_message: str | None
    total_duration_seconds: float | None


@router.post("/orchestrate", response_model=OrchestrateResponse)
def orchestrate_processing(
    request: OrchestrateRequest,
    db: Session = Depends(get_db),
) -> OrchestrateResponse:
    service = ProcessingOrchestratorService(db)
    try:
        result = service.process_transcript(request.transcript_id)
    except OrchestrationError as exc:
        db.rollback()
        logger.warning(
            "zoom_orchestrate.error",
            extra={"transcript_id": str(request.transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning(
            "zoom_orchestrate.external_error",
            extra={"transcript_id": str(request.transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_orchestrate.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist orchestration data",
        ) from exc

    return OrchestrateResponse(
        run_id=str(result.run_id),
        transcript_id=str(result.transcript_id),
        meeting_id=str(result.meeting_id) if result.meeting_id else None,
        status=result.status,
        steps_completed=result.steps_completed,
        total_steps=result.total_steps,
        questions_generated=result.questions_generated,
        model_used=result.model_used,
        error_message=result.error_message,
        total_duration_seconds=result.total_duration_seconds,
    )


class OrchestrateQueueRequest(BaseModel):
    transcript_id: uuid.UUID
    priority: int = Field(0, ge=0, le=10)
    max_retries: int = Field(3, ge=0, le=10)


class OrchestrateQueueResponse(BaseModel):
    run_id: str
    transcript_id: str
    status: str
    priority: int
    queued_at: str | None = None


@router.post("/orchestrate/queue", response_model=OrchestrateQueueResponse, status_code=status.HTTP_202_ACCEPTED)
def orchestrate_queue_processing(
    request: OrchestrateQueueRequest,
    db: Session = Depends(get_db),
) -> OrchestrateQueueResponse:
    try:
        result = _queue_service.enqueue(
            db,
            transcript_id=request.transcript_id,
            priority=request.priority,
            max_retries=request.max_retries,
        )
    except JobQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("zoom_orchestrate_queue.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue orchestration job",
        ) from exc

    return OrchestrateQueueResponse(
        run_id=str(result.run_id),
        transcript_id=str(result.transcript_id),
        status=result.status,
        priority=result.priority,
        queued_at=str(result.queued_at) if result.queued_at else None,
    )


class BatchOrchestrateRequest(BaseModel):
    meeting_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)
    priority: int = Field(0, ge=0, le=10)
    max_retries: int = Field(3, ge=0, le=10)


class BatchOrchestrateResponse(BaseModel):
    enqueued: list[dict]
    skipped: list[dict]
    errors: list[str]


@router.post("/orchestrate/batch", response_model=BatchOrchestrateResponse, status_code=status.HTTP_202_ACCEPTED)
def batch_orchestrate_processing(
    request: BatchOrchestrateRequest,
    db: Session = Depends(get_db),
) -> BatchOrchestrateResponse:
    transcript_ids: list[uuid.UUID] = []

    for meeting_id in request.meeting_ids:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            continue
        rows = db.scalars(
            select(Transcript.id).where(Transcript.meeting_id == meeting_id)
        ).all()
        transcript_ids.extend(rows)

    if not transcript_ids:
        return BatchOrchestrateResponse(enqueued=[], skipped=[], errors=["No transcripts found for given meetings"])

    try:
        result = _queue_service.batch_enqueue(
            db,
            transcript_ids=transcript_ids,
            priority=request.priority,
            max_retries=request.max_retries,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("zoom_batch_orchestrate.error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch enqueue processing jobs",
        ) from exc

    enqueued = [
        {"run_id": str(e.run_id), "transcript_id": str(e.transcript_id), "status": e.status}
        for e in result.enqueued
    ]
    return BatchOrchestrateResponse(
        enqueued=enqueued,
        skipped=result.skipped,
        errors=result.errors,
    )
