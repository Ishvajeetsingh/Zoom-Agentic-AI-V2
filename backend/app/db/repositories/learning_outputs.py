import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.learning_output import LearningOutput

logger = get_logger(__name__)

VALID_OUTPUT_TYPES = {"flashcard", "short_question"}
VALID_CATEGORIES = {"core_concept", "definition", "important_term", "revision", "concept", "application", "meeting"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_BLOOM_LEVELS = {"remember", "understand", "apply", "analyze"}


def get_by_id(db: Session, output_id: uuid.UUID) -> LearningOutput | None:
    return db.get(LearningOutput, output_id)


def list_by_transcript(
    db: Session,
    transcript_id: uuid.UUID,
    *,
    output_type: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    bloom_taxonomy: str | None = None,
    offset: int = 0,
    limit: int = 20,
    order_desc: bool = False,
    order_by_educational: bool = False,
) -> tuple[list[LearningOutput], int]:
    stmt = select(LearningOutput).where(LearningOutput.transcript_id == transcript_id)
    count_stmt = select(func.count()).select_from(LearningOutput).where(
        LearningOutput.transcript_id == transcript_id
    )

    if output_type is not None:
        stmt = stmt.where(LearningOutput.output_type == output_type)
        count_stmt = count_stmt.where(LearningOutput.output_type == output_type)
    if category is not None:
        stmt = stmt.where(LearningOutput.category == category)
        count_stmt = count_stmt.where(LearningOutput.category == category)
    if difficulty is not None:
        stmt = stmt.where(LearningOutput.difficulty == difficulty)
        count_stmt = count_stmt.where(LearningOutput.difficulty == difficulty)
    if bloom_taxonomy is not None:
        stmt = stmt.where(LearningOutput.bloom_taxonomy == bloom_taxonomy)
        count_stmt = count_stmt.where(LearningOutput.bloom_taxonomy == bloom_taxonomy)

    total: int = db.scalar(count_stmt) or 0

    if order_by_educational:
        order_col = LearningOutput.educational_score.desc().nulls_last()
    else:
        order_col = LearningOutput.created_at.desc() if order_desc else LearningOutput.created_at.asc()
    rows = db.scalars(stmt.order_by(order_col).offset(offset).limit(limit)).all()

    return list(rows), total


def count_by_type(db: Session, transcript_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(LearningOutput.output_type, func.count(LearningOutput.id))
        .where(LearningOutput.transcript_id == transcript_id)
        .group_by(LearningOutput.output_type)
    ).all()
    return {row[0]: row[1] for row in rows}


def bulk_insert(
    db: Session,
    *,
    transcript_id: uuid.UUID,
    meeting_id: uuid.UUID,
    outputs: list[dict],
) -> int:
    if not outputs:
        return 0

    for out in outputs:
        db.add(
            LearningOutput(
                transcript_id=transcript_id,
                meeting_id=meeting_id,
                chunk_id=out.get("chunk_id"),
                output_type=out["output_type"],
                content=out["content"],
                difficulty=out.get("difficulty"),
                category=out.get("category"),
                bloom_taxonomy=out.get("bloom_taxonomy"),
                educational_score=out.get("educational_score"),
            )
        )
    db.flush()

    logger.info(
        "learning_outputs.bulk_inserted",
        extra={
            "transcript_id": str(transcript_id),
            "outputs_persisted": len(outputs),
        },
    )
    return len(outputs)


def delete_by_transcript_id(db: Session, transcript_id: uuid.UUID) -> int:
    result = db.execute(
        delete(LearningOutput).where(LearningOutput.transcript_id == transcript_id)
    )
    return result.rowcount
