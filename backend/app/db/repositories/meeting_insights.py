import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.meeting_insights import MeetingInsights

logger = get_logger(__name__)


def get_by_transcript_id(db: Session, transcript_id: uuid.UUID) -> MeetingInsights | None:
    return db.scalar(
        select(MeetingInsights).where(MeetingInsights.transcript_id == transcript_id)
    )


def get_by_id(db: Session, insight_id: uuid.UUID) -> MeetingInsights | None:
    return db.get(MeetingInsights, insight_id)


def upsert_insights(
    db: Session,
    *,
    transcript_id: uuid.UUID,
    meeting_id: uuid.UUID,
    summary_text: str,
    key_concepts: list[dict],
    action_items: list[dict],
    key_takeaways: list[dict] | None = None,
    learning_outcomes: list[dict] | None = None,
    topics: list[dict] | None = None,
    decisions: list[dict] | None = None,
    recommendations: list[dict] | None = None,
    model_used: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_duration_seconds: float | None = None,
) -> MeetingInsights:
    existing = get_by_transcript_id(db, transcript_id)
    if existing is not None:
        existing.summary_text = summary_text
        existing.key_concepts = key_concepts
        existing.action_items = action_items
        existing.key_takeaways = key_takeaways or []
        existing.learning_outcomes = learning_outcomes or []
        existing.topics = topics or []
        existing.decisions = decisions or []
        existing.recommendations = recommendations or []
        existing.model_used = model_used
        existing.prompt_tokens = prompt_tokens
        existing.completion_tokens = completion_tokens
        existing.total_duration_seconds = total_duration_seconds
        db.flush()
        return existing

    insight = MeetingInsights(
        transcript_id=transcript_id,
        meeting_id=meeting_id,
        summary_text=summary_text,
        key_concepts=key_concepts,
        action_items=action_items,
        key_takeaways=key_takeaways or [],
        learning_outcomes=learning_outcomes or [],
        topics=topics or [],
        decisions=decisions or [],
        recommendations=recommendations or [],
        model_used=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_duration_seconds=total_duration_seconds,
    )
    db.add(insight)
    db.flush()

    logger.info(
        "meeting_insights.upserted",
        extra={
            "transcript_id": str(transcript_id),
            "key_concepts_count": len(key_concepts),
            "action_items_count": len(action_items),
            "key_takeaways_count": len(key_takeaways or []),
            "learning_outcomes_count": len(learning_outcomes or []),
            "topics_count": len(topics or []),
            "decisions_count": len(decisions or []),
            "recommendations_count": len(recommendations or []),
        },
    )
    return insight


def delete_by_transcript_id(db: Session, transcript_id: uuid.UUID) -> int:
    result = db.execute(
        delete(MeetingInsights).where(MeetingInsights.transcript_id == transcript_id)
    )
    return result.rowcount
