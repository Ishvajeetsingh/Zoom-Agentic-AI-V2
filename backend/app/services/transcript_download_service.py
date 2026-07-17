import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError, ExternalServiceError
from app.core.logging import get_logger
from app.db.models.transcript import Transcript
from app.db.repositories import transcripts
from app.integrations.zoom.client import ZoomApiClient
from app.services.storage_service import LocalTranscriptStorage, sanitize_filename

logger = get_logger(__name__)


class TranscriptDownloadError(AppError):
    """Raised when transcript download cannot be completed."""


@dataclass(frozen=True)
class TranscriptDownloadResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    status: str
    transcript_filename: str
    raw_file_path: str
    file_size_bytes: int
    checksum_sha256: str


class TranscriptDownloadService:
    def __init__(
        self,
        db: Session,
        *,
        zoom_client: ZoomApiClient | None = None,
        storage: LocalTranscriptStorage | None = None,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.zoom_client = zoom_client or ZoomApiClient(config=config)
        self.storage = storage or LocalTranscriptStorage(config)
        self.config = config

    def download_transcript(self, transcript_id: uuid.UUID) -> TranscriptDownloadResult:
        transcript = transcripts.get_by_id(self.db, transcript_id)
        if transcript is None:
            raise TranscriptDownloadError(f"Transcript not found: {transcript_id}")

        if not transcript.download_url:
            self._refresh_transcript_download_url(transcript)

        if not transcript.download_url:
            raise TranscriptDownloadError("Transcript metadata does not include a download URL")

        transcripts.mark_download_started(self.db, transcript)
        self.db.commit()

        logger.info(
            "transcript_download.started",
            extra={
                "transcript_id": str(transcript.id),
                "meeting_id": str(transcript.meeting_id),
                "zoom_file_id": transcript.zoom_file_id,
            },
        )

        try:
            path, size, checksum = self._download_with_retries(transcript)
            transcripts.mark_downloaded(
                self.db,
                transcript,
                transcript_filename=path.name,
                raw_file_path=str(path),
                file_size_bytes=size,
                checksum_sha256=checksum,
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            transcript = transcripts.get_by_id(self.db, transcript_id)
            if transcript is not None:
                transcripts.mark_download_failed(self.db, transcript, str(exc))
                self.db.commit()
            logger.exception(
                "transcript_download.failed",
                extra={"transcript_id": str(transcript_id), "error": str(exc)},
            )
            raise

        logger.info(
            "transcript_download.completed",
            extra={
                "transcript_id": str(transcript.id),
                "meeting_id": str(transcript.meeting_id),
                "path": str(path),
                "file_size_bytes": size,
            },
        )
        return TranscriptDownloadResult(
            transcript_id=transcript.id,
            meeting_id=transcript.meeting_id,
            status=transcript.status,
            transcript_filename=path.name,
            raw_file_path=str(path),
            file_size_bytes=size,
            checksum_sha256=checksum,
        )

    def _download_with_retries(self, transcript: Transcript) -> tuple[Path, int, str]:
        last_error: Exception | None = None
        attempts = max(self.config.zoom_oauth_retry_attempts, 1)

        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1:
                    self._refresh_transcript_download_url(transcript)
                    self.db.commit()

                response = self.zoom_client.stream_download(
                    transcript.download_url,
                    force_refresh_token=attempt > 1,
                )
                try:
                    if response.status_code in {401, 403, 404}:
                        raise ExpiredDownloadUrlError(
                            f"Zoom download URL rejected with status {response.status_code}"
                        )
                    if response.status_code in {429, 500, 502, 503, 504}:
                        raise TemporaryZoomDownloadError(
                            f"Zoom temporary download failure: {response.status_code}"
                        )
                    response.raise_for_status()
                    return self._stream_response_to_disk(transcript, response)
                finally:
                    response.close()
            except (ExpiredDownloadUrlError, TemporaryZoomDownloadError, httpx.HTTPError) as exc:
                last_error = exc
                logger.warning(
                    "transcript_download.retryable_error",
                    extra={
                        "transcript_id": str(transcript.id),
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                )
                if attempt == attempts:
                    break

        raise ExternalServiceError("Transcript download failed after retry attempts") from last_error

    def _stream_response_to_disk(
        self,
        transcript: Transcript,
        response: httpx.Response,
    ) -> tuple[Path, int, str]:
        filename = self._filename_for_transcript(transcript)
        destination = self.storage.raw_transcript_path(
            meeting_id=str(transcript.meeting_id),
            filename=filename,
        )
        temporary_path = destination.with_suffix(destination.suffix + ".part")

        digest = hashlib.sha256()
        total_bytes = 0
        with temporary_path.open("wb") as file:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                file.write(chunk)
                digest.update(chunk)
                total_bytes += len(chunk)

        temporary_path.replace(destination)
        return destination, total_bytes, digest.hexdigest()

    def _refresh_transcript_download_url(self, transcript: Transcript) -> None:
        meeting = transcript.meeting
        if meeting is None or not meeting.zoom_uuid:
            raise TranscriptDownloadError("Cannot refresh download URL without Zoom meeting UUID")

        metadata = self.zoom_client.get_recording_metadata(meeting.zoom_uuid)
        matching_file = self._find_matching_transcript_file(metadata, transcript)
        if not matching_file:
            raise TranscriptDownloadError("Could not locate transcript file in refreshed Zoom metadata")

        transcript.download_url = matching_file.get("download_url")
        transcript.metadata_json = matching_file
        transcript.file_size_bytes = _to_optional_int(matching_file.get("file_size"))
        transcript.file_type = matching_file.get("file_type")
        transcript.file_extension = matching_file.get("file_extension")
        transcript.source_format = _source_format(matching_file)
        self.db.flush()

        logger.info(
            "transcript_download.metadata_refreshed",
            extra={
                "transcript_id": str(transcript.id),
                "meeting_id": str(transcript.meeting_id),
                "zoom_file_id": transcript.zoom_file_id,
            },
        )

    @staticmethod
    def _find_matching_transcript_file(metadata: dict, transcript: Transcript) -> dict | None:
        files = metadata.get("recording_files", []) or []
        if transcript.zoom_file_id:
            for file in files:
                if str(file.get("id")) == transcript.zoom_file_id:
                    return file
        for file in files:
            if _looks_like_transcript(file):
                return file
        return None

    @staticmethod
    def _filename_for_transcript(transcript: Transcript) -> str:
        if transcript.transcript_filename:
            return sanitize_filename(transcript.transcript_filename)

        extension = (transcript.file_extension or transcript.source_format or "vtt").lower()
        if extension.startswith("."):
            extension = extension[1:]
        if extension not in {"vtt", "json", "txt", "srt"}:
            extension = "vtt"

        identifier = transcript.zoom_file_id or str(transcript.id)
        return sanitize_filename(f"{identifier}.{extension}")


class ExpiredDownloadUrlError(ExternalServiceError):
    """Raised for statuses that usually mean the stored download URL/token is no longer usable."""


class TemporaryZoomDownloadError(ExternalServiceError):
    """Raised for retryable Zoom-side temporary failures."""


def _looks_like_transcript(file: dict) -> bool:
    file_type = str(file.get("file_type") or "").upper()
    extension = str(file.get("file_extension") or "").upper()
    recording_type = str(file.get("recording_type") or "").lower()
    return file_type in {"TRANSCRIPT", "CC", "VTT", "SRT"} or extension in {"VTT", "SRT"} or "transcript" in recording_type


def _source_format(file: dict) -> str | None:
    extension = str(file.get("file_extension") or "").lower()
    if extension:
        return extension
    file_type = str(file.get("file_type") or "").lower()
    return file_type or None


def _to_optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
