import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.repositories import transcripts as transcript_repo
from app.services.docx_export_service import DocxExportError, DocxExportService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/status")
def export_status() -> dict[str, str]:
    return {"status": "available"}


@router.post("/transcripts/{transcript_id}/docx")
def export_transcript_docx(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")

    service = DocxExportService(db)
    try:
        file_path = service.generate_docx(transcript_id)
    except DocxExportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("export.docx_generation_failed", extra={"transcript_id": str(transcript_id)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate DOCX") from exc

    filename = file_path.name
    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )

