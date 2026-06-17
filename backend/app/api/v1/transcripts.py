import uuid
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.db.repositories import meetings as meeting_repo
from app.db.repositories import questions as question_repo
from app.db.repositories import transcripts as transcript_repo
from app.schemas.questions import QuestionListOut, QuestionOut
from app.schemas.transcripts import TranscriptDetailOut, TranscriptListOut, TranscriptListItem
from app.services.transcript_download_service import (
    TranscriptDownloadError,
    TranscriptDownloadService,
)
from app.services.processing_orchestrator_service import (
    OrchestrationError,
    ProcessingOrchestratorService,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=TranscriptListOut)
def list_transcripts(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    order_by: str = Query("created_at", pattern="^(created_at|updated_at|status|segment_count|chunk_count|question_count)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> TranscriptListOut:
    if status_filter is not None and status_filter not in transcript_repo.VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {sorted(transcript_repo.VALID_STATUSES)}",
        )

    rows, total = transcript_repo.list_transcripts(
        db,
        offset=offset,
        limit=limit,
        status=status_filter,
        order_by=order_by,
        order_desc=(order == "desc"),
    )

    items = [TranscriptListItem.model_validate(t) for t in rows]

    return TranscriptListOut(items=items, total=total, offset=offset, limit=limit)


@router.get("/{transcript_id}", response_model=TranscriptDetailOut)
def get_transcript(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> TranscriptDetailOut:
    detail = transcript_repo.get_transcript_detail(db, transcript_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    return TranscriptDetailOut.model_validate(detail)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_transcript(
    file: UploadFile = File(...),
    meeting_topic: str = Form("Uploaded Transcript"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")

    extension = Path(file.filename).suffix.lstrip(".").lower()
    if extension not in {"vtt", "json", "txt"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '.{extension}'. Supported: .vtt, .json, .txt",
        )

    file_content = file.file.read()
    file_size = len(file_content)
    if file_size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    checksum = hashlib.sha256(file_content).hexdigest()

    source_format = extension
    if extension == "vtt":
        file_type = "VTT"
    elif extension == "json":
        file_type = "JSON"
    else:
        file_type = "TXT"

    try:
        meeting = meeting_repo.upsert_zoom_meeting(
            db,
            {
                "source": "upload",
                "topic": meeting_topic,
            },
        )

        storage_dir = Path(settings.transcript_storage_dir) / "uploads"
        storage_dir.mkdir(parents=True, exist_ok=True)
        raw_file_path = storage_dir / f"{uuid.uuid4()}.{extension}"
        raw_file_path.write_bytes(file_content)

        transcript = transcript_repo.upsert_transcript_metadata(
            db,
            {
                "meeting_id": meeting.id,
                "source_format": source_format,
                "status": "downloaded",
                "transcript_filename": file.filename,
                "raw_file_path": str(raw_file_path),
                "file_type": file_type,
                "file_extension": extension,
                "file_size_bytes": file_size,
                "checksum_sha256": checksum,
            },
        )

        db.commit()

        return {
            "transcript_id": str(transcript.id),
            "meeting_id": str(meeting.id),
            "transcript_filename": transcript.transcript_filename,
            "file_size_bytes": transcript.file_size_bytes,
            "source_format": transcript.source_format,
            "status": transcript.status,
        }
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("transcript_upload.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded transcript",
        ) from exc


@router.post("/{transcript_id}/download")
def download_transcript(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    service = TranscriptDownloadService(db)
    try:
        result = service.download_transcript(transcript_id)
    except TranscriptDownloadError as exc:
        db.rollback()
        logger.warning(
            "transcript_download.api_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExternalServiceError as exc:
        db.rollback()
        logger.warning(
            "transcript_download.external_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("transcript_download.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transcript download metadata",
        ) from exc

    return {
        "status": result.status,
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id),
        "transcript_filename": result.transcript_filename,
        "raw_file_path": result.raw_file_path,
        "file_size_bytes": result.file_size_bytes,
        "checksum_sha256": result.checksum_sha256,
    }


@router.post("/{transcript_id}/parse")
def parse_transcript(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    service = TranscriptParseService(db)
    try:
        result = service.parse_transcript(transcript_id)
    except TranscriptParseError as exc:
        db.rollback()
        logger.warning(
            "transcript_parse.api_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("transcript_parse.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist parsed transcript segments",
        ) from exc

    return {
        "status": result.status,
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id),
        "segment_count": result.segment_count,
        "word_count": result.word_count,
    }


@router.post("/{transcript_id}/clean")
def clean_transcript(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    service = TranscriptCleaningService(db)
    try:
        result = service.clean_transcript(transcript_id)
    except TranscriptCleaningError as exc:
        db.rollback()
        logger.warning(
            "transcript_cleaning.api_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("transcript_cleaning.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist cleaned transcript segments",
        ) from exc

    return {
        "status": result.status,
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id),
        "segments_cleaned": result.segments_cleaned,
        "speakers_normalized": result.speakers_normalized,
        "null_speakers_assigned": result.null_speakers_assigned,
        "total_fillers_removed": result.total_fillers_removed,
        "total_annotations_removed": result.total_annotations_removed,
        "total_artifacts_removed": result.total_artifacts_removed,
    }


@router.post("/{transcript_id}/chunk")
def chunk_transcript(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    service = ChunkingService(db)
    try:
        result = service.chunk_transcript(transcript_id)
    except ChunkingError as exc:
        db.rollback()
        logger.warning(
            "chunking.api_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("chunking.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist transcript chunks",
        ) from exc

    return {
        "status": result.status,
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id),
        "total_chunks": result.total_chunks,
        "total_words": result.total_words,
        "segments_merged": result.segments_merged,
    }


@router.post("/{transcript_id}/generate")
def generate_questions(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    service = PreprocessingService(db)
    try:
        result = service.run_workflow(transcript_id)
    except WorkflowError as exc:
        db.rollback()
        logger.warning(
            "workflow.api_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("workflow.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transcript generation status",
        ) from exc

    return {
        "status": result.status,
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id) if result.meeting_id else None,
        "total_questions": result.total_questions,
        "questions_persisted": result.questions_persisted,
        "chunks_loaded": result.chunks_loaded,
        "questions_generated": result.questions_generated,
        "questions_validated": result.questions_validated,
        "duplicates_removed": result.duplicates_removed,
        "model_used": result.model_used,
        "total_prompt_tokens": result.total_prompt_tokens,
        "total_completion_tokens": result.total_completion_tokens,
        "total_duration_seconds": result.total_duration_seconds,
        "learning_outputs_persisted": result.learning_outputs_persisted,
        "insights_persisted": result.insights_persisted,
    }


@router.get("/{transcript_id}/questions", response_model=QuestionListOut)
def list_transcript_questions(
    transcript_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    difficulty: str | None = Query(None),
    question_type: str | None = Query(None, alias="question_type"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> QuestionListOut:
    if difficulty is not None and difficulty not in question_repo.VALID_DIFFICULTIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid difficulty. Must be one of: {sorted(question_repo.VALID_DIFFICULTIES)}",
        )
    if question_type is not None and question_type not in question_repo.VALID_QUESTION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid question_type. Must be one of: {sorted(question_repo.VALID_QUESTION_TYPES)}",
        )

    rows, total = question_repo.list_questions_for_transcript(
        db,
        transcript_id,
        offset=offset,
        limit=limit,
        difficulty=difficulty,
        question_type=question_type,
        order_desc=(order == "desc"),
    )

    return QuestionListOut(
        items=[QuestionOut.model_validate(q) for q in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/{transcript_id}/pipeline")
def run_pipeline(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    orchestrator = ProcessingOrchestratorService(db)
    try:
        result = orchestrator.process_transcript(transcript_id)
    except OrchestrationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("pipeline.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pipeline failed due to a database error",
        ) from exc

    return {
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id) if result.meeting_id else None,
        "status": result.status,
        "steps_completed": result.steps_completed,
        "total_steps": result.total_steps,
        "steps": result.step_results,
        "questions_generated": result.questions_generated,
        "model_used": result.model_used,
        "total_duration_seconds": result.total_duration_seconds,
        "error_message": result.error_message,
    }
