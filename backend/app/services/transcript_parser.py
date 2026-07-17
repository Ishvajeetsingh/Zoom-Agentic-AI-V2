import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import AppError

logger = logging.getLogger(__name__)

TIMESTAMP_SEPARATOR = "-->"
TIMESTAMP_PATTERN = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})"
)
SPEAKER_PATTERN = re.compile(r"^(?P<speaker>[A-Za-z][A-Za-z0-9 ._'()-]{0,80}):\s*(?P<text>.+)$")
VOICE_TAG_PATTERN = re.compile(r"^<v(?:\.[^ >]+)?\s+(?P<speaker>[^>]+)>(?P<text>.*?)(?:</v>)?$")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
ZOOM_CHAT_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{1,2}:\d{2}:\d{2})\s+"
    r"(?P<speaker>[^:]+):\s*"
    r"(?P<text>.+)$"
)


class VttParsingError(AppError):
    """Raised when a VTT file cannot be parsed into any usable segments."""


class SrtParsingError(AppError):
    """Raised when an SRT file cannot be parsed into any usable segments."""


@dataclass(frozen=True)
class ParsedTranscriptSegment:
    start_time: float
    end_time: float
    speaker: str | None
    text: str
    sequence_number: int

    def as_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "speaker": self.speaker,
            "text": self.text,
            "sequence_number": self.sequence_number,
        }


class VttParser:
    def parse_file(self, path: str | Path) -> list[ParsedTranscriptSegment]:
        file_path = Path(path)
        if not file_path.exists():
            raise VttParsingError(f"VTT file does not exist: {file_path}")
        content = file_path.read_text(encoding="utf-8-sig", errors="replace")
        return self.parse(content, source=str(file_path))

    def parse(self, content: str, *, source: str = "<memory>") -> list[ParsedTranscriptSegment]:
        if not content.strip():
            raise VttParsingError("VTT content is empty")
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n\s*\n", normalized_content)
        return _parse_cue_blocks(
            blocks,
            source=source,
            error_cls=VttParsingError,
            logger_component="vtt_parser",
        )


class SrtParser:
    """Parser for SubRip (.srt) transcripts.

    SRT is structurally a near-twin of WebVTT: blocks are separated by blank
    lines, each block carries an optional cue index, a `00:00:01,100 -->
    00:00:05,000` timestamp line (note the COMMA fractional separator),
    then one or more text lines. The only parser-level difference from VTT
    is the fractional-seconds separator, which TIMESTAMP_PATTERN already
    tolerates (it accepts both `.` and `,`). We therefore reuse the
    VTT block-parsing logic verbatim through `_parse_cue_blocks`, so there
    is exactly ONE cue-extraction pipeline for VTT and SRT — no duplicated
    parsing logic.
    """

    def parse_file(self, path: str | Path) -> list[ParsedTranscriptSegment]:
        file_path = Path(path)
        if not file_path.exists():
            raise SrtParsingError(f"SRT file does not exist: {file_path}")
        content = file_path.read_text(encoding="utf-8-sig", errors="replace")
        return self.parse(content, source=str(file_path))

    def parse(self, content: str, *, source: str = "<memory>") -> list[ParsedTranscriptSegment]:
        if not content.strip():
            raise SrtParsingError("SRT content is empty")
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n\s*\n", normalized_content)
        return _parse_cue_blocks(
            blocks,
            source=source,
            error_cls=SrtParsingError,
            logger_component="srt_parser",
        )


def _parse_cue_blocks(
    blocks: list[str],
    *,
    source: str,
    error_cls: type[AppError],
    logger_component: str,
) -> list[ParsedTranscriptSegment]:
    """Shared cue extraction for VTT and SRT.

    Both formats share block separation (one or more blank lines), header
    skipping (WEBVTT / NOTE / STYLE), cue-index tolerance (lines before the
    timestamp line are ignored), the `-->` timestamp separator, the speaker
    label `Speaker: text` convention, voice-tag stripping, duplicate-cue
    suppression, and invalid-time-range rejection. The only
    format-specific detail — the fractional-seconds separator — is already
    handled by TIMESTAMP_PATTERN, which accepts both `.` (VTT) and `,` (SRT).
    """
    segments: list[ParsedTranscriptSegment] = []
    seen_cues: set[tuple[float, float, str]] = set()

    for block_index, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if _is_header_or_note(lines):
            continue

        timestamp_index = _find_timestamp_line(lines)
        if timestamp_index is None:
            logger.warning(
                f"{logger_component}.missing_timestamp",
                extra={"source": source, "block_index": block_index},
            )
            continue

        timestamps = _parse_timestamp_line(lines[timestamp_index])
        if timestamps is None:
            logger.warning(
                f"{logger_component}.malformed_timestamp",
                extra={"source": source, "block_index": block_index, "line": lines[timestamp_index]},
            )
            continue

        text_lines = lines[timestamp_index + 1 :]
        if not text_lines:
            logger.warning(
                f"{logger_component}.empty_cue",
                extra={"source": source, "block_index": block_index},
            )
            continue

        speaker, text = _extract_speaker_and_text(text_lines)
        if not text:
            logger.warning(
                f"{logger_component}.empty_text_after_cleanup",
                extra={"source": source, "block_index": block_index},
            )
            continue

        start_time, end_time = timestamps
        if end_time < start_time:
            logger.warning(
                f"{logger_component}.invalid_time_range",
                extra={"source": source, "block_index": block_index},
            )
            continue

        cue_key = (start_time, end_time, text)
        if cue_key in seen_cues:
            logger.info(
                f"{logger_component}.duplicate_cue_skipped",
                extra={"source": source, "block_index": block_index},
            )
            continue
        seen_cues.add(cue_key)

        segments.append(
            ParsedTranscriptSegment(
                start_time=start_time,
                end_time=end_time,
                speaker=speaker,
                text=text,
                sequence_number=len(segments) + 1,
            )
        )

    if not segments:
        raise error_cls(f"No valid transcript cues found in {source}")

    logger.info(
        f"{logger_component}.completed",
        extra={"source": source, "segment_count": len(segments)},
    )
    return segments


def _is_header_or_note(lines: list[str]) -> bool:
    first = lines[0].upper()
    return first.startswith("WEBVTT") or first.startswith("NOTE") or first.startswith("STYLE")


def _find_timestamp_line(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if TIMESTAMP_SEPARATOR in line:
            return index
    return None


def _parse_timestamp_line(line: str) -> tuple[float, float] | None:
    match = TIMESTAMP_PATTERN.search(line)
    if not match:
        return None
    return _timestamp_to_seconds(match.group("start")), _timestamp_to_seconds(match.group("end"))


def _timestamp_to_seconds(value: str) -> float:
    # Both VTT (`.`) and SRT (`,`) fractional-seconds separators are valid.
    # Normalize the SubRip comma to a dot before parsing so float() copes.
    normalized = value.replace(",", ".")
    parts = normalized.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    else:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    return round(hours * 3600 + minutes * 60 + seconds, 3)


def _extract_speaker_and_text(lines: list[str]) -> tuple[str | None, str]:
    cleaned_lines: list[str] = []
    speaker: str | None = None

    for line in lines:
        line_speaker, line_text = _extract_speaker_from_line(line)
        if speaker is None and line_speaker:
            speaker = line_speaker
        cleaned_lines.append(line_text)

    text = " ".join(part for part in cleaned_lines if part).strip()
    text = re.sub(r"\s+", " ", text)
    return speaker, text


def _extract_speaker_from_line(line: str) -> tuple[str | None, str]:
    voice_match = VOICE_TAG_PATTERN.match(line)
    if voice_match:
        return _clean_speaker(voice_match.group("speaker")), _clean_text(voice_match.group("text"))

    clean_line = _clean_text(line)
    speaker_match = SPEAKER_PATTERN.match(clean_line)
    if speaker_match:
        return _clean_speaker(speaker_match.group("speaker")), speaker_match.group("text").strip()

    return None, clean_line


def _clean_text(value: str) -> str:
    return HTML_TAG_PATTERN.sub("", value).strip()


def _clean_speaker(value: str) -> str:
    return _clean_text(value).strip()


class ZoomChatParsingError(AppError):
    """Raised when a Zoom chat export file cannot be parsed into any usable segments."""


def detect_zoom_chat_format(content: str) -> bool:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        return False
    matches = sum(1 for line in lines if ZOOM_CHAT_LINE_PATTERN.match(line))
    return matches > 0 and matches / len(lines) >= 0.5


class ZoomChatParser:
    def parse_file(self, path: str | Path) -> list[ParsedTranscriptSegment]:
        file_path = Path(path)
        if not file_path.exists():
            raise ZoomChatParsingError(f"Zoom chat file does not exist: {file_path}")
        content = file_path.read_text(encoding="utf-8-sig", errors="replace")
        return self.parse(content, source=str(file_path))

    def parse(self, content: str, *, source: str = "<memory>") -> list[ParsedTranscriptSegment]:
        if not content.strip():
            raise ZoomChatParsingError("Zoom chat content is empty")

        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.split("\n")
        segments: list[ParsedTranscriptSegment] = []

        for line_num, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            match = ZOOM_CHAT_LINE_PATTERN.match(line)
            if not match:
                logger.warning(
                    "zoom_chat_parser.unmatched_line",
                    extra={"source": source, "line_num": line_num, "line": line},
                )
                continue

            timestamp_str = match.group("timestamp")
            speaker = match.group("speaker").strip()
            text = match.group("text").strip()

            if not text:
                logger.warning(
                    "zoom_chat_parser.empty_message",
                    extra={"source": source, "line_num": line_num},
                )
                continue

            start_seconds = _chat_timestamp_to_seconds(timestamp_str)
            if start_seconds is None:
                logger.warning(
                    "zoom_chat_parser.invalid_timestamp",
                    extra={"source": source, "line_num": line_num, "timestamp": timestamp_str},
                )
                continue

            end_seconds = start_seconds + 1.0

            segments.append(
                ParsedTranscriptSegment(
                    start_time=start_seconds,
                    end_time=end_seconds,
                    speaker=speaker,
                    text=text,
                    sequence_number=len(segments) + 1,
                )
            )

        if not segments:
            raise ZoomChatParsingError(f"No valid Zoom chat lines found in {source}")

        logger.info(
            "zoom_chat_parser.completed",
            extra={"source": source, "segment_count": len(segments)},
        )
        return segments


def _chat_timestamp_to_seconds(value: str) -> float | None:
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return None
    if minutes > 59 or seconds > 59:
        return None
    return round(hours * 3600 + minutes * 60 + seconds, 3)
