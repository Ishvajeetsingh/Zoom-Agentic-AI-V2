import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.question import Question
from app.workflows.state import QuestionData

logger = get_logger(__name__)

VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_QUESTION_TYPES = {"mcq", "true_false", "short_answer"}
VALID_CATEGORIES = {"quiz", "concept", "application", "meeting"}
VALID_BLOOM_LEVELS = {"remember", "understand", "apply", "analyze"}


def get_by_id(db: Session, question_id: uuid.UUID) -> Question | None:
    return db.get(Question, question_id)


def get_by_transcript_id(db: Session, transcript_id: uuid.UUID) -> list[Question]:
    rows = db.scalars(
        select(Question)
        .where(Question.transcript_id == transcript_id)
        .order_by(Question.created_at)
    ).all()
    return list(rows)


def list_questions_for_transcript(
    db: Session,
    transcript_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int = 20,
    difficulty: str | None = None,
    question_type: str | None = None,
    category: str | None = None,
    bloom_taxonomy: str | None = None,
    order_desc: bool = False,
    order_by_educational: bool = False,
) -> tuple[list[Question], int]:
    stmt = select(Question).where(Question.transcript_id == transcript_id)

    if difficulty is not None:
        stmt = stmt.where(Question.difficulty == difficulty)
    if question_type is not None:
        stmt = stmt.where(Question.question_type == question_type)
    if category is not None:
        stmt = stmt.where(Question.category == category)
    if bloom_taxonomy is not None:
        stmt = stmt.where(Question.bloom_taxonomy == bloom_taxonomy)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = db.scalar(count_stmt) or 0

    if order_by_educational:
        order_col = Question.educational_score.desc().nulls_last()
    else:
        order_col = Question.created_at.desc() if order_desc else Question.created_at.asc()
    rows = db.scalars(
        stmt.order_by(order_col).offset(offset).limit(limit)
    ).all()

    return list(rows), total


def get_by_chunk_id(db: Session, chunk_id: uuid.UUID) -> list[Question]:
    rows = db.scalars(
        select(Question)
        .where(Question.chunk_id == chunk_id)
        .order_by(Question.created_at)
    ).all()
    return list(rows)


def count_by_transcript_id(db: Session, transcript_id: uuid.UUID) -> int:
    from sqlalchemy import func

    result = db.scalar(
        select(func.count()).select_from(Question).where(Question.transcript_id == transcript_id)
    )
    return result or 0


def delete_by_transcript_id(db: Session, transcript_id: uuid.UUID) -> int:
    result = db.execute(
        delete(Question).where(Question.transcript_id == transcript_id)
    )
    return result.rowcount


def bulk_insert_questions(
    db: Session,
    *,
    transcript_id: uuid.UUID,
    meeting_id: uuid.UUID | None,
    questions: list[QuestionData],
) -> int:
    if not questions:
        return 0

    if meeting_id is None:
        logger.warning(
            "questions.bulk_insert_skipped_no_meeting",
            extra={"transcript_id": str(transcript_id)},
        )
        return 0

    delete_by_transcript_id(db, transcript_id)

    for q in questions:
        db.add(
            Question(
                transcript_id=transcript_id,
                meeting_id=meeting_id,
                chunk_id=q.chunk_id,
                chunk_index=q.chunk_index,
                question_text=q.question_text,
                question_type=q.question_type,
                options=q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                difficulty=q.difficulty,
                is_valid=q.validation_passed,
                is_duplicate=q.is_duplicate,
                duplicate_of=q.duplicate_of,
                category=q.category,
                bloom_taxonomy=q.bloom_taxonomy,
                educational_score=q.educational_score,
                relevance_score=q.relevance_score,
            )
        )

    db.flush()

    logger.info(
        "questions.bulk_inserted",
        extra={
            "transcript_id": str(transcript_id),
            "questions_persisted": len(questions),
        },
    )

    return len(questions)
