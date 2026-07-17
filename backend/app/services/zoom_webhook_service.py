from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.logging import get_logger
from app.db.repositories import meetings as meeting_repo
from app.db.repositories import runs as run_repo
from app.db.repositories import transcripts as transcript_repo
from app.db.repositories import webhook_events as webhook_events_repo
from app.integrations.zoom.webhook import ZoomWebhookError, body_sha256, sanitize_headers

logger = get_logger(__name__)


class ZoomWebhookService:
    def __init__(
        self,
        db: Session,
        *,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.config = config

    def handle_event(
        self, *, payload: dict[str, Any], headers: dict[str, str], raw_body: bytes
    ) -> dict[str, Any]:
        event_type = payload.get("event")
        if not event_type:
            raise ZoomWebhookError("Zoom webhook payload is missing event")

        request_hash = body_sha256(raw_body)
        zoom_event_id = self._event_identifier(headers, payload)

        existing_event = webhook_events_repo.get_existing_event_for_update(
            self.db, zoom_event_id, request_hash
        )
        if existing_event:
            logger.info(
                "zoom_webhook.duplicate_ignored",
                extra={"event_type": event_type, "event_id": str(existing_event.id)},
            )
            return _duplicate_response(existing_event)

        event = webhook_events_repo.create_event(
            self.db,
            event_type=event_type,
            zoom_event_id=zoom_event_id,
            request_body_sha256=request_hash,
            payload=payload,
            headers=sanitize_headers(headers),
        )

        if event_type != "recording.completed":
            webhook_events_repo.mark_processed(self.db, event, status="ignored")
            logger.info("zoom_webhook.ignored_event", extra={"event_type": event_type})
            return {"status": "ignored", "event": event_type, "event_id": str(event.id)}

        try:
            webhook_events_repo.mark_processing(self.db, event)
            self.db.flush()
            result = self._handle_recording_completed(payload, webhook_event_id=event.id)
            webhook_events_repo.mark_processed(
                self.db, event, meeting_id=result["meeting_id"]
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            event_after = webhook_events_repo.get_by_id(self.db, event.id)
            if event_after is not None:
                webhook_events_repo.mark_failed(self.db, event_after, str(exc))
                self.db.commit()
            raise

        logger.info(
            "zoom_webhook.recording_completed_processed",
            extra={
                "event_id": str(event.id),
                "meeting_id": str(result["meeting_id"]),
                "transcripts_enqueued": result["transcripts_enqueued"],
                "transcripts_skipped": result["transcripts_skipped"],
            },
        )
        return {
            "status": "processed",
            "event": event_type,
            "event_id": str(event.id),
            "meeting_id": str(result["meeting_id"]),
            "transcripts_enqueued": result["transcripts_enqueued"],
            "transcripts_skipped": result["transcripts_skipped"],
        }

    def _handle_recording_completed(
        self, payload: dict[str, Any], *, webhook_event_id: uuid.UUID
    ) -> dict[str, Any]:
        event_payload = payload.get("payload") or {}
        meeting_object = event_payload.get("object") or {}
        if not meeting_object:
            raise ZoomWebhookError("recording.completed payload is missing object")

        meeting = meeting_repo.upsert_zoom_meeting(
            self.db,
            {
                "source": "zoom",
                "zoom_meeting_id": _to_optional_str(meeting_object.get("id")),
                "zoom_uuid": _to_optional_str(meeting_object.get("uuid")),
                "account_id": _to_optional_str(event_payload.get("account_id")),
                "host_id": _to_optional_str(meeting_object.get("host_id")),
                "host_email": _to_optional_str(meeting_object.get("host_email")),
                "topic": meeting_object.get("topic"),
                "start_time": _parse_datetime(meeting_object.get("start_time")),
                "timezone": meeting_object.get("timezone"),
                "duration_minutes": _to_optional_int(meeting_object.get("duration")),
                "participant_count": _to_optional_int(meeting_object.get("participant_count")),
                "metadata_json": meeting_object,
            },
        )
        self.db.flush()

        transcript_files = [
            file
            for file in meeting_object.get("recording_files", []) or []
            if _looks_like_transcript(file)
        ]

        # Per-meeting VTT-before-SRT priority (mirrors
        # TranscriptDiscoveryService): when the recording surfaces BOTH a
        # VTT and an SRT transcript file, only register the VTT one as a
        # first-class transcript (existing behaviour). When ONLY an SRT
        # transcript file is surfaced, register it. This prevents duplicate
        # transcript rows for the same meeting/recording.
        if any(_recording_format(f) == "vtt" for f in transcript_files):
            transcript_files = [f for f in transcript_files if _recording_format(f) != "srt"]

        transcripts_enqueued = 0
        transcripts_skipped = 0
        run_ids: list[str] = []

        for file in transcript_files:
            transcript = transcript_repo.upsert_transcript_metadata(
                self.db,
                {
                    "meeting_id": meeting.id,
                    "source_format": _source_format(file),
                    "status": "metadata_received",
                    "zoom_file_id": _to_optional_str(file.get("id")),
                    "zoom_recording_type": file.get("recording_type"),
                    "file_type": file.get("file_type"),
                    "file_extension": file.get("file_extension"),
                    "file_size_bytes": _to_optional_int(file.get("file_size")),
                    "recording_start": _parse_datetime(file.get("recording_start")),
                    "recording_end": _parse_datetime(file.get("recording_end")),
                    "play_url": file.get("play_url"),
                    "download_url": file.get("download_url"),
                    "language": file.get("language"),
                    "metadata_json": file,
                },
            )
            self.db.flush()

            if transcript.status == "completed":
                logger.info(
                    "zoom_webhook.transcript_already_completed",
                    extra={"transcript_id": str(transcript.id)},
                )
                transcripts_skipped += 1
                continue

            existing_run = self.db.scalar(
                _active_run_for_transcript(transcript.id)
            )
            if existing_run is not None:
                logger.info(
                    "zoom_webhook.transcript_has_active_run",
                    extra={
                        "transcript_id": str(transcript.id),
                        "run_id": str(existing_run.id),
                        "run_status": existing_run.status,
                    },
                )
                transcripts_skipped += 1
                continue

            run = run_repo.create_run(
                self.db,
                transcript_id=transcript.id,
                meeting_id=meeting.id,
                webhook_event_id=webhook_event_id,
                priority=5,
                max_retries=self.config.job_queue_max_retries,
            )
            run_repo.mark_queued(self.db, run)
            self.db.flush()

            transcripts_enqueued += 1
            run_ids.append(str(run.id))
            logger.info(
                "zoom_webhook.transcript_enqueued",
                extra={
                    "transcript_id": str(transcript.id),
                    "run_id": str(run.id),
                    "webhook_event_id": str(webhook_event_id),
                },
            )

        return {
            "meeting_id": meeting.id,
            "transcripts_enqueued": transcripts_enqueued,
            "transcripts_skipped": transcripts_skipped,
            "run_ids": run_ids,
        }

    @staticmethod
    def _event_identifier(headers: dict[str, str], payload: dict[str, Any]) -> str | None:
        for key in ("x-zm-request-id", "x-zm-trackingid", "x-zm-tracking-id"):
            if headers.get(key):
                return headers[key]
        event_ts = payload.get("event_ts")
        event = payload.get("event")
        meeting_uuid = ((payload.get("payload") or {}).get("object") or {}).get("uuid")
        if event and event_ts and meeting_uuid:
            return f"{event}:{meeting_uuid}:{event_ts}"
        return None


def _duplicate_response(event) -> dict[str, Any]:
    return {
        "status": "duplicate",
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_status": event.status,
        "meeting_id": str(event.meeting_id) if event.meeting_id else None,
    }


def _active_run_for_transcript(transcript_id: uuid.UUID):
    from sqlalchemy import select
    from app.db.models.processing_run import ProcessingRun

    active_statuses = {"pending", "queued", "running", "retrying"}
    return (
        select(ProcessingRun.id, ProcessingRun.status)
        .where(
            ProcessingRun.transcript_id == transcript_id,
            ProcessingRun.status.in_(active_statuses),
        )
        .limit(1)
    )


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
    "vtt" / "srt" / "json" / None. Used for the per-meeting
    VTT-before-SRT prioritization in handle_recording_completed (identical
    rule to TranscriptDiscoveryService). Falls back on file_type when the
    file_extension is missing.
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
