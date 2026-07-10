"""Backend-owned citation registry and Sources-section builder for Atlas.

This module makes citations deterministic. The LLM is ONLY allowed to reference
citation IDs that already exist in the registry; it may never invent new ones.
After the LLM finishes, the backend scans the response for the citation markers
that were actually used and builds the trailing ``Sources`` block entirely from
registry metadata. The LLM never owns the Sources block.

Supported source kinds:
  - ``transcript``  : a retrieved transcript / semantic chunk (with optional
                      speaker + start/end timestamps).
  - ``insight``     : a meeting insight (summary, key concepts, action items,
                      decisions, recommendations, key takeaways).
  - ``learning``    : a learning output.

All metadata is optional and omitted gracefully when absent — speakers,
timestamps, etc. are never fabricated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from app.services.atlas_context_service import MeetingContext, RetrievedChunk

# Matches valid citation markers like [1], [2], [12]. We intentionally do not
# match bracketed text that contains spaces (e.g. "[1 ]") to avoid false hits.
_CITATION_RE = re.compile(r"\[(\d{1,3})\]")

# Matches a trailing LLM-generated Sources block so we can strip it and rebuild
# it deterministically from the registry. We are deliberately forgiving: we
# remove any final section that starts with a horizontal rule + "Sources".
_LLM_SOURCES_BLOCK_RE = re.compile(
    r"\s*(?:^|\n)\s*-{3,}\s*\n\s*#*\s*Sources.*?(?:\Z|\n\s*-{3,})",
    re.IGNORECASE,
)
# Also remove a bare trailing "Sources" heading followed by citation lines, in
# case the model produced a block without a leading horizontal rule.
_LLM_SOURCES_HEADING_RE = re.compile(
    r"\s*\n\s*#*\s*Sources\s*\n(?:\s*\[\d+\][^\n]*\n?)+\s*\Z",
    re.IGNORECASE,
)


@dataclass
class CitationSource:
    """A single backend-owned, numbered citation source."""

    citation_id: int
    kind: str  # "transcript" | "insight" | "learning"
    speaker: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    # A short human label for the source, used in the Sources block.
    label: str = ""
    # The text/content the source provides (used when rendering numbered sources
    # into the LLM context).
    text: str = ""


@dataclass
class CitationRegistry:
    """Holds all numbered sources for one Atlas response, in stable order."""

    sources: list[CitationSource] = field(default_factory=list)
    _index: dict[int, CitationSource] = field(default_factory=dict)

    def add(
        self,
        kind: str,
        *,
        text: str = "",
        speaker: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        label: str = "",
    ) -> CitationSource:
        """Register a new source and return it with its stable citation id."""
        citation_id = len(self.sources) + 1
        src = CitationSource(
            citation_id=citation_id,
            kind=kind,
            speaker=speaker,
            start_time=start_time,
            end_time=end_time,
            label=label or kind,
            text=text,
        )
        self.sources.append(src)
        self._index[citation_id] = src
        return src

    def get(self, citation_id: int) -> CitationSource | None:
        return self._index.get(citation_id)

    @property
    def valid_ids(self) -> set[int]:
        return set(self._index.keys())

    def __len__(self) -> int:
        return len(self.sources)


def build_citation_registry(context: MeetingContext) -> CitationRegistry:
    """Build a stable citation registry from a MeetingContext.

    Ordering (citation IDs are assigned in this order):
      1. Retrieved transcript / semantic chunks  -> kind "transcript"
      2. Meeting insights fields                 -> kind "insight"
      3. Learning outputs summary                 -> kind "learning"

    A kind is only registered when the underlying content exists. Speakers and
    timestamps are included only when present on the retrieved chunk; otherwise
    they are omitted (never fabricated).
    """
    registry = CitationRegistry()

    # 1) Transcript / semantic chunks
    for chunk in context.retrieved_chunks:
        speaker = getattr(chunk, "speaker", None)
        start_time = getattr(chunk, "start_time", None)
        end_time = getattr(chunk, "end_time", None)
        registry.add(
            "transcript",
            text=chunk.chunk_text,
            speaker=speaker,
            start_time=start_time,
            end_time=end_time,
            label="Transcript",
        )

    # 2) Meeting insights — each non-empty insight field becomes one source so
    # that the model can cite insights individually when supporting a statement.
    if context.transcript_summary:
        registry.add("insight", text=context.transcript_summary, label="Meeting Insight")
    if context.key_concepts:
        registry.add(
            "insight",
            text=", ".join(context.key_concepts[:5]),
            label="Meeting Insight",
        )
    if context.action_items:
        items = ", ".join([a.get("item_text", "") for a in context.action_items[:3] if a.get("item_text")])
        if items:
            registry.add("insight", text=items, label="Meeting Insight")
    if context.key_takeaways:
        registry.add(
            "insight",
            text=", ".join(context.key_takeaways[:3]),
            label="Meeting Insight",
        )
    if context.decisions:
        decisions = ", ".join([d.get("decision", "") for d in context.decisions[:3] if d.get("decision")])
        if decisions:
            registry.add("insight", text=decisions, label="Meeting Insight")
    if context.recommendations:
        recs = ", ".join([r.get("text", "") for r in context.recommendations[:3] if r.get("text")])
        if recs:
            registry.add("insight", text=recs, label="Meeting Insight")

    # 3) Learning outputs
    if context.learning_outputs_summary:
        registry.add("learning", text=context.learning_outputs_summary, label="Learning Output")

    return registry


def render_numbered_sources(registry: CitationRegistry) -> str:
    """Render the registry as a numbered sources block for the LLM prompt.

    The LLM is instructed to reference these exact IDs inline and to NEVER
    invent its own. The backend owns the final Sources block, so the model is
    told NOT to write one itself.
    """
    if not registry.sources:
        return ""
    lines = ["Sources you may cite (use ONLY these IDs)[citation-id]:"]
    for src in registry.sources:
        speaker_info = f" speaker={src.speaker}" if src.speaker else ""
        time_info = ""
        if src.start_time and src.end_time:
            time_info = f" {src.start_time}-{src.end_time}"
        elif src.start_time:
            time_info = f" {src.start_time}"
        kind_note = (
            "Transcript" if src.kind == "transcript"
            else "Meeting Insight" if src.kind == "insight"
            else "Learning Output"
        )
        snippet = src.text.strip().replace("\n", " ")
        if len(snippet) > 280:
            snippet = snippet[:280].rstrip() + "…"
        lines.append(
            f"[{src.citation_id}] {kind_note}{speaker_info}{time_info}: {snippet}"
        )
    return "\n".join(lines)


def format_context_with_citations(context: MeetingContext) -> tuple[str, CitationRegistry]:
    """Format a MeetingContext into (prompt_context_str, citation_registry).

    This keeps the previous context layout but replaces ad-hoc "cite as ..."
    hints with a single, backend-owned numbered sources block at the end. The
    rest of the context (meeting header, insights, learning outputs) keeps its
    natural wording; the LLM cites by the stable IDs in the sources block.
    """
    if not context.has_context:
        return "", CitationRegistry()

    registry = build_citation_registry(context)

    parts: list[str] = []

    # Header
    parts.append(f"Meeting: {context.meeting_topic or 'Untitled Meeting'}")
    if context.meeting_date:
        parts.append(f"Date: {context.meeting_date}")

    # Retrieved transcript segments (verbatim, unnumbered — the IDs live in the
    # numbered sources block below this; their order matches the registry).
    if context.retrieved_chunks:
        parts.append("\nRelevant Meeting Segments:")
        for i, chunk in enumerate(context.retrieved_chunks, 1):
            speaker = f" [{chunk.speaker}]" if getattr(chunk, "speaker", None) else ""
            time_info = ""
            if getattr(chunk, "start_time", None) and getattr(chunk, "end_time", None):
                time_info = f" {chunk.start_time}-{chunk.end_time}"
            parts.append(f"[{i}]{speaker}{time_info} {chunk.chunk_text}")

    # Meeting insights (kept readable; the matching insight citations exist in
    # the numbered sources block).
    if context.transcript_summary:
        parts.append(f"Summary: {context.transcript_summary}")
    if context.key_concepts:
        parts.append("Key Concepts: " + ", ".join(context.key_concepts[:5]))
    if context.action_items:
        items = ", ".join([a.get("item_text", "") for a in context.action_items[:3] if a.get("item_text")])
        if items:
            parts.append(f"Action Items: {items}")
    if context.key_takeaways:
        parts.append("Key Takeaways: " + ", ".join(context.key_takeaways[:3]))
    if context.decisions:
        decisions = ", ".join([d.get("decision", "") for d in context.decisions[:3] if d.get("decision")])
        if decisions:
            parts.append(f"Decisions: {decisions}")
    if context.recommendations:
        recs = ", ".join([r.get("text", "") for r in context.recommendations[:3] if r.get("text")])
        if recs:
            parts.append(f"Recommendations: {recs}")
    if context.learning_outputs_summary:
        parts.append(f"Learning Outputs: {context.learning_outputs_summary}")

    # Backend-owned numbered sources block — the only place citation IDs are
    # declared. The LLM must reference these IDs verbatim and never invent new
    # ones or write its own Sources section.
    sources_block = render_numbered_sources(registry)
    if sources_block:
        parts.append("\n" + sources_block)

    return "\n\n".join(parts), registry


def extract_used_citations(text: str, registry: CitationRegistry) -> list[int]:
    """Return the sorted, de-duplicated list of valid citation IDs actually used
    in ``text``. Invalid IDs (not in the registry) are dropped — they are
    treated as model hallucinations and ignored, never rendered.
    """
    if not registry or not text:
        return []
    valid = registry.valid_ids
    used: set[int] = set()
    for m in _CITATION_RE.finditer(text):
        try:
            cid = int(m.group(1))
        except ValueError:
            continue
        if cid in valid:
            used.add(cid)
    return sorted(used)


def _strip_llm_sources_block(text: str) -> str:
    """Remove any Sources block the LLM may have appended, so the backend can
    append its own deterministic one."""
    if not text:
        return text
    stripped = _LLM_SOURCES_BLOCK_RE.sub("", text)
    stripped = _LLM_SOURCES_HEADING_RE.sub("", stripped)
    return stripped.rstrip()


def _format_source_line(src: CitationSource) -> str:
    """Format a single source line for the backend-owned Sources block.

    Speaker-aware, timestamp-aware, graceful when metadata is missing.
    """
    if src.kind == "transcript":
        label = "Transcript"
        line = f"[{src.citation_id}] {label}"
        if src.speaker:
            line += f" • Speaker: {src.speaker}"
        if src.start_time and src.end_time:
            line += f" • {src.start_time}-{src.end_time}"
        elif src.start_time:
            line += f" • {src.start_time}"
        return line
    if src.kind == "insight":
        return f"[{src.citation_id}] Meeting Insight"
    if src.kind == "learning":
        return f"[{src.citation_id}] Learning Output"
    return f"[{src.citation_id}] {src.label or 'Source'}"


def append_sources_block(text: str, registry: CitationRegistry | None) -> str:
    """Finalize an Atlas response.

    - Strips any Sources block the LLM may have written.
    - Detects which registered citation IDs were actually used inline.
    - Appends a backend-built ``Sources`` block containing ONLY the used IDs,
      in numeric order, with speaker/timestamp metadata when available.

    If ``registry`` is None/empty or no citations are used, no Sources block is
    appended (graceful omission — never an empty Sources section).
    """
    if not text:
        return text
    cleaned = _strip_llm_sources_block(text)
    if not registry or len(registry) == 0:
        return cleaned
    used = extract_used_citations(cleaned, registry)
    if not used:
        return cleaned
    lines = ["", "---", "", "Sources", ""]
    for cid in used:
        src = registry.get(cid)
        if src is None:
            continue
        lines.append(_format_source_line(src))
    return cleaned + "\n" + "\n".join(lines) + "\n"


def finalize_response(text: str, registry: CitationRegistry | None) -> str:
    """Public entry point used by all assistant response paths (direct, LLM,
    and streamed). Equivalent to ``append_sources_block`` today; kept as a
    named seam so future post-processing stays centralized here."""
    return append_sources_block(text, registry)
