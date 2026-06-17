from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError, ConfigurationError, ExternalServiceError
from app.core.logging import get_logger
from app.db.models.meeting import Meeting
from app.db.repositories import meetings as meeting_repo
from app.integrations.zoom.client import ZoomApiClient

logger = get_logger(__name__)


class MeetingDiscoveryError(AppError):
    """Raised when meeting discovery cannot be completed."""


@dataclass(frozen=True)
class DiscoveredMeeting:
    zoom_uuid: str
    zoom_meeting_id: str | None
    topic: str | None
    start_time: datetime | None
    duration_minutes: int | None
    recording_count: int
    has_transcript: bool
    meeting_id: uuid.UUID | None = None
    is_new: bool = False


@dataclass
class DiscoveryResult:
    total_found: int = 0
    new_meetings: int = 0
    existing_meetings: int = 0
    meetings_with_transcripts: int = 0
    discovered: list[DiscoveredMeeting] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class MeetingDiscoveryService:
    def __init__(
        self,
        db: Session,
        *,
        zoom_client: ZoomApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.config = config
        self._external_client = zoom_client is not None
        self.zoom_client = zoom_client or ZoomApiClient(config=config)

    def discover_meetings(
        self,
        *,
        user_id: str = "me",
        from_date: str | None = None,
        to_date: str | None = None,
        lookback_days: int | None = 30,
    ) -> DiscoveryResult:
        self._validate_config()

        if from_date is None and lookback_days is not None:
            from_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        if to_date is None:
            to_date = datetime.now(UTC).strftime("%Y-%m-%d")

        logger.info(
            "meeting_discovery.started",
            extra={"user_id": user_id, "from_date": from_date, "to_date": to_date},
        )

        result = DiscoveryResult()
        next_page_token: str | None = None

        while True:
            try:
                response = self.zoom_client.list_user_recordings(
                    user_id=user_id,
                    from_date=from_date,
                    to_date=to_date,
                    next_page_token=next_page_token,
                )
            except ExternalServiceError as exc:
                raise MeetingDiscoveryError(f"Failed to list Zoom recordings: {exc}") from exc

            meetings_data = response.get("meetings", []) or []
            result.total_found += len(meetings_data)

            for meeting_data in meetings_data:
                try:
                    discovered = self._process_discovered_meeting(meeting_data)
                    result.discovered.append(discovered)
                    if discovered.is_new:
                        result.new_meetings += 1
                    else:
                        result.existing_meetings += 1
                    if discovered.has_transcript:
                        result.meetings_with_transcripts += 1
                except Exception as exc:
                    error_msg = f"meeting_uuid={meeting_data.get('uuid')}: {exc}"
                    result.errors.append(error_msg)
                    logger.warning(
                        "meeting_discovery.meeting_failed",
                        extra={"error": error_msg},
                    )

            next_page_token = response.get("next_page_token")
            if not next_page_token:
                break

        self.db.commit()

        logger.info(
            "meeting_discovery.completed",
            extra={
                "total_found": result.total_found,
                "new_meetings": result.new_meetings,
                "existing_meetings": result.existing_meetings,
                "with_transcripts": result.meetings_with_transcripts,
                "errors": len(result.errors),
            },
        )

        return result

    def _process_discovered_meeting(self, meeting_data: dict[str, Any]) -> DiscoveredMeeting:
        zoom_uuid = _to_optional_str(meeting_data.get("uuid"))
        if not zoom_uuid:
            raise MeetingDiscoveryError("Discovered meeting missing UUID")

        existing = meeting_repo.get_by_zoom_uuid(self.db, zoom_uuid)

        recording_files = meeting_data.get("recording_files", []) or []
        has_transcript = any(_looks_like_transcript(f) for f in recording_files)

        if existing is None:
            meeting = meeting_repo.upsert_zoom_meeting(
                self.db,
                {
                    "source": "zoom",
                    "zoom_meeting_id": _to_optional_str(meeting_data.get("id")),
                    "zoom_uuid": zoom_uuid,
                    "account_id": _to_optional_str(meeting_data.get("account_id")),
                    "host_id": _to_optional_str(meeting_data.get("host_id")),
                    "host_email": _to_optional_str(meeting_data.get("host_email")),
                    "topic": meeting_data.get("topic"),
                    "start_time": _parse_datetime(meeting_data.get("start_time")),
                    "timezone": meeting_data.get("timezone"),
                    "duration_minutes": _to_optional_int(meeting_data.get("duration")),
                    "participant_count": _to_optional_int(meeting_data.get("participant_count")),
                    "metadata_json": meeting_data,
                },
            )
            self.db.flush()

            return DiscoveredMeeting(
                zoom_uuid=zoom_uuid,
                zoom_meeting_id=_to_optional_str(meeting_data.get("id")),
                topic=meeting_data.get("topic"),
                start_time=_parse_datetime(meeting_data.get("start_time")),
                duration_minutes=_to_optional_int(meeting_data.get("duration")),
                recording_count=len(recording_files),
                has_transcript=has_transcript,
                meeting_id=meeting.id,
                is_new=True,
            )

        return DiscoveredMeeting(
            zoom_uuid=zoom_uuid,
            zoom_meeting_id=_to_optional_str(meeting_data.get("id")),
            topic=meeting_data.get("topic"),
            start_time=_parse_datetime(meeting_data.get("start_time")),
            duration_minutes=_to_optional_int(meeting_data.get("duration")),
            recording_count=len(recording_files),
            has_transcript=has_transcript,
            meeting_id=existing.id,
            is_new=False,
        )

    def _validate_config(self) -> None:
        if self._external_client:
            return
        missing = [
            name
            for name, value in {
                "ZOOM_ACCOUNT_ID": self.config.zoom_account_id,
                "ZOOM_CLIENT_ID": self.config.zoom_client_id,
                "ZOOM_CLIENT_SECRET": self.config.zoom_client_secret,
            }.items()
            if not value
        ]
        if missing:
            raise ConfigurationError(f"Missing required Zoom OAuth settings: {', '.join(missing)}")


def _looks_like_transcript(file: dict[str, Any]) -> bool:
    file_type = str(file.get("file_type") or "").upper()
    extension = str(file.get("file_extension") or "").upper()
    recording_type = str(file.get("recording_type") or "").lower()
    return (
        file_type in {"TRANSCRIPT", "CC", "VTT"}
        or extension in {"VTT", "JSON"}
        or "transcript" in recording_type
    )


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
