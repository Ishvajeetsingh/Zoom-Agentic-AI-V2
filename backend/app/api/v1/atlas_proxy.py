"""Atlas-facing REST proxy (Phase 2 of the standalone-Atlas migration).

These endpoints exist ONLY to expose pre-existing, Zoom-pipeline-owned
services over HTTP so that a future standalone Atlas can consume them
remotely instead of calling the services in-process. The integrated
Atlas inside Zoom Agentic AI continues to call the services in-process;
nothing in this module changes that path.

Each endpoint is a thin wrapper:
  * ``retrieval/search``           -> EmbeddingService + ChunkEmbeddingStore +
                                     SemanticRetrievalService (mirrors
                                     ``atlas_context_service.build_meeting_context``'s
                                     retrieval block exactly, including the
                                     chunk_text deduplication).
  * ``meetings/{id}/ranked-questions``
                                   -> ProfessorRankingService.rank_questions
                                     across all of a meeting's transcripts,
                                     joined with the full Question content,
                                     in rank order (mirrors
                                     ``atlas_educational_intelligence.build_quiz_response``'s
                                     per-transcript iteration + score-merge).
  * ``transcripts/{id}/ranked-questions``
                                   -> ProfessorRankingService.rank_questions
                                     for a single transcript, joined with the
                                     full Question content, in rank order.

No business logic is duplicated. No existing endpoint is modified.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.question import Question
from app.db.models.transcript import Transcript
from app.services.embedding_service import EmbeddingService, ChunkEmbeddingStore
from app.services.professor_ranking_service import ProfessorRankingService, RankedQuestion
from app.services.semantic_retrieval_service import (
    SemanticRetrievalService,
    cosine_similarity,
)
from app.db.models.chunk_embedding import ChunkEmbedding

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schemas (defined locally so no existing schemas file is modified)
# ---------------------------------------------------------------------------

class RetrievalRequest(BaseModel):
    """Body for POST /retrieval/search.

    Mirrors the inputs of the retrieval block inside
    ``atlas_context_service.build_meeting_context``.
    """
    meeting_id: uuid.UUID
    query: str
    top_k: int | None = None  # falls back to settings.atlas_max_retrieved_chunks


class RetrievedChunkOut(BaseModel):
    """One ranked, deduplicated chunk. Matches the fields Atlas consumes from
    ``MeetingContext.retrieved_chunks`` (RetrievedChunk dataclass)."""
    chunk_text: str
    similarity: float
    start_time: str | None = None
    end_time: str | None = None
    speaker: str | None = None


class RetrievalSearchOut(BaseModel):
    meeting_id: uuid.UUID
    query: str
    chunks: list[RetrievedChunkOut]
    total: int


class RankedQuestionItemOut(BaseModel):
    """One professor-ranked question with the full MCQ content joined.

    Exactly the union of ``RankedQuestion`` (ranking fields) and the
    ``Question`` ORM fields ``atlas_educational_intelligence._ranked_to_mcq_dict``
    reads via ``getattr``. Atlas needs both to render a quiz without any
    additional round-trip.
    """
    # Ranking metadata (from ProfessorRankingService).
    rank: int
    composite_score: float
    rank_reasons: list[str] = []
    concepts: list[str] = []
    # Full MCQ content (from the Question ORM row).
    id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    question_text: str
    question_type: str
    options: list
    correct_answer: str
    explanation: str
    difficulty: str
    is_valid: bool
    is_duplicate: bool
    duplicate_of: str | None = None
    category: str | None = None
    bloom_taxonomy: str | None = None
    educational_score: float | None = None
    relevance_score: float | None = None


class RankedQuestionsOut(BaseModel):
    scope: str  # "meeting" or "transcript"
    scope_id: uuid.UUID
    requested_top_k: int | None
    returned_count: int
    total_ranked: int
    items: list[RankedQuestionItemOut]


# ---------------------------------------------------------------------------
# Retrieval search endpoint
# ---------------------------------------------------------------------------

@router.post("/retrieval/search", response_model=RetrievalSearchOut)
def retrieval_search(
    payload: RetrievalRequest,
    db: Session = Depends(get_db),
) -> RetrievalSearchOut:
    """Server-side embed + ranked semantic retrieval for one meeting.

    Thin wrapper around the same three services Atlas calls in-process
    in ``atlas_context_service.build_meeting_context``. The result is the
    deduplicated, similarity-ranked chunk list. No new logic.
    """
    if not payload.query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty.",
        )

    top_k = payload.top_k or settings.atlas_max_retrieved_chunks
    if top_k <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be a positive integer.",
        )

    try:
        embed_svc = EmbeddingService(config=settings)
        store = ChunkEmbeddingStore(db)
        # Mirror the in-process retrieval block exactly: fetch all
        # embeddings for this meeting, embed the user query, then run
        # the SemanticRetrievalService.search over the candidate pool.
        meeting_embeddings = store.get_for_meeting(payload.meeting_id, embed_svc.model)
        if not meeting_embeddings:
            return RetrievalSearchOut(
                meeting_id=payload.meeting_id,
                query=payload.query,
                chunks=[],
                total=0,
            )

        query_embedding = embed_svc.embed(payload.query)
        retrieval = SemanticRetrievalService(top_k=top_k)
        relevant: list[ChunkEmbedding] = retrieval.search(
            query_embedding, candidates=meeting_embeddings
        )

        # Deduplicate chunks by chunk_text (keep highest similarity first).
        # Same behaviour as the in-process Atlas retrieval path
        # (``atlas_context_service.build_meeting_context``).
        seen: set[str] = set()
        unique_relevant: list[ChunkEmbedding] = []
        for r in relevant:
            if r.chunk_text not in seen:
                seen.add(r.chunk_text)
                unique_relevant.append(r)

        # ``SemanticRetrievalService.search`` returns ``ChunkEmbedding`` rows
        # without an attached similarity score, exactly as in the in-process
        # Atlas path. We recompute the score here with the same shared
        # ``cosine_similarity`` helper from the retrieval service module —
        # no ranking implementation is duplicated; the top-k ordering is
        # already determined by the service.
        chunks_out = [
            RetrievedChunkOut(
                chunk_text=r.chunk_text,
                similarity=cosine_similarity(query_embedding, r.embedding),
                # As with the in-process path, transcript-segment metadata
                # (start_time / end_time / speaker) is not populated at the
                # retrieval boundary; Atlas already tolerates None here.
                start_time=None,
                end_time=None,
                speaker=None,
            )
            for r in unique_relevant
        ]
        return RetrievalSearchOut(
            meeting_id=payload.meeting_id,
            query=payload.query,
            chunks=chunks_out,
            total=len(chunks_out),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "atlas_proxy.retrieval_search.failed",
            extra={"meeting_id": str(payload.meeting_id), "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Ranked-questions endpoints
# ---------------------------------------------------------------------------

def _ranked_to_item(rq: RankedQuestion, question: Question) -> RankedQuestionItemOut:
    """Compose one RankedQuestionItemOut from a rank entry + the Question row.

    Reads ranking fields off the RankedQuestion and MCQ content off the
    Question ORM, exactly as ``atlas_educational_intelligence._ranked_to_mcq_dict``
    does in-process. No business logic; pure field projection.
    """
    return RankedQuestionItemOut(
        # Ranking metadata.
        rank=rq.rank,
        composite_score=rq.composite_score,
        rank_reasons=list(rq.rank_reasons or []),
        concepts=list(rq.concepts or []),
        # Full MCQ content from the Question row.
        id=question.id,
        transcript_id=question.transcript_id,
        meeting_id=question.meeting_id,
        chunk_id=question.chunk_id,
        chunk_index=question.chunk_index,
        question_text=question.question_text or "",
        question_type=question.question_type or "mcq",
        options=list(question.options or []),
        correct_answer=question.correct_answer or "",
        explanation=question.explanation or "",
        difficulty=question.difficulty or "medium",
        is_valid=bool(question.is_valid),
        is_duplicate=bool(question.is_duplicate),
        duplicate_of=question.duplicate_of,
        category=question.category,
        bloom_taxonomy=question.bloom_taxonomy,
        educational_score=question.educational_score,
        relevance_score=question.relevance_score,
    )


def _build_for_transcripts(
    db: Session,
    transcripts: list[Transcript],
    top_k: int | None,
    category: str | None,
    scope: str,
    scope_id: uuid.UUID,
) -> RankedQuestionsOut:
    """Shared helper: rank a set of transcripts, join full Question rows,
    return rank-ordered items. This mirrors the exact in-process flow used
    by ``atlas_educational_intelligence.build_quiz_response``:
      1. Per-transcript ``ProfessorRankingService.rank_questions``
      2. Flatten and sort by composite_score (highest first), preserving
         per-transcript insertion order on ties.
      3. Optionally filter by category.
      4. Optionally trim to ``top_k``.
      5. Join the full ``Question`` rows for the selected question IDs.
    No new logic; the ranking service is the single source of truth for
    ranking.
    """
    # 1) Per-transcript ranking.
    ranking_svc = ProfessorRankingService(db)
    per_transcript_ranked: list[RankedQuestion] = []
    for t in transcripts:
        try:
            result = ranking_svc.rank_questions(t.id)
            if result.ranked:
                per_transcript_ranked.extend(result.ranked)
        except Exception:
            logger.exception(
                "atlas_proxy.ranking_failed",
                extra={"transcript_id": str(t.id)},
            )

    if not per_transcript_ranked:
        return RankedQuestionsOut(
            scope=scope,
            scope_id=scope_id,
            requested_top_k=top_k,
            returned_count=0,
            total_ranked=0,
            items=[],
        )

    # 2) Flatten and sort by composite_score descending, preserving the
    # transcript-then-position order on ties. This is the same merge Atlas
    # performs in-process via ``_merge_ranked_by_score``.
    flattened: list[tuple[float, int, int, RankedQuestion]] = []
    for transcript_rank_idx, rq in enumerate(per_transcript_ranked):
        # enumerate position within the flat list, since the ranking service
        # already returns each transcript's list in rank order.
        flattened.append((-rq.composite_score, transcript_rank_idx, len(flattened), rq))
    flattened.sort(key=lambda t: (t[0], t[1], t[2]))
    merged: list[RankedQuestion] = [t[3] for t in flattened]

    total_ranked = len(merged)

    # 3) Optional category filter on the joined Question.
    if category:
        selected_ids = [rq.question_id for rq in merged if rq.question_id is not None]
        if not selected_ids:
            rows = []
        else:
            rows = db.scalars(
                select(Question).where(Question.id.in_(selected_ids))
            ).all()
        cat_by_id: dict[uuid.UUID, str | None] = {q.id: q.category for q in rows}
        merged = [
            rq for rq in merged
            if cat_by_id.get(rq.question_id) == category
        ]

    # 4) Optional top-K trim.
    if top_k is not None and top_k > 0:
        merged = merged[:top_k]

    if not merged:
        return RankedQuestionsOut(
            scope=scope,
            scope_id=scope_id,
            requested_top_k=top_k,
            returned_count=0,
            total_ranked=total_ranked,
            items=[],
        )

    # 5) Join the full Question rows for the selected ranked IDs.
    selected_ids = [rq.question_id for rq in merged if rq.question_id is not None]
    questions_by_id: dict[uuid.UUID, Question] = {}
    if selected_ids:
        rows = db.scalars(
            select(Question).where(Question.id.in_(selected_ids))
        ).all()
        questions_by_id = {q.id: q for q in rows}

    items: list[RankedQuestionItemOut] = []
    for rq in merged:
        question = questions_by_id.get(rq.question_id)
        if question is None:
            logger.warning(
                "atlas_proxy.ranked_question_missing",
                extra={"question_id": str(rq.question_id)},
            )
            continue
        items.append(_ranked_to_item(rq, question))

    return RankedQuestionsOut(
        scope=scope,
        scope_id=scope_id,
        requested_top_k=top_k,
        returned_count=len(items),
        total_ranked=total_ranked,
        items=items,
    )


@router.get(
    "/meetings/{meeting_id}/ranked-questions",
    response_model=RankedQuestionsOut,
)
def get_meeting_ranked_questions(
    meeting_id: uuid.UUID,
    top_k: int | None = Query(None, ge=1, le=100),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
) -> RankedQuestionsOut:
    """Top-K professor-ranked MCQs for an entire meeting.

    Iterates all transcripts of ``meeting_id``, runs
    ``ProfessorRankingService.rank_questions`` on each, merges by score
    (descending), joins the full Question rows in rank order. This is the
    single round-trip Atlas needs for a meeting-wide quiz — it replaces
    the per-transcript iteration + ORM fetch that
    ``atlas_educational_intelligence.build_quiz_response`` performs
    in-process today. No business logic is duplicated; the ranking
    service is the single source of truth for ordering and scoring.
    """
    transcripts = db.scalars(
        select(Transcript).where(Transcript.meeting_id == meeting_id)
    ).all()

    if not transcripts:
        return RankedQuestionsOut(
            scope="meeting",
            scope_id=meeting_id,
            requested_top_k=top_k,
            returned_count=0,
            total_ranked=0,
            items=[],
        )

    return _build_for_transcripts(
        db=db,
        transcripts=list(transcripts),
        top_k=top_k,
        category=category,
        scope="meeting",
        scope_id=meeting_id,
    )


@router.get(
    "/transcripts/{transcript_id}/ranked-questions",
    response_model=RankedQuestionsOut,
)
def get_transcript_ranked_questions(
    transcript_id: uuid.UUID,
    top_k: int | None = Query(None, ge=1, le=100),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
) -> RankedQuestionsOut:
    """Top-K professor-ranked MCQs for a single transcript.

    Thin wrapper around ``ProfessorRankingService.rank_questions`` plus
    a join of the full Question rows, returned in rank order. This is the
    transcript-scoped counterpart of ``/meetings/{id}/ranked-questions``.
    """
    transcript = db.get(Transcript, transcript_id)
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found",
        )

    return _build_for_transcripts(
        db=db,
        transcripts=[transcript],
        top_k=top_k,
        category=category,
        scope="transcript",
        scope_id=transcript_id,
    )
