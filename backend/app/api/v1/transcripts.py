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
from app.services.classification_service import ClassificationService
from app.services.professor_ranking_service import ProfessorRankingService
from app.services.question_service import (
    QuestionGenerationError,
    preview_regenerate_mcqs,
    regenerate_mcqs_for_transcript,
)
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
    if extension not in {"vtt", "json", "txt", "srt"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '.{extension}'. Supported: .vtt, .json, .txt, .srt",
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
    elif extension == "srt":
        file_type = "SRT"
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
    orchestrator = ProcessingOrchestratorService(db)
    try:
        result = orchestrator.process_transcript(transcript_id)
    except OrchestrationError as exc:
        db.rollback()
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
        "total_questions": result.questions_generated,
        "questions_persisted": result.questions_generated,
        "chunks_loaded": 0,
        "questions_generated": result.questions_generated,
        "questions_validated": 0,
        "duplicates_removed": 0,
        "model_used": result.model_used,
        "total_prompt_tokens": None,
        "total_completion_tokens": None,
        "total_duration_seconds": result.total_duration_seconds,
        "learning_outputs_persisted": 0,
        "insights_persisted": False,
    }


@router.get("/{transcript_id}/questions", response_model=QuestionListOut)
def list_transcript_questions(
    transcript_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    difficulty: str | None = Query(None),
    question_type: str | None = Query(None, alias="question_type"),
    category: str | None = Query(None),
    bloom_taxonomy: str | None = Query(None, alias="bloom"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    top_n: int | None = Query(None, ge=1, le=100, alias="top"),
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
    if category is not None and category not in question_repo.VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {sorted(question_repo.VALID_CATEGORIES)}",
        )
    if bloom_taxonomy is not None and bloom_taxonomy not in question_repo.VALID_BLOOM_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bloom level. Must be one of: {sorted(question_repo.VALID_BLOOM_LEVELS)}",
        )

    effective_offset = 0 if top_n else offset
    effective_limit = top_n if top_n else limit

    rows, total = question_repo.list_questions_for_transcript(
        db,
        transcript_id,
        offset=effective_offset,
        limit=effective_limit,
        difficulty=difficulty,
        question_type=question_type,
        category=category,
        bloom_taxonomy=bloom_taxonomy,
        order_desc=(order == "desc"),
        order_by_educational=bool(top_n),
    )

    return QuestionListOut(
        items=[QuestionOut.model_validate(q) for q in rows],
        total=total,
        offset=effective_offset,
        limit=effective_limit,
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


@router.post("/{transcript_id}/classify")
def classify_transcript(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    service = ClassificationService(db)
    try:
        result = service.classify_transcript(transcript_id)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("classify.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Classification failed due to a database error",
        ) from exc

    return result


@router.post("/{transcript_id}/recompute-rankings")
def recompute_rankings(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    service = ClassificationService(db)
    try:
        result = service.recompute_rankings(transcript_id)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("recompute_rankings.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ranking recomputation failed due to a database error",
        ) from exc

    return result


@router.post("/classify-all")
def classify_all_transcripts(
    db: Session = Depends(get_db),
) -> dict[str, object]:
    result = ClassificationService.classify_all_unclassified(db)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("classify_all.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk classification failed due to a database error",
        ) from exc
    return result


@router.post("/{transcript_id}/regenerate-mcqs")
def regenerate_mcqs(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    try:
        result = regenerate_mcqs_for_transcript(db, transcript_id)
        db.commit()
    except QuestionGenerationError as exc:
        db.rollback()
        logger.warning(
            "regenerate_mcqs.generation_error",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("regenerate_mcqs.database_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Regeneration failed due to a database error",
        ) from exc

    return {
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id),
        "previous_count": result.previous_count,
        "new_count": result.new_count,
        "chunks_processed": result.chunks_processed,
        "duplicates_removed": result.duplicates_removed,
        "classified": result.classified,
        "ranked": result.ranked,
        "model_used": result.model_used,
        "aborted": result.aborted,
        "abort_reason": result.abort_reason,
    }


@router.post("/{transcript_id}/preview-regenerate-mcqs")
def preview_regenerate_mcqs_endpoint(
    transcript_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    try:
        result = preview_regenerate_mcqs(db, transcript_id)
    except QuestionGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("preview_regenerate.unexpected_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    questions_preview = result.questions[:limit]
    return {
        "transcript_id": str(result.transcript_id),
        "meeting_id": str(result.meeting_id),
        "previous_count": result.previous_count,
        "regenerated_count": result.regenerated_count,
        "chunks_processed": result.chunks_processed,
        "duplicates_removed": result.duplicates_removed,
        "model_used": result.model_used,
        "questions": [
            {
                "question_text": q.question_text,
                "question_style": q.question_style,
                "bloom_level": q.bloom_level,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "chunk_index": q.chunk_index,
            }
            for q in questions_preview
        ],
    }


@router.post("/{transcript_id}/rank-questions")
def rank_questions(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    service = ProfessorRankingService(db)
    result = service.rank_questions(transcript_id)

    return {
        "transcript_id": str(result.transcript_id),
        "total_questions": result.total_questions,
        "ranked_count": len(result.ranked),
        "top_10_count": len(result.top_10),
        "top_20_count": len(result.top_20),
        "top_50_count": len(result.top_50),
        "hierarchy_verified": result.hierarchy_verified,
        "concept_coverage": result.concept_coverage,
        "top_10": [_ranked_dict(rq) for rq in result.top_10],
    }


@router.get("/{transcript_id}/ranking-preview")
def ranking_preview(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    service = ProfessorRankingService(db)
    return service.get_ranking_preview(transcript_id)


def _ranked_dict(rq) -> dict:
    return {
        "rank": rq.rank,
        "composite_score": rq.composite_score,
        "question_text": rq.question_text[:120],
        "bloom_level": rq.bloom_level,
        "category": rq.category,
        "difficulty": rq.difficulty,
        "educational_score": rq.educational_score,
        "chunk_index": rq.chunk_index,
        "rank_reasons": rq.rank_reasons,
        "concepts_represented": rq.concepts,
    }
