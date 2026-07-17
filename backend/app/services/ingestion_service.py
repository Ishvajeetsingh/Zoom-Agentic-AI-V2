from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError, ExternalServiceError
from app.core.logging import get_logger
from app.db.models.transcript import Transcript
from app.db.repositories import meetings as meeting_repo
from app.db.repositories import transcripts as transcript_repo
from app.integrations.zoom.client import ZoomApiClient

logger = get_logger(__name__)


class ZoomIngestionError(AppError):
    """Raised when Zoom meeting ingestion cannot be completed."""


@dataclass(frozen=True)
class ZoomIngestionResult:
    meeting_id: uuid.UUID
    transcript_id: uuid.UUID | None
    recording_found: bool
    zoom_meeting_id: str | None
    zoom_uuid: str
    topic: str | None


class ZoomIngestionService:
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

    def ingest_meeting(self, meeting_uuid: str) -> ZoomIngestionResult:
        logger.info(
            "zoom_ingestion.started",
            extra={"meeting_uuid": meeting_uuid},
        )

        recording_metadata = self._fetch_recording_metadata(meeting_uuid)

        meeting = self._upsert_meeting(recording_metadata)

        transcript_file = self._find_transcript_file(recording_metadata)

        transcript: Transcript | None = None
        if transcript_file is not None:
            transcript = transcript_repo.upsert_transcript_metadata(
                self.db,
                {
                    "meeting_id": meeting.id,
                    "source_format": _source_format(transcript_file),
                    "status": "metadata_received",
                    "zoom_file_id": _to_optional_str(transcript_file.get("id")),
                    "zoom_recording_type": transcript_file.get("recording_type"),
                    "file_type": transcript_file.get("file_type"),
                    "file_extension": transcript_file.get("file_extension"),
                    "file_size_bytes": _to_optional_int(transcript_file.get("file_size")),
                    "recording_start": _parse_datetime(transcript_file.get("recording_start")),
                    "recording_end": _parse_datetime(transcript_file.get("recording_end")),
                    "play_url": transcript_file.get("play_url"),
                    "download_url": transcript_file.get("download_url"),
                    "language": transcript_file.get("language"),
                    "metadata_json": transcript_file,
                },
            )

        self.db.commit()

        logger.info(
            "zoom_ingestion.completed",
            extra={
                "meeting_uuid": meeting_uuid,
                "meeting_id": str(meeting.id),
                "transcript_id": str(transcript.id) if transcript else None,
                "recording_found": transcript_file is not None,
            },
        )

        return ZoomIngestionResult(
            meeting_id=meeting.id,
            transcript_id=transcript.id if transcript else None,
            recording_found=transcript_file is not None,
            zoom_meeting_id=meeting.zoom_meeting_id,
            zoom_uuid=meeting_uuid,
            topic=meeting.topic,
        )

    def _fetch_recording_metadata(self, meeting_uuid: str) -> dict:
        try:
            return self.zoom_client.get_recording_metadata(meeting_uuid)
        except ExternalServiceError as exc:
            raise ZoomIngestionError(
                f"Failed to retrieve recording metadata for meeting UUID {meeting_uuid}: {exc}"
            ) from exc

    def _upsert_meeting(self, recording_metadata: dict):
        meeting_uuid = _to_optional_str(recording_metadata.get("uuid"))
        if not meeting_uuid:
            raise ZoomIngestionError(
                "Zoom recording metadata did not include a meeting UUID"
            )

        return meeting_repo.upsert_zoom_meeting(
            self.db,
            {
                "source": "zoom",
                "zoom_meeting_id": _to_optional_str(recording_metadata.get("id")),
                "zoom_uuid": meeting_uuid,
                "account_id": _to_optional_str(recording_metadata.get("account_id")),
                "host_id": _to_optional_str(recording_metadata.get("host_id")),
                "host_email": _to_optional_str(recording_metadata.get("host_email")),
                "topic": recording_metadata.get("topic"),
                "start_time": _parse_datetime(recording_metadata.get("start_time")),
                "timezone": recording_metadata.get("timezone"),
                "duration_minutes": _to_optional_int(recording_metadata.get("duration")),
                "participant_count": _to_optional_int(recording_metadata.get("participant_count")),
                "metadata_json": recording_metadata,
            },
        )

    @staticmethod
    def _find_transcript_file(recording_metadata: dict) -> dict | None:
        recording_files = recording_metadata.get("recording_files", []) or []
        # Per-meeting VTT-before-SRT priority (Part 1): when a recording
        # surfaces BOTH a VTT transcript and an SRT transcript, prefer the
        # VTT (existing behaviour); only when no VTT is surfaced is an SRT
        # transcript registered as a first-class transcript. Non-VTT,
        # non-SRT formats (CHAT/CC/JSON/generic "transcript" by recording
        # type) keep their original first-match preference and are NOT
        # displaced by SRT — preserving existing prioritization.
        first_match: dict | None = None
        srt_match: dict | None = None
        # VTT wins outright once found: short-circuit the scan (no
        # downstream order can beat it, and the existing behaviour
        # already returned the first scan match, so early-stop cannot
        # introduce a regression for non-VTT/non-SRT formats since VTT
        # would have won anyway).
        for file in recording_files:
            if not _looks_like_transcript(file):
                continue
            if first_match is None:
                first_match = file
            fmt = _recording_format(file)
            if fmt == "vtt":
                first_match = file
                srt_match = None
                break
            if fmt == "srt" and srt_match is None:
                srt_match = file
        return first_match or srt_match


def _looks_like_transcript(file: dict[str, Any]) -> bool:
    file_type = str(file.get("file_type") or "").upper()
    extension = str(file.get("file_extension") or "").upper()
    recording_type = str(file.get("recording_type") or "").lower()
    return (
        file_type in {"TRANSCRIPT", "CC", "VTT", "SRT"}
        or extension in {"VTT", "JSON", "SRT"}
        or "transcript" in recording_type
    )


def _source_format(file: dict[str, Any]) -> str | None:
    extension = str(file.get("file_extension") or "").lower()
    if extension:
        return extension
    file_type = str(file.get("file_type") or "").lower()
    return file_type or None


def _recording_format(file: dict[str, Any]) -> str | None:
    """Normalise a discovered file's transcript format to one of
    "vtt" / "srt" / "json" / None. Used by `_find_transcript_file` to
    apply per-meeting VTT-before-SRT prioritization (identical rule to
    TranscriptDiscoveryService and ZoomWebhookService). Falls back on
    file_type when file_extension is missing.
    """
    extension = str(file.get("file_extension") or "").lower()
    if extension:
        return extension
    file_type = str(file.get("file_type") or "").lower()
    return file_type or None


def _parse_datetime(value: Any) -> datetime | None:
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

