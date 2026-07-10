"""Meeting Context Service for Atlas with Semantic Retrieval."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.conversation import Conversation
from app.db.models.meeting import Meeting
from app.db.models.meeting_insights import MeetingInsights
from app.db.models.transcript import Transcript
from app.db.repositories import meeting_insights as meeting_insights_repo
from app.services.embedding_service import EmbeddingService, ChunkEmbeddingStore
from app.services.semantic_retrieval_service import RetrievedChunk, SemanticRetrievalService, cosine_similarity

logger = get_logger(__name__)

# Approximate tokens per character for rough token estimation
# Average English: ~4 chars per token; using a conservative 3.5 for safety with code/special chars
TOKENS_PER_CHAR = 1 / 3.5
MAX_CONTEXT_TOKENS = 3000  # Keep well within typical model limits; leaves room for prompt + response


@dataclass
class MeetingContext:
    meeting_id: uuid.UUID | None = None
    meeting_topic: str | None = None
    meeting_date: str | None = None
    transcript_summary: str = ""
    key_concepts: list[str] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)
    key_takeaways: list[str] = field(default_factory=list)
    learning_outputs_summary: str = ""
    decisions: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    has_context: bool = False


def build_meeting_context(
    db: Session,
    conversation: Conversation,
    *,
    use_semantic_search: bool = True,
    user_query: str | None = None,
) -> MeetingContext:
    """Build a compact MeetingContext from a conversation's meeting."""
    if conversation is None or conversation.meeting_id is None:
        return MeetingContext(has_context=False)

    meeting: Meeting | None = db.get(Meeting, conversation.meeting_id)
    if meeting is None:
        return MeetingContext(has_context=False)

    # Find the meeting's transcripts and use the first one for insights lookup
    from sqlalchemy import select as sa_select
    from app.db.models.transcript import Transcript
    first_transcript = db.scalar(
        sa_select(Transcript).where(Transcript.meeting_id == meeting.id).order_by(Transcript.created_at.asc())
    )

    # Load insights via the meeting's transcript
    insights: MeetingInsights | None = None
    if first_transcript:
        insights = meeting_insights_repo.get_by_transcript_id(db, first_transcript.id)

    context = MeetingContext(
        meeting_id=meeting.id,
        meeting_topic=meeting.topic or "Untitled Meeting",
        meeting_date=str(meeting.start_time) if meeting.start_time else None,
        transcript_summary=insights.summary_text if insights else "",
        key_concepts=[c.get("concept", "") for c in (insights.key_concepts or [])] if insights else [],
        action_items=insights.action_items or [] if insights else [],
        key_takeaways=[t.get("takeaway", "") for t in (insights.key_takeaways or [])] if insights else [],
        learning_outputs_summary=f"{0} learning outputs generated",  # placeholder, filled below
        decisions=insights.decisions or [] if insights else [],
        recommendations=insights.recommendations or [] if insights else [],
        has_context=True,
    )

    # Semantic retrieval
    if use_semantic_search and user_query and first_transcript:
        try:
            embed_svc = EmbeddingService(config=settings)
            store = ChunkEmbeddingStore(db)

            # Get all embeddings for this meeting
            meeting_embeddings = store.get_for_meeting(meeting.id, embed_svc.model)
            if meeting_embeddings:
                query_embedding = embed_svc.embed(user_query)
                retrieval = SemanticRetrievalService(top_k=settings.atlas_max_retrieved_chunks)
                relevant = retrieval.search(query_embedding, candidates=meeting_embeddings)
                # Deduplicate chunks by chunk_text (keep highest similarity first)
                seen: set[str] = set()
                unique_relevant = []
                for r in relevant:
                    if r.chunk_text not in seen:
                        seen.add(r.chunk_text)
                        unique_relevant.append(r)
                relevant = unique_relevant

                # Map raw results to RetrievedChunk objects (metadata not yet populated)
                similarities = [cosine_similarity(query_embedding, r.embedding) for r in relevant]
                context.retrieved_chunks = [
                    RetrievedChunk(
                        chunk_text=r.chunk_text,
                        similarity=sim,
                    )
                    for r, sim in zip(relevant, similarities)
                ]
        except Exception:
            logger.exception("semantic.retrieval.failed", extra={"meeting_id": str(meeting.id)})

    return context


def _estimate_tokens(text: str) -> int:
    """Roughly estimate token count from character count."""
    return int(len(text) * TOKENS_PER_CHAR)


def format_context_for_prompt(context: MeetingContext) -> str:
    """Format MeetingContext into a compact string for the LLM prompt.

    Kept as a thin facade over the backend-owned citation service so existing
    callers (e.g. educational intelligence) continue to work. Prompt-building
    paths that need deterministic citations should call
    ``format_context_with_citations`` instead to also receive the
    ``CitationRegistry``.
    """
    from app.services.atlas_citation_service import format_context_with_citations

    context_str, _registry = format_context_with_citations(context)
    return context_str
