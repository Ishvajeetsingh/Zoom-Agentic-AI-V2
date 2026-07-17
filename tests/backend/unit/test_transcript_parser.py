from pathlib import Path

import pytest

from app.services.transcript_parser import (
    ParsedTranscriptSegment,
    SrtParser,
    SrtParsingError,
    VttParser,
    VttParsingError,
    ZoomChatParser,
    ZoomChatParsingError,
    detect_zoom_chat_format,
)


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


class TestZoomChatParser:
    def test_parse_zoom_chat_extracts_segments(self) -> None:
        segments = ZoomChatParser().parse_file(FIXTURES_DIR / "sample_zoom_chat.txt")

        assert len(segments) == 8

        assert segments[0].sequence_number == 1
        assert segments[0].start_time == 5.0
        assert segments[0].end_time == 6.0
        assert segments[0].speaker == "Alice"
        assert segments[0].text == "Hi everyone, welcome to the standup."

        assert segments[1].speaker == "Bob"
        assert segments[1].text == "Thanks Alice, I have a quick update on the backend."
        assert segments[1].start_time == 12.0

        assert segments[3].speaker == "Carol"
        assert segments[3].text == "Great, I'll start QA testing this afternoon."

        assert segments[5].speaker == "David"
        assert segments[5].start_time == 62.0

    def test_parse_zoom_chat_multiline_timestamp(self) -> None:
        content = "00:27:08 User Name: Hello world\n00:27:18 Jane Doe: Second message\n"
        segments = ZoomChatParser().parse(content)

        assert len(segments) == 2
        assert segments[0].start_time == 1628.0
        assert segments[0].speaker == "User Name"
        assert segments[0].text == "Hello world"
        assert segments[1].start_time == 1638.0
        assert segments[1].speaker == "Jane Doe"

    def test_parse_zoom_chat_raises_when_no_valid_lines(self) -> None:
        with pytest.raises(ZoomChatParsingError):
            ZoomChatParser().parse_file(FIXTURES_DIR / "malformed_zoom_chat.txt")

    def test_parse_zoom_chat_raises_on_empty_content(self) -> None:
        with pytest.raises(ZoomChatParsingError):
            ZoomChatParser().parse("")

    def test_parse_zoom_chat_skips_empty_messages(self) -> None:
        content = "00:01:00 Alice:\n00:01:30 Bob: Actual message\n"
        segments = ZoomChatParser().parse(content)

        assert len(segments) == 1
        assert segments[0].speaker == "Bob"
        assert segments[0].text == "Actual message"

    def test_parse_zoom_chat_handles_various_timestamps(self) -> None:
        content = "00:00:00 Alice: Start\n01:30:45 Bob: Deep in meeting\n"
        segments = ZoomChatParser().parse(content)

        assert segments[0].start_time == 0.0
        assert segments[1].start_time == 5445.0


class TestDetectZoomChatFormat:
    def test_detects_zoom_chat_format(self) -> None:
        content = "00:00:05 Alice: Hello\n00:00:10 Bob: Hi there\n"
        assert detect_zoom_chat_format(content) is True

    def test_rejects_vtt_format(self) -> None:
        content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nAlice: Hello\n"
        assert detect_zoom_chat_format(content) is False

    def test_rejects_empty_content(self) -> None:
        assert detect_zoom_chat_format("") is False

    def test_rejects_random_text(self) -> None:
        content = "Just some random lines\nwithout any timestamps\nor chat format\n"
        assert detect_zoom_chat_format(content) is False

    def test_detects_mixed_with_some_non_matching_lines(self) -> None:
        content = "00:00:05 Alice: Hello\nSome metadata line\n00:00:10 Bob: Hi\n"
        assert detect_zoom_chat_format(content) is True


class TestVttParserStillWorks:
    def test_parse_vtt_extracts_segments(self) -> None:
        segments = VttParser().parse_file(FIXTURES_DIR / "sample_transcript.vtt")
        assert len(segments) == 4
        assert segments[0].speaker == "Alice"
        assert segments[0].text == "Welcome to the weekly sync."

    def test_parse_vtt_raises_when_no_valid_cues(self) -> None:
        with pytest.raises(VttParsingError):
            VttParser().parse_file(FIXTURES_DIR / "malformed_transcript.vtt")


class TestSrtParser:
    """SRT first-class support regression tests.

    SRT and VTT share the same ``ParsedTranscriptSegment`` shape and the
    same shared cue-extraction logic in ``_parse_cue_blocks``. These tests
    lock in:
      - cue numbering (sequence_number increments after filtering)
      - timestamp parsing (comma fractional separator)
      - speaker extraction ("Speaker: text")
      - missing-speaker cues (speaker == None)
      - multi-line dialogue
      - unicode
      - duplicate-cue suppression
      - invalid-cue skipping (no timestamp, malformed timestamp, invalid range)
      - same ParsedTranscriptSegment dataclass shape as VTT
    """

    def test_parse_srt_extracts_segments_speakers_and_timestamps(self) -> None:
        segments = SrtParser().parse_file(FIXTURES_DIR / "sample_transcript.srt")

        # 6 valid cues expected:
        # 1 (Alice), 2 (Bob), 3 (no speaker), 4 (duplicate of 3 - skipped),
        # 5 (invalid range - skipped), 6 (Carol), 7 (multiline), 8 (unicode)
        # Survivors: 1, 2, 3, 6, 7, 8 = 6 segments.
        assert len(segments) == 6

        # Cue 1: speaker, comma-separated fractional seconds, sequence resets
        assert segments[0].sequence_number == 1
        assert segments[0].start_time == 1.1
        assert segments[0].end_time == 4.0
        assert segments[0].speaker == "Alice"
        assert segments[0].text == "Welcome to the weekly sync."

        # Cue 2: Bob, normal timestamp parsing
        assert segments[1].sequence_number == 2
        assert segments[1].speaker == "Bob"
        assert segments[1].text == "We completed the API integration yesterday."
        assert segments[1].start_time == 5.5
        assert segments[1].end_time == 8.25

        # Cue 3: no speaker label -> None
        assert segments[2].speaker is None
        assert segments[2].text == "The release candidate is ready for testing."

        # Cue 4 (the literal "4" block which duplicates cue #3) is
        # skipped as a duplicate (same start, end, text), so Carol becomes #4.
        assert segments[3].sequence_number == 4
        assert segments[3].speaker == "Carol"
        assert segments[3].text == "Please share the QA checklist after this call."

        # Multi-line cue: lines joined with single space, speaker None
        assert segments[4].sequence_number == 5
        assert segments[4].speaker is None
        assert segments[4].text == "A multi-line cue with a second line of the same caption."

        # Unicode preserved verbatim through the clean+strip pipeline.
        assert segments[5].sequence_number == 6
        assert segments[5].speaker is None
        assert segments[5].text == "Fuente de café naïve façade år."

    def test_parse_srt_skips_blocks_without_timestamps(self) -> None:
        segments = SrtParser().parse_file(FIXTURES_DIR / "sample_transcript.srt")
        assert all("bad cue" not in s.text for s in segments)
        assert all("This block should be ignored." not in s.text for s in segments)

    def test_parse_srt_rejects_invalid_time_range(self) -> None:
        segments = SrtParser().parse_file(FIXTURES_DIR / "sample_transcript.srt")
        assert all("This invalid range should be ignored." not in s.text for s in segments)

    def test_parse_srt_deduplicates_identical_cues(self) -> None:
        segments = SrtParser().parse_file(FIXTURES_DIR / "sample_transcript.srt")
        repeats = [s for s in segments if s.text == "The release candidate is ready for testing."]
        assert len(repeats) == 1

    def test_parse_srt_raises_when_no_valid_cues(self) -> None:
        with pytest.raises(SrtParsingError):
            SrtParser().parse_file(FIXTURES_DIR / "malformed_transcript.srt")

    def test_parse_srt_raises_on_empty_content(self) -> None:
        with pytest.raises(SrtParsingError):
            SrtParser().parse("")

    def test_parse_srt_in_memory(self) -> None:
        content = (
            "1\n00:00:01,000 --> 00:00:02,000\nAlice: Hello world.\n\n"
            "2\n00:00:02,500 --> 00:00:03,500\nBob: Goodbye.\n"
        )
        segments = SrtParser().parse(content)
        assert len(segments) == 2
        assert segments[0].speaker == "Alice"
        assert segments[0].start_time == 1.0
        assert segments[0].end_time == 2.0
        assert segments[1].speaker == "Bob"

    def test_parse_srt_accepts_missing_optional_cue_index(self) -> None:
        # SRT cue-index lines are optional from the parser's perspective (it
        # locates the timestamp line anywhere in the block). Verify a file
        # that omits the leading index still parses.
        content = (
            "00:00:01,000 --> 00:00:02,000\nAlice: Hello.\n\n"
            "00:00:02,500 --> 00:00:03,500\nBob: Goodbye.\n"
        )
        segments = SrtParser().parse(content)
        assert len(segments) == 2
        assert segments[0].speaker == "Alice"
        assert segments[1].speaker == "Bob"

    def test_srt_emits_identical_segment_shape_as_vtt(self) -> None:
        # The SRT parser and the VTT parser MUST emit the same dataclass
        # type with the same fields so every downstream stage (cleaning,
        # chunking, embeddings, ...) treats them identically — guaranteeing
        # there is no separate SRT pipeline.
        srt_segments = SrtParser().parse_file(FIXTURES_DIR / "sample_transcript.srt")
        vtt_segments = VttParser().parse_file(FIXTURES_DIR / "sample_transcript.vtt")

        assert all(isinstance(s, ParsedTranscriptSegment) for s in srt_segments)
        assert all(isinstance(s, ParsedTranscriptSegment) for s in vtt_segments)

        assert ParsedTranscriptSegment.__dataclass_fields__.keys() == {
            "start_time", "end_time", "speaker", "text", "sequence_number",
        }
        # The same as_dict() feeds the transcript_segments table for both
        # formats — so SRT and VTT persist identical dict shapes.
        srt_dict = srt_segments[0].as_dict()
        vtt_dict = vtt_segments[0].as_dict()
        assert srt_dict.keys() == vtt_dict.keys() == {
            "start_time", "end_time", "speaker", "text", "sequence_number",
        }


class TestSharedCueExtractionPipeline:
    """The SRT and VTT parsers MUST share ONE cue-extraction implementation
    (``_parse_cue_blocks``), never two parallel pipelines. Lock that in.
    """

    def test_vtt_and_srt_parsers_share_same_cue_extractor(self) -> None:
        from app.services import transcript_parser

        assert callable(transcript_parser._parse_cue_blocks)

        # The VTT and SRT parser classes both call into it (rather than
        # re-implementing the cue loop). This sanity check ensures no future
        # refactor re-introduces duplicated logic.
        import inspect

        vtt_src = inspect.getsource(VttParser)
        srt_src = inspect.getsource(SrtParser)
        assert "_parse_cue_blocks" in vtt_src
        assert "_parse_cue_blocks" in srt_src
        # The cue-loop bookkeeping (duplicate detection, time-range check)
        # must NOT appear inside either parser class body — it lives only
        # in the shared helper.
        assert "seen_cues" not in vtt_src
        assert "seen_cues" not in srt_src

    def test_vtt_parser_tolerates_comma_timestamp_separator_too(self) -> None:
        # Although the production codepath dispatches SRT files to
        # SrtParser, TIMESTAMP_PATTERN accepts BOTH `.` and `,` so the VTT
        # parser is structurally capable of parsing SRT-formatted content
        # too — this confirms the timestamp regex generalization was the
        # only parser-level delta needed.
        srt_content = "1\n00:00:01,000 --> 00:00:02,000\nAlice: Hello.\n"
        assert len(VttParser().parse(srt_content)) == 1
