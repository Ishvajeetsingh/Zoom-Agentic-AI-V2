from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError, ExternalServiceError
from app.core.logging import get_logger
from app.db.models.meeting import Meeting
from app.db.repositories import transcripts as transcript_repo
from app.integrations.zoom.client import ZoomApiClient

logger = get_logger(__name__)


class TranscriptDiscoveryError(AppError):
    """Raised when transcript discovery cannot be completed."""


@dataclass(frozen=True)
class DiscoveredTranscript:
    transcript_id: uuid.UUID | None
    zoom_file_id: str | None
    source_format: str | None
    file_type: str | None
    file_extension: str | None
    file_size_bytes: int | None
    download_url: str | None
    is_new: bool


@dataclass
class TranscriptDiscoveryResult:
    meeting_id: uuid.UUID
    zoom_uuid: str
    total_files_scanned: int = 0
    transcripts_found: int = 0
    new_transcripts: int = 0
    existing_transcripts: int = 0
    discovered: list[DiscoveredTranscript] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class TranscriptDiscoveryService:
    def __init__(
        self,
        db: Session,
        *,
        zoom_client: ZoomApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.config = config
        self.zoom_client = zoom_client or ZoomApiClient(config=config)

    def discover_for_meeting(self, meeting: Meeting) -> TranscriptDiscoveryResult:
        if not meeting.zoom_uuid:
            raise TranscriptDiscoveryError(f"Meeting {meeting.id} has no zoom_uuid")

        logger.info(
            "transcript_discovery.started",
            extra={"meeting_id": str(meeting.id), "zoom_uuid": meeting.zoom_uuid},
        )

        result = TranscriptDiscoveryResult(
            meeting_id=meeting.id,
            zoom_uuid=meeting.zoom_uuid,
        )

        metadata_json = meeting.metadata_json or {}
        recording_files_from_metadata = metadata_json.get("recording_files")

        if recording_files_from_metadata:
            recording_metadata = {"recording_files": recording_files_from_metadata}
            logger.info(
                "transcript_discovery.using_cached_metadata",
                extra={
                    "meeting_id": str(meeting.id),
                    "zoom_uuid": meeting.zoom_uuid,
                    "cached_file_count": len(recording_files_from_metadata),
                },
            )
        else:
            recording_metadata = self._fetch_recording_metadata(meeting.zoom_uuid)

        recording_files = recording_metadata.get("recording_files", []) or []
        result.total_files_scanned = len(recording_files)

        for file_data in recording_files:
            if not _looks_like_transcript(file_data):
                continue

            result.transcripts_found += 1
            try:
                discovered = self._process_transcript_file(meeting, file_data)
                result.discovered.append(discovered)
                if discovered.is_new:
                    result.new_transcripts += 1
                else:
                    result.existing_transcripts += 1
            except Exception as exc:
                error_msg = f"zoom_file_id={file_data.get('id')}: {exc}"
                result.errors.append(error_msg)
                logger.warning(
                    "transcript_discovery.file_failed",
                    extra={"error": error_msg},
                )

        self.db.flush()

        logger.info(
            "transcript_discovery.completed",
            extra={
                "meeting_id": str(meeting.id),
                "zoom_uuid": meeting.zoom_uuid,
                "transcripts_found": result.transcripts_found,
                "new_transcripts": result.new_transcripts,
                "existing_transcripts": result.existing_transcripts,
            },
        )

        return result

    def discover_for_all_meetings(
        self,
        *,
        only_without_transcripts: bool = True,
    ) -> list[TranscriptDiscoveryResult]:
        from sqlalchemy import select
        from app.db.models.transcript import Transcript

        stmt = select(Meeting).where(Meeting.source == "zoom")
        if only_without_transcripts:
            has_transcript_sq = (
                select(Transcript.meeting_id)
                .where(Transcript.meeting_id.isnot(None))
                .distinct()
            )
            stmt = stmt.where(Meeting.id.notin_(has_transcript_sq))

        meetings = self.db.scalars(stmt).all()

        results: list[TranscriptDiscoveryResult] = []
        for meeting in meetings:
            try:
                result = self.discover_for_meeting(meeting)
                results.append(result)
            except Exception as exc:
                logger.warning(
                    "transcript_discovery.meeting_failed",
                    extra={
                        "meeting_id": str(meeting.id),
                        "zoom_uuid": meeting.zoom_uuid,
                        "error": str(exc),
                    },
                )
                results.append(
                    TranscriptDiscoveryResult(
                        meeting_id=meeting.id,
                        zoom_uuid=meeting.zoom_uuid or "",
                        errors=[str(exc)],
                    )
                )

        self.db.commit()
        return results

    def _fetch_recording_metadata(self, zoom_uuid: str) -> dict:
        try:
            return self.zoom_client.get_recording_metadata(zoom_uuid)
        except ExternalServiceError as exc:
            raise TranscriptDiscoveryError(
                f"Failed to fetch recording metadata for {zoom_uuid}: {exc}"
            ) from exc

    def _process_transcript_file(
        self, meeting: Meeting, file_data: dict[str, Any]
    ) -> DiscoveredTranscript:
        zoom_file_id = _to_optional_str(file_data.get("id"))

        existing = transcript_repo.get_by_zoom_file_id(self.db, zoom_file_id)

        if existing is None:
            transcript = transcript_repo.upsert_transcript_metadata(
                self.db,
                {
                    "meeting_id": meeting.id,
                    "source_format": _source_format(file_data),
                    "status": "metadata_received",
                    "zoom_file_id": zoom_file_id,
                    "zoom_recording_type": file_data.get("recording_type"),
                    "file_type": file_data.get("file_type"),
                    "file_extension": file_data.get("file_extension"),
                    "file_size_bytes": _to_optional_int(file_data.get("file_size")),
                    "recording_start": _parse_datetime(file_data.get("recording_start")),
                    "recording_end": _parse_datetime(file_data.get("recording_end")),
                    "play_url": file_data.get("play_url"),
                    "download_url": file_data.get("download_url"),
                    "language": file_data.get("language"),
                    "metadata_json": file_data,
                },
            )
            self.db.flush()

            return DiscoveredTranscript(
                transcript_id=transcript.id,
                zoom_file_id=zoom_file_id,
                source_format=transcript.source_format,
                file_type=transcript.file_type,
                file_extension=transcript.file_extension,
                file_size_bytes=transcript.file_size_bytes,
                download_url=transcript.download_url,
                is_new=True,
            )

        return DiscoveredTranscript(
            transcript_id=existing.id,
            zoom_file_id=zoom_file_id,
            source_format=existing.source_format,
            file_type=existing.file_type,
            file_extension=existing.file_extension,
            file_size_bytes=existing.file_size_bytes,
            download_url=existing.download_url,
            is_new=False,
        )


def _looks_like_transcript(file: dict[str, Any]) -> bool:
    file_type = str(file.get("file_type") or "").upper()
    extension = str(file.get("file_extension") or "").upper()
    recording_type = str(file.get("recording_type") or "").lower()
    return (
        file_type in {"TRANSCRIPT", "CC", "VTT"}
        or extension in {"VTT", "JSON"}
        or "transcript" in recording_type
    )


def _source_format(file: dict[str, Any]) -> str | None:
    extension = str(file.get("file_extension") or "").lower()
    if extension:
        return extension
    file_type = str(file.get("file_type") or "").lower()
    return file_type or None


def _parse_datetime(value: Any) -> datetime | None:
    from datetime import UTC, datetime

    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
