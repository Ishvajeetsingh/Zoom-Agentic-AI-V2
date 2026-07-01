import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.db.repositories import learning_outputs as learning_output_repo
from app.db.repositories import meeting_insights as meeting_insights_repo
from app.db.repositories import transcripts as transcript_repo
from app.schemas.learning_outputs import (
    ActionItemsOut,
    DecisionsOut,
    FullInsightsOut,
    KeyConceptsOut,
    KeyTakeawaysOut,
    LearningOutputItem,
    LearningOutputListOut,
    LearningOutcomesOut,
    OutputCountItem,
    OutputCountsOut,
    RecommendationsOut,
    SummaryOut,
    TopicsOut,
)

router = APIRouter()
logger = get_logger(__name__)


def _get_transcript_or_404(db: Session, transcript_id: uuid.UUID):
    transcript = transcript_repo.get_by_id(db, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    return transcript


@router.get("/{transcript_id}/summary", response_model=SummaryOut)
def get_summary(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SummaryOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return SummaryOut(
        transcript_id=transcript_id,
        summary_text=insights.summary_text,
        model_used=insights.model_used,
    )


@router.get("/{transcript_id}/key-concepts", response_model=KeyConceptsOut)
def get_key_concepts(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> KeyConceptsOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return KeyConceptsOut(
        transcript_id=transcript_id,
        key_concepts=insights.key_concepts,
    )


@router.get("/{transcript_id}/action-items", response_model=ActionItemsOut)
def get_action_items(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ActionItemsOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return ActionItemsOut(
        transcript_id=transcript_id,
        action_items=insights.action_items,
    )


@router.get("/{transcript_id}/outputs", response_model=LearningOutputListOut)
def list_outputs(
    transcript_id: uuid.UUID,
    output_type: str | None = Query(None, pattern="^(flashcard|short_question)$"),
    category: str | None = Query(None),
    difficulty: str | None = Query(None),
    bloom_taxonomy: str | None = Query(None, alias="bloom"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    top_n: int | None = Query(None, ge=1, le=100, alias="top"),
    db: Session = Depends(get_db),
) -> LearningOutputListOut:
    _get_transcript_or_404(db, transcript_id)
    if output_type is not None and output_type not in learning_output_repo.VALID_OUTPUT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_type. Must be one of: {sorted(learning_output_repo.VALID_OUTPUT_TYPES)}",
        )
    if category is not None and category not in learning_output_repo.VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {sorted(learning_output_repo.VALID_CATEGORIES)}",
        )
    if difficulty is not None and difficulty not in learning_output_repo.VALID_DIFFICULTIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid difficulty. Must be one of: {sorted(learning_output_repo.VALID_DIFFICULTIES)}",
        )
    if bloom_taxonomy is not None and bloom_taxonomy not in learning_output_repo.VALID_BLOOM_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bloom level. Must be one of: {sorted(learning_output_repo.VALID_BLOOM_LEVELS)}",
        )

    effective_offset = 0 if top_n else offset
    effective_limit = top_n if top_n else limit

    rows, total = learning_output_repo.list_by_transcript(
        db,
        transcript_id,
        output_type=output_type,
        category=category,
        difficulty=difficulty,
        bloom_taxonomy=bloom_taxonomy,
        offset=effective_offset,
        limit=effective_limit,
        order_desc=(order == "desc"),
        order_by_educational=bool(top_n),
    )
    items = [LearningOutputItem.model_validate(row) for row in rows]
    return LearningOutputListOut(items=items, total=total, offset=effective_offset, limit=effective_limit)


@router.get("/{transcript_id}/outputs/count", response_model=OutputCountsOut)
def get_output_counts(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> OutputCountsOut:
    _get_transcript_or_404(db, transcript_id)
    counts = learning_output_repo.count_by_type(db, transcript_id)
    return OutputCountsOut(
        transcript_id=transcript_id,
        counts=[OutputCountItem(output_type=ot, count=c) for ot, c in counts.items()],
    )


@router.get("/{transcript_id}/key-takeaways", response_model=KeyTakeawaysOut)
def get_key_takeaways(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> KeyTakeawaysOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return KeyTakeawaysOut(
        transcript_id=transcript_id,
        key_takeaways=insights.key_takeaways,
    )


@router.get("/{transcript_id}/learning-outcomes", response_model=LearningOutcomesOut)
def get_learning_outcomes(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> LearningOutcomesOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return LearningOutcomesOut(
        transcript_id=transcript_id,
        learning_outcomes=insights.learning_outcomes,
    )


@router.get("/{transcript_id}/topics", response_model=TopicsOut)
def get_topics(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> TopicsOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return TopicsOut(
        transcript_id=transcript_id,
        topics=insights.topics,
    )


@router.get("/{transcript_id}/decisions", response_model=DecisionsOut)
def get_decisions(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DecisionsOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return DecisionsOut(
        transcript_id=transcript_id,
        decisions=insights.decisions,
    )


@router.get("/{transcript_id}/recommendations", response_model=RecommendationsOut)
def get_recommendations(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RecommendationsOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return RecommendationsOut(
        transcript_id=transcript_id,
        recommendations=insights.recommendations,
    )


@router.get("/{transcript_id}/full-insights", response_model=FullInsightsOut)
def get_full_insights(
    transcript_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FullInsightsOut:
    _get_transcript_or_404(db, transcript_id)
    insights = meeting_insights_repo.get_by_transcript_id(db, transcript_id)
    if insights is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No insights found for this transcript. Run the pipeline first.",
        )
    return FullInsightsOut(
        transcript_id=transcript_id,
        summary_text=insights.summary_text,
        model_used=insights.model_used,
        key_concepts=insights.key_concepts,
        action_items=insights.action_items,
        key_takeaways=insights.key_takeaways,
        learning_outcomes=insights.learning_outcomes,
        topics=insights.topics,
        decisions=insights.decisions,
        recommendations=insights.recommendations,
    )
