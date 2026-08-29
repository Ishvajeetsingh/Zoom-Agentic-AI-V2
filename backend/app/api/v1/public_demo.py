from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db.models.meeting import Meeting
from app.db.models.transcript import Transcript
from app.db.repositories import questions as question_repo
from app.schemas.questions import QuestionListOut, QuestionOut
from app.services.processing_orchestrator_service import (
    ProcessingOrchestratorService,
)


router = APIRouter()


ALLOWED_EXTENSIONS = {
    ".txt",
    ".vtt",
    ".srt",
}


def require_public_demo() -> None:
    if not settings.public_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


def get_public_upload_transcript(
    db: Session,
    transcript_id: uuid.UUID,
) -> Transcript:
    transcript = db.get(
        Transcript,
        transcript_id,
    )

    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found",
        )

    meeting = db.get(
        Meeting,
        transcript.meeting_id,
    )

    if (
        meeting is None
        or meeting.source != "upload"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This transcript is not available "
                "through the public demo."
            ),
        )

    return transcript


@router.post(
    "/transcripts/upload",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_public_demo)
    ],
)
async def upload_transcript(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:

    filename = (
        file.filename
        or "transcript.txt"
    )

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. "
                "Allowed types: TXT, VTT, SRT."
            ),
        )

    content = await file.read(
        settings.public_demo_max_upload_bytes
        + 1
    )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if (
        len(content)
        >
        settings.public_demo_max_upload_bytes
    ):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Public demo uploads are limited "
                "to 2 MB."
            ),
        )

    try:
        content.decode(
            "utf-8",
            errors="strict",
        )
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Transcript must be UTF-8 text."
            ),
        ) from exc


    meeting = Meeting(
        source="upload",
        topic=(
            "Public Demo Upload - "
            f"{Path(filename).stem[:80]}"
        ),
        metadata_json={
            "public_demo": True,
        },
    )

    db.add(meeting)
    db.flush()


    storage_dir = (
        Path(
            settings.transcript_storage_dir
        )
        / "public_demo"
    )

    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    transcript_id = uuid.uuid4()

    safe_filename = (
        f"{transcript_id}"
        f"{extension}"
    )

    raw_file_path = (
        storage_dir
        / safe_filename
    )

    raw_file_path.write_bytes(
        content
    )


    source_format = (
        extension
        .lstrip(".")
    )


    transcript = Transcript(
        id=transcript_id,
        meeting_id=meeting.id,
        source_format=source_format,
        status="downloaded",
        transcript_filename=filename,
        raw_file_path=str(
            raw_file_path
        ),
        file_type=source_format,
        file_extension=extension,
        file_size_bytes=len(content),
    )

    db.add(transcript)
    db.flush()


    # Match the existing TranscriptUploadResponse
    # expected by the frontend.
    return {
        "transcript_id":
            str(transcript.id),

        "meeting_id":
            str(meeting.id),

        "transcript_filename":
            filename,

        "file_size_bytes":
            len(content),

        "source_format":
            source_format,

        "status":
            transcript.status,
    }


@router.post(
    "/transcripts/{transcript_id}/pipeline",
    dependencies=[
        Depends(require_public_demo)
    ],
)
@router.post(
    "/transcripts/{transcript_id}/pipeline",
    dependencies=[
        Depends(require_public_demo)
    ],
)
def run_transcript_pipeline(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    transcript = get_public_upload_transcript(
        db,
        transcript_id,
    )

    orchestrator = ProcessingOrchestratorService(
        db
    )

    result = orchestrator.process_transcript(
        transcript.id
    )

    # These are the six steps displayed by the existing
    # UploadTranscriptPage processing timeline.
    public_step_names = [
        "parse",
        "clean",
        "chunk",
        "generate",
        "generate_learning_outputs",
        "synthesize",
    ]

    # Start every public-facing step as waiting.
    step_statuses: dict[str, dict] = {
        step_name: {
            "step": step_name,
            "status": "waiting",
            "message": None,
        }
        for step_name in public_step_names
    }

    # Translate the real orchestrator step results into the
    # PipelineResponse format expected by the frontend.
    for step_result in result.step_results:
        step_name = (
            step_result.get("step")
            or step_result.get("name")
        )

        if not step_name:
            continue

        # Ignore internal orchestrator steps that are not shown
        # in the public upload timeline.
        if step_name not in step_statuses:
            continue

        raw_status = str(
            step_result.get("status")
            or ""
        ).lower()

        if raw_status in {
            "completed",
            "success",
            "succeeded",
            "skipped",
        }:
            frontend_status = "completed"

        elif raw_status in {
            "failed",
            "error",
        }:
            frontend_status = "failed"

        else:
            frontend_status = "waiting"

        step_statuses[step_name] = {
            "step": step_name,
            "status": frontend_status,
            "message": (
                step_result.get("message")
                or step_result.get("error")
                or step_result.get("error_message")
            ),
        }

    # If the complete orchestration succeeded, all six
    # public-facing stages are considered completed.
    #
    # This also handles internal orchestrator step names that
    # may not map one-to-one onto the simplified public timeline.
    if result.status in {
        "completed",
        "completed_with_warnings",
    }:
        for step_name in public_step_names:
            step_statuses[step_name]["status"] = "completed"

    errors: list[str] = []

    if result.error_message:
        errors.append(
            result.error_message
        )

    return {
        "transcript_id": str(
            result.transcript_id
        ),
        "status": result.status,
        "steps": [
            step_statuses[step_name]
            for step_name in public_step_names
        ],
        "errors": errors,
    }
@router.get(
    "/transcripts/{transcript_id}/questions",
    response_model=QuestionListOut,
    dependencies=[
        Depends(require_public_demo)
    ],
)
def get_generated_questions(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> QuestionListOut:
    get_public_upload_transcript(
        db,
        transcript_id,
    )

    rows = question_repo.get_by_transcript_id(
        db,
        transcript_id,
    )

    items = [
        QuestionOut.model_validate(question)
        for question in rows
    ]

    return QuestionListOut(
        items=items,
        total=len(items),
        offset=0,
        limit=len(items),
    )