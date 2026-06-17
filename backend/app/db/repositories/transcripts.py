import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.transcript import Transcript
from app.db.models.transcript_chunk import TranscriptChunk
from app.db.models.transcript_segment import TranscriptSegment

logger = get_logger(__name__)

VALID_STATUSES = {
    "metadata_received", "download_started", "downloaded", "failed",
    "parsing_started", "parsed", "parsing_failed",
    "cleaning_started", "cleaned", "cleaning_failed",
    "chunking_started", "chunked", "chunking_failed",
    "assessing", "generating", "generating_learning_outputs", "learning_generation_failed",
    "synthesizing", "synthesis_failed",
    "completed", "completed_with_warnings", "generation_failed",
}

VALID_ORDER_FIELDS = {"created_at", "updated_at", "status", "segment_count", "chunk_count", "question_count"}


def list_transcripts(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 20,
    status: str | None = None,
    order_by: str = "created_at",
    order_desc: bool = False,
) -> tuple[list[Transcript], int]:
    query = select(Transcript)
    count_query = select(func.count()).select_from(Transcript)

    if status is not None:
        query = query.where(Transcript.status == status)
        count_query = count_query.where(Transcript.status == status)

    order_column = getattr(Transcript, order_by, Transcript.created_at)
    query = query.order_by(order_column.desc() if order_desc else order_column.asc())
    query = query.offset(offset).limit(limit)

    rows = db.scalars(query).all()
    total = db.scalar(count_query)
    return rows, total


def get_transcript_detail(db: Session, transcript_id: uuid.UUID) -> dict | None:
    transcript = db.get(Transcript, transcript_id)
    if transcript is None:
        return None

    segment_count = db.scalar(
        select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript_id)
    )
    chunk_count = db.scalar(
        select(func.count()).select_from(TranscriptChunk).where(TranscriptChunk.transcript_id == transcript_id)
    )
    question_count_val = transcript.question_count
    if question_count_val is None:
        from app.db.models.question import Question
        question_count_val = db.scalar(
            select(func.count()).select_from(Question).where(Question.transcript_id == transcript_id)
        )

    return {
        "id": transcript.id,
        "meeting_id": transcript.meeting_id,
        "source_format": transcript.source_format,
        "status": transcript.status,
        "transcript_filename": transcript.transcript_filename,
        "raw_file_path": transcript.raw_file_path,
        "processed_file_path": transcript.processed_file_path,
        "zoom_file_id": transcript.zoom_file_id,
        "zoom_recording_type": transcript.zoom_recording_type,
        "file_type": transcript.file_type,
        "file_extension": transcript.file_extension,
        "file_size_bytes": transcript.file_size_bytes,
        "recording_start": transcript.recording_start,
        "recording_end": transcript.recording_end,
        "language": transcript.language,
        "segment_count": segment_count,
        "word_count": transcript.word_count,
        "cleaned_segment_count": transcript.cleaned_segment_count,
        "cleaned_word_count": transcript.cleaned_word_count,
        "chunk_count": chunk_count,
        "question_count": question_count_val or 0,
        "generation_model": transcript.generation_model,
        "checksum_sha256": transcript.checksum_sha256,
        "created_at": transcript.created_at,
        "updated_at": transcript.updated_at,
        "warnings": (transcript.metadata_json or {}).get("warnings", []),
    }


def get_by_zoom_file_id(db: Session, zoom_file_id: str | None) -> Transcript | None:
    if not zoom_file_id:
        return None
    return db.scalar(select(Transcript).where(Transcript.zoom_file_id == zoom_file_id))


def get_by_id(db: Session, transcript_id: uuid.UUID) -> Transcript | None:
    return db.get(Transcript, transcript_id)


def upsert_transcript_metadata(db: Session, transcript_data: dict) -> Transcript:
    transcript = get_by_zoom_file_id(db, transcript_data.get("zoom_file_id"))
    if transcript is None:
        transcript = Transcript()
        db.add(transcript)

    for key, value in transcript_data.items():
        setattr(transcript, key, value)

    db.flush()
    return transcript


def mark_download_started(db: Session, transcript: Transcript) -> None:
    transcript.status = "download_started"
    transcript.download_started_at = datetime.now(UTC)
    transcript.download_error = None
    db.flush()


def mark_downloaded(
    db: Session,
    transcript: Transcript,
    *,
    transcript_filename: str,
    raw_file_path: str,
    file_size_bytes: int,
    checksum_sha256: str,
) -> None:
    transcript.status = "downloaded"
    transcript.transcript_filename = transcript_filename
    transcript.raw_file_path = raw_file_path
    transcript.file_size_bytes = file_size_bytes
    transcript.checksum_sha256 = checksum_sha256
    transcript.downloaded_at = datetime.now(UTC)
    transcript.download_error = None
    db.flush()


def mark_download_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "failed"
    transcript.download_error = error_message
    db.flush()


def mark_parsing_started(db: Session, transcript: Transcript) -> None:
    transcript.status = "parsing_started"
    transcript.parse_error = None
    db.flush()


def replace_segments(db: Session, transcript: Transcript, parsed_segments: list[dict]) -> int:
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id))
    for segment in parsed_segments:
        db.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                meeting_id=transcript.meeting_id,
                start_time=_to_decimal(segment.get("start_time")),
                end_time=_to_decimal(segment.get("end_time")),
                speaker=segment.get("speaker"),
                text=segment["text"],
                sequence_number=segment["sequence_number"],
            )
        )
    db.flush()
    return len(parsed_segments)


def mark_parsed(db: Session, transcript: Transcript, *, segment_count: int, word_count: int) -> None:
    transcript.status = "parsed"
    transcript.segment_count = segment_count
    transcript.word_count = word_count
    transcript.parse_error = None
    db.flush()


def mark_parsing_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "parsing_failed"
    transcript.parse_error = error_message
    db.flush()


def mark_cleaning_started(db: Session, transcript: Transcript) -> None:
    transcript.status = "cleaning_started"
    transcript.cleaning_error = None
    db.flush()


def mark_cleaned(
    db: Session,
    transcript: Transcript,
    *,
    segments_cleaned: int,
    cleaned_word_count: int,
) -> None:
    transcript.status = "cleaned"
    transcript.cleaned_segment_count = segments_cleaned
    transcript.cleaned_word_count = cleaned_word_count
    transcript.cleaning_error = None
    db.flush()


def mark_cleaning_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "cleaning_failed"
    transcript.cleaning_error = error_message
    db.flush()


def mark_chunking_started(db: Session, transcript: Transcript) -> None:
    transcript.status = "chunking_started"
    transcript.chunking_error = None
    db.flush()


def mark_chunked(
    db: Session,
    transcript: Transcript,
    *,
    chunk_count: int,
) -> None:
    transcript.status = "chunked"
    transcript.chunk_count = chunk_count
    transcript.chunking_error = None
    db.flush()


def mark_chunking_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "chunking_failed"
    transcript.chunking_error = error_message
    db.flush()


def mark_assessing(db: Session, transcript: Transcript) -> None:
    transcript.status = "assessing"
    db.flush()


def mark_generation_started(db: Session, transcript: Transcript) -> None:
    transcript.status = "generating"
    transcript.generation_error = None
    db.flush()


def mark_generation_completed(
    db: Session,
    transcript: Transcript,
    *,
    question_count: int,
    generation_model: str,
) -> None:
    transcript.status = "completed"
    transcript.question_count = question_count
    transcript.generation_model = generation_model
    transcript.generation_error = None
    db.flush()


def mark_generation_completed_with_warnings(
    db: Session,
    transcript: Transcript,
    *,
    question_count: int,
    generation_model: str,
    warnings: list[str] | None = None,
) -> None:
    transcript.status = "completed_with_warnings"
    transcript.question_count = question_count
    transcript.generation_model = generation_model
    transcript.generation_error = None
    if warnings:
        meta = dict(transcript.metadata_json or {})
        meta["warnings"] = list(warnings)
        transcript.metadata_json = meta
    db.flush()


def mark_generation_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "generation_failed"
    transcript.generation_error = error_message
    db.flush()


def mark_generating_learning_outputs(db: Session, transcript: Transcript) -> None:
    transcript.status = "generating_learning_outputs"
    db.flush()


def mark_synthesizing(db: Session, transcript: Transcript) -> None:
    transcript.status = "synthesizing"
    db.flush()


def mark_learning_generation_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "learning_generation_failed"
    transcript.generation_error = error_message
    db.flush()


def mark_cancelled(db: Session, transcript: Transcript) -> None:
    if transcript.status in ("generating", "assessing"):
        transcript.status = "generation_failed"
        transcript.generation_error = "Processing run was cancelled"
    elif transcript.status in ("generating_learning_outputs",):
        transcript.status = "learning_generation_failed"
        transcript.generation_error = "Processing run was cancelled"
    elif transcript.status in ("synthesizing",):
        transcript.status = "synthesis_failed"
        transcript.generation_error = "Processing run was cancelled"
    elif transcript.status in ("download_started",):
        transcript.status = "failed"
        transcript.download_error = "Processing run was cancelled"
    elif transcript.status in ("parsing_started",):
        transcript.status = "parsing_failed"
        transcript.parse_error = "Processing run was cancelled"
    elif transcript.status in ("cleaning_started",):
        transcript.status = "cleaning_failed"
        transcript.cleaning_error = "Processing run was cancelled"
    elif transcript.status in ("chunking_started",):
        transcript.status = "chunking_failed"
        transcript.chunking_error = "Processing run was cancelled"
    db.flush()


def mark_synthesis_failed(db: Session, transcript: Transcript, error_message: str) -> None:
    transcript.status = "synthesis_failed"
    transcript.generation_error = error_message
    db.flush()


def replace_chunks(db: Session, transcript: Transcript, chunks: list) -> None:
    db.execute(delete(TranscriptChunk).where(TranscriptChunk.transcript_id == transcript.id))
    for i, chunk in enumerate(chunks):
        db.add(
            TranscriptChunk(
                transcript_id=transcript.id,
                meeting_id=transcript.meeting_id,
                chunk_index=i,
                text=chunk.text,
                word_count=chunk.word_count,
                start_time=_to_decimal(chunk.start_time),
                end_time=_to_decimal(chunk.end_time),
                speakers=chunk.speakers,
                segment_ids=chunk.segment_ids,
                segment_range_start=chunk.segment_range_start,
                segment_range_end=chunk.segment_range_end,
            )
        )
    db.flush()

    logger.info(
        "transcript_chunks.replaced",
        extra={
            "transcript_id": str(transcript.id),
            "chunk_count": len(chunks),
        },
    )


def _to_decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(float(value), 3)))
