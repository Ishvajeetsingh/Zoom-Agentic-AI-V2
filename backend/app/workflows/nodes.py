from __future__ import annotations

import time

from app.core.config import Settings, settings
from app.core.logging import get_logger
from app.db.repositories import learning_outputs as learning_output_repo
from app.db.repositories import meeting_insights as meeting_insights_repo
from app.db.repositories import questions as question_repo
from app.services.learning_output_service import LearningOutputService
from app.services.meeting_insights_service import MeetingInsightsService
from app.services.question_service import QuestionService
from app.workflows.state import ChunkData, ContentAssessment, FlashcardData, QuestionData, ShortQuestionData, WorkflowState, WorkflowStatus

logger = get_logger(__name__)

_SHORT_TRANSCRIPT_WORD_THRESHOLD = 300
_VERY_SHORT_TRANSCRIPT_WORD_THRESHOLD = 100


def assess_content_node(state: WorkflowState, *, db_session=None) -> dict:
    transcript_id = state["transcript_id"]
    chunks = state.get("chunks", [])
    total_words = sum(c.word_count for c in chunks) if chunks else 0

    if db_session is not None:
        from sqlalchemy import select, func as sa_func
        from app.db.models.transcript_chunk import TranscriptChunk
        total_words = db_session.scalar(
            select(sa_func.sum(TranscriptChunk.word_count))
            .where(TranscriptChunk.transcript_id == transcript_id)
        ) or total_words

    is_short = total_words < _SHORT_TRANSCRIPT_WORD_THRESHOLD
    is_very_short = total_words < _VERY_SHORT_TRANSCRIPT_WORD_THRESHOLD

    if is_very_short:
        category = "very_short"
        mcq_feasible = False
        mcq_reason = f"Only {total_words} words — insufficient for diverse MCQ distractors"
        flashcard_feasible = True
        flashcard_reason = "Brief content suitable for flashcard-style recall"
        short_questions_feasible = True
        short_questions_reason = "Brief content suitable for short answer recall"
    elif is_short:
        category = "short"
        mcq_feasible = True
        mcq_reason = f"Short transcript ({total_words} words) — may produce fewer questions"
        flashcard_feasible = True
        flashcard_reason = "Suitable for flashcard generation"
        short_questions_feasible = True
        short_questions_reason = "Suitable for short answer generation"
    else:
        category = "standard"
        mcq_feasible = True
        mcq_reason = "Sufficient content for MCQ generation"
        flashcard_feasible = True
        flashcard_reason = "Suitable for flashcard generation"
        short_questions_feasible = True
        short_questions_reason = "Suitable for short answer generation"

    assessment: ContentAssessment = ContentAssessment(
        word_count=total_words,
        transcript_category=category,
        mcq_feasible=mcq_feasible,
        mcq_reason=mcq_reason,
        flashcard_feasible=flashcard_feasible,
        flashcard_reason=flashcard_reason,
        summary_feasible=True,
        summary_reason="Summary is always feasible",
        insights_feasible=True,
        insights_reason="Insights extraction is always feasible",
        short_questions_feasible=short_questions_feasible,
        short_questions_reason=short_questions_reason,
        recommended_chunk_strategy="adaptive" if is_short else "standard",
    )

    logger.info(
        "workflow.assess_content.completed",
        extra={
            "transcript_id": str(transcript_id),
            "word_count": total_words,
            "category": category,
            "mcq_feasible": mcq_feasible,
        },
    )

    return {
        "content_assessment": assessment,
        "status": WorkflowStatus.ASSESSING,
        "current_node": "assess_content",
    }


def load_chunks_node(state: WorkflowState, *, db_session=None) -> dict:
    transcript_id = state["transcript_id"]

    logger.info(
        "workflow.load_chunks.started",
        extra={"transcript_id": str(transcript_id)},
    )

    if db_session is None:
        return {
            "status": WorkflowStatus.FAILED,
            "error": "No database session provided",
            "current_node": "load_chunks",
        }

    from sqlalchemy import select
    from app.db.models.transcript_chunk import TranscriptChunk

    rows = db_session.scalars(
        select(TranscriptChunk)
        .where(TranscriptChunk.transcript_id == transcript_id)
        .order_by(TranscriptChunk.chunk_index)
    ).all()

    if not rows:
        logger.warning(
            "workflow.load_chunks.no_chunks_found",
            extra={"transcript_id": str(transcript_id)},
        )
        return {
            "status": WorkflowStatus.FAILED,
            "error": f"No chunks found for transcript {transcript_id}",
            "current_node": "load_chunks",
        }

    chunks = [
        ChunkData(
            chunk_id=row.chunk_id,
            chunk_index=row.chunk_index,
            text=row.text,
            word_count=row.word_count,
            speakers=list(row.speakers) if row.speakers else [],
        )
        for row in rows
    ]

    logger.info(
        "workflow.load_chunks.completed",
        extra={
            "transcript_id": str(transcript_id),
            "chunks_loaded": len(chunks),
        },
    )

    return {
        "chunks": chunks,
        "chunks_loaded": len(chunks),
        "status": WorkflowStatus.LOADING_CHUNKS,
        "current_node": "load_chunks",
    }


_GENERATION_MAX_RETRIES = 2
_GENERATION_RETRY_DELAY_SECONDS = 2


def generate_questions_node(
    state: WorkflowState,
    *,
    question_service: QuestionService | None = None,
    config: Settings | None = None,
) -> dict:
    import time

    cfg = config or settings
    transcript_id = state["transcript_id"]
    chunks = state.get("chunks", [])

    logger.info(
        "workflow.generate_questions.started",
        extra={
            "transcript_id": str(transcript_id),
            "chunks_to_process": len(chunks),
        },
    )

    service = question_service or QuestionService(config=cfg)

    all_questions: list[QuestionData] = []
    questions_by_chunk: dict[int, int] = {}
    warnings: list[str] = []
    chunks_failed: list[int] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_duration = 0.0
    model_used: str | None = None

    for chunk in chunks:
        chunk_questions: list[QuestionData] = []
        last_exc: Exception | None = None

        for attempt in range(1, _GENERATION_MAX_RETRIES + 2):
            try:
                result = service.generate_questions_from_chunk(
                    chunk_text=chunk.text,
                    chunk_id=chunk.chunk_id,
                    model=cfg.ollama_primary_model,
                )

                if result.questions:
                    for q in result.questions:
                        chunk_questions.append(
                            QuestionData(
                                question_text=q.question_text,
                                question_type=q.question_type,
                                options=q.options,
                                correct_answer=q.correct_answer,
                                explanation=q.explanation,
                                difficulty=q.difficulty,
                                chunk_id=chunk.chunk_id,
                                chunk_index=chunk.chunk_index,
                            )
                        )

                    if result.total_prompt_tokens is not None:
                        total_prompt_tokens += result.total_prompt_tokens
                    if result.total_completion_tokens is not None:
                        total_completion_tokens += result.total_completion_tokens
                    if result.total_duration_seconds is not None:
                        total_duration += result.total_duration_seconds
                    if model_used is None:
                        model_used = result.model_used
                    last_exc = None
                    break

                logger.warning(
                    "workflow.generate_questions.chunk_zero_questions",
                    extra={
                        "transcript_id": str(transcript_id),
                        "chunk_index": chunk.chunk_index,
                        "attempt": attempt,
                        "max_retries": _GENERATION_MAX_RETRIES,
                    },
                )

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "workflow.generate_questions.chunk_failed",
                    extra={
                        "transcript_id": str(transcript_id),
                        "chunk_index": chunk.chunk_index,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )

            if attempt <= _GENERATION_MAX_RETRIES:
                time.sleep(_GENERATION_RETRY_DELAY_SECONDS)

        all_questions.extend(chunk_questions)
        questions_by_chunk[chunk.chunk_index] = len(chunk_questions)

        if chunk_questions:
            logger.info(
                "workflow.generate_questions.chunk_completed",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunk_index": chunk.chunk_index,
                    "questions_from_chunk": len(chunk_questions),
                },
            )
        else:
            chunks_failed.append(chunk.chunk_index)
            reason = str(last_exc) if last_exc else "zero_questions"
            warn_msg = f"Chunk {chunk.chunk_index}: question generation failed ({reason})"
            warnings.append(warn_msg)
            logger.error(
                "workflow.generate_questions.chunk_exhausted_retries",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunk_index": chunk.chunk_index,
                    "retries_attempted": _GENERATION_MAX_RETRIES,
                    "last_error": reason,
                },
            )

    if chunks_failed:
        warnings.insert(
            0,
            f"{len(chunks_failed)}/{len(chunks)} chunks produced no questions (failed: {chunks_failed})",
        )

    logger.info(
        "workflow.generate_questions.completed",
        extra={
            "transcript_id": str(transcript_id),
            "total_questions": len(all_questions),
            "chunks_processed": len(questions_by_chunk),
            "chunks_failed": len(chunks_failed),
        },
    )

    status = WorkflowStatus.GENERATING

    return {
        "questions_raw": all_questions,
        "questions_generated": len(all_questions),
        "questions_by_chunk": questions_by_chunk,
        "warnings": warnings,
        "questions_model_used": model_used,
        "questions_total_prompt_tokens": total_prompt_tokens if total_prompt_tokens > 0 else None,
        "questions_total_completion_tokens": total_completion_tokens if total_completion_tokens > 0 else None,
        "questions_total_duration_seconds": total_duration if total_duration > 0 else None,
        "status": status,
        "current_node": "generate_questions",
    }


def validate_questions_node(state: WorkflowState, *, config: Settings | None = None) -> dict:
    cfg = config or settings
    transcript_id = state["transcript_id"]
    questions_raw = state.get("questions_raw", [])

    logger.info(
        "workflow.validate_questions.started",
        extra={
            "transcript_id": str(transcript_id),
            "questions_to_validate": len(questions_raw),
        },
    )

    valid: list[QuestionData] = []
    invalid: list[QuestionData] = []

    for q in questions_raw:
        errors: list[str] = []

        if not q.question_text or len(q.question_text.strip()) < 10:
            errors.append("question_text too short or empty")

        if not q.options or len(q.options) < 2:
            errors.append("must have at least 2 options")
        elif len(q.options) != 4:
            errors.append(f"expected 4 options, got {len(q.options)}")

        if not q.correct_answer or len(q.correct_answer.strip()) == 0:
            errors.append("correct_answer is empty")
        else:
            answer_letter = q.correct_answer.strip()[0].upper()
            if answer_letter not in "ABCD":
                errors.append(f"correct_answer '{q.correct_answer}' is not A/B/C/D")

        if not q.explanation or len(q.explanation.strip()) < 5:
            errors.append("explanation too short or empty")

        if q.difficulty not in ("easy", "medium", "hard"):
            errors.append(f"invalid difficulty: {q.difficulty}")

        if q.question_type != "mcq":
            errors.append(f"unsupported question_type: {q.question_type}")

        if len(questions_raw) > cfg.question_max_count * 2:
            if q.difficulty not in ("easy", "medium", "hard"):
                errors.append("invalid difficulty for filtering")

        q.validation_passed = len(errors) == 0
        q.validation_errors = errors

        if q.validation_passed:
            valid.append(q)
        else:
            invalid.append(q)

    logger.info(
        "workflow.validate_questions.completed",
        extra={
            "transcript_id": str(transcript_id),
            "valid": len(valid),
            "invalid": len(invalid),
        },
    )

    return {
        "questions_valid": valid,
        "questions_invalid": invalid,
        "questions_validated": len(valid),
        "status": WorkflowStatus.VALIDATING,
        "current_node": "validate_questions",
    }


def deduplicate_questions_node(state: WorkflowState) -> dict:
    from app.workflows.dedup import deduplicate_questions

    transcript_id = state["transcript_id"]
    questions_valid = state.get("questions_valid", [])

    logger.info(
        "workflow.deduplicate.started",
        extra={
            "transcript_id": str(transcript_id),
            "questions_to_dedup": len(questions_valid),
        },
    )

    unique, duplicates_removed = deduplicate_questions(questions_valid)

    logger.info(
        "workflow.deduplicate.completed",
        extra={
            "transcript_id": str(transcript_id),
            "unique_questions": len(unique),
            "duplicates_removed": duplicates_removed,
        },
    )

    return {
        "questions_unique": unique,
        "duplicates_removed": duplicates_removed,
        "status": WorkflowStatus.DEDUPLICATING,
        "current_node": "deduplicate",
    }


def persist_questions_node(state: WorkflowState, *, db_session=None) -> dict:
    transcript_id = state["transcript_id"]
    meeting_id = state.get("meeting_id")
    questions_unique = state.get("questions_unique", [])

    logger.info(
        "workflow.persist_questions.started",
        extra={
            "transcript_id": str(transcript_id),
            "questions_to_persist": len(questions_unique),
        },
    )

    if db_session is None:
        return {
            "status": WorkflowStatus.FAILED,
            "error": "No database session provided for question persistence",
            "current_node": "persist_questions",
        }

    if not questions_unique:
        logger.warning(
            "workflow.persist_questions.no_questions",
            extra={"transcript_id": str(transcript_id)},
        )
        return {
            "questions_persisted": 0,
            "status": WorkflowStatus.PERSISTING,
            "current_node": "persist_questions",
        }

    try:
        persisted_count = question_repo.bulk_insert_questions(
            db_session,
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            questions=questions_unique,
        )
    except Exception as exc:
        logger.exception(
            "workflow.persist_questions.failed",
            extra={
                "transcript_id": str(transcript_id),
                "error": str(exc),
            },
        )
        existing_warnings = state.get("warnings", [])
        merged_warnings = existing_warnings + [f"Question persistence failed: {exc}"]
        return {
            "questions_persisted": 0,
            "warnings": merged_warnings,
            "status": WorkflowStatus.PERSISTING,
            "current_node": "persist_questions",
        }

    logger.info(
        "workflow.persist_questions.completed",
        extra={
            "transcript_id": str(transcript_id),
            "questions_persisted": persisted_count,
        },
    )

    return {
        "questions_persisted": persisted_count,
        "status": WorkflowStatus.PERSISTING,
        "current_node": "persist_questions",
    }


def finalize_node(state: WorkflowState) -> dict:
    transcript_id = state["transcript_id"]
    questions_unique = state.get("questions_unique", [])
    warnings = list(state.get("warnings", []))

    logger.info(
        "workflow.finalize.started",
        extra={
            "transcript_id": str(transcript_id),
            "unique_questions": len(questions_unique),
            "warnings": len(warnings),
        },
    )

    total_questions = len(questions_unique)
    questions_persisted = state.get("questions_persisted", 0)
    assessment = state.get("content_assessment", {})
    is_short = assessment.get("transcript_category") in ("short", "very_short")

    if total_questions == 0:
        chunks_loaded = state.get("chunks_loaded", 0)
        questions_generated = state.get("questions_generated", 0)

        if is_short or chunks_loaded <= 2:
            logger.warning(
                "workflow.finalize.zero_questions_degraded",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunks_loaded": chunks_loaded,
                    "questions_generated": questions_generated,
                    "is_short_transcript": is_short,
                },
            )
            warnings.append(
                f"No MCQ questions generated from {chunks_loaded} chunks "
                f"({questions_generated} raw). Short transcript may not contain enough "
                f"diverse content for MCQ distractors. Learning outputs and insights "
                f"may still be available."
            )
        else:
            logger.error(
                "workflow.finalize.zero_questions",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunks_loaded": chunks_loaded,
                    "questions_generated": questions_generated,
                },
            )
            warnings.append(
                f"Question generation produced 0 valid questions "
                f"(chunks_loaded={chunks_loaded}, questions_generated={questions_generated}). "
                f"The LLM may have returned an unexpected response format."
            )

        did_produce_learning = state.get("learning_outputs_persisted", 0) > 0
        did_produce_insights = state.get("insights_persisted", False)

        if did_produce_learning or did_produce_insights:
            logger.info(
                "workflow.finalize.degraded_completion",
                extra={
                    "transcript_id": str(transcript_id),
                    "learning_outputs_persisted": state.get("learning_outputs_persisted", 0),
                    "insights_persisted": did_produce_insights,
                },
            )
            warnings.insert(0, "No MCQ questions produced, but other outputs are available")
            return _build_finalize_output(
                state,
                total_questions=0,
                questions_persisted=0,
                warnings=warnings,
                status=WorkflowStatus.COMPLETED_WITH_WARNINGS,
            )

        return {
            "status": WorkflowStatus.FAILED,
            "error": warnings[-1] if warnings else "Zero questions with no outputs",
            "warnings": warnings,
            "current_node": "finalize",
        }

    if warnings:
        logger.info(
            "workflow.finalize.completed_with_warnings",
            extra={
                "transcript_id": str(transcript_id),
                "total_questions": total_questions,
                "warning_count": len(warnings),
            },
        )
        return _build_finalize_output(
            state,
            total_questions=total_questions,
            questions_persisted=questions_persisted,
            warnings=warnings,
            status=WorkflowStatus.COMPLETED_WITH_WARNINGS,
        )

    return _build_finalize_output(
        state,
        total_questions=total_questions,
        questions_persisted=questions_persisted,
        warnings=[],
        status=WorkflowStatus.COMPLETED,
    )


def _build_finalize_output(
    state: WorkflowState,
    *,
    total_questions: int,
    questions_persisted: int,
    warnings: list[str],
    status: WorkflowStatus,
) -> dict:
    def _safe_add(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    questions_model = state.get("questions_model_used")
    learning_model = state.get("learning_model_used")
    insights_model = state.get("insights_model_used")
    aggregate_model = insights_model or learning_model or questions_model

    aggregate_prompt_tokens = _safe_add(
        _safe_add(
            state.get("questions_total_prompt_tokens"),
            state.get("learning_total_prompt_tokens"),
        ),
        state.get("insights_total_prompt_tokens"),
    )
    aggregate_completion_tokens = _safe_add(
        _safe_add(
            state.get("questions_total_completion_tokens"),
            state.get("learning_total_completion_tokens"),
        ),
        state.get("insights_total_completion_tokens"),
    )
    aggregate_duration = _safe_add(
        _safe_add(
            state.get("questions_total_duration_seconds"),
            state.get("learning_total_duration_seconds"),
        ),
        state.get("insights_total_duration_seconds"),
    )

    logger.info(
        "workflow.finalize.output",
        extra={
            "transcript_id": str(state.get("transcript_id", "")),
            "total_questions": total_questions,
            "questions_persisted": questions_persisted,
            "status": status.value,
            "warning_count": len(warnings),
            "model_used": aggregate_model,
        },
    )

    return {
        "total_questions": total_questions,
        "questions_persisted": questions_persisted,
        "model_used": aggregate_model,
        "total_prompt_tokens": aggregate_prompt_tokens,
        "total_completion_tokens": aggregate_completion_tokens,
        "total_duration_seconds": aggregate_duration,
        "warnings": warnings,
        "status": status,
        "current_node": "finalize",
    }


def handle_failure_node(state: WorkflowState) -> dict:
    logger.error(
        "workflow.failure",
        extra={
            "transcript_id": str(state.get("transcript_id", "")),
            "error": state.get("error"),
            "current_node": state.get("current_node", ""),
        },
    )

    return {
        "status": WorkflowStatus.FAILED,
        "current_node": "handle_failure",
    }


_LEARNING_MAX_RETRIES = 2
_LEARNING_RETRY_DELAY_SECONDS = 2


def generate_learning_outputs_node(
    state: WorkflowState,
    *,
    learning_service: LearningOutputService | None = None,
    config: Settings | None = None,
) -> dict:
    cfg = config or settings
    transcript_id = state["transcript_id"]
    chunks = state.get("chunks", [])

    logger.info(
        "workflow.generate_learning_outputs.started",
        extra={
            "transcript_id": str(transcript_id),
            "chunks_to_process": len(chunks),
        },
    )

    service = learning_service or LearningOutputService(config=cfg)

    all_flashcards: list[FlashcardData] = []
    all_short_questions: list[ShortQuestionData] = []
    warnings: list[str] = []
    chunks_failed: list[int] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_duration = 0.0
    model_used: str | None = None

    for chunk in chunks:
        chunk_flashcards: list[FlashcardData] = []
        chunk_short_questions: list[ShortQuestionData] = []
        last_exc: Exception | None = None

        for attempt in range(1, _LEARNING_MAX_RETRIES + 2):
            try:
                result = service.generate_from_chunk(
                    chunk_text=chunk.text,
                    chunk_id=chunk.chunk_id,
                    model=cfg.ollama_primary_model,
                )

                for fc in result.flashcards:
                    chunk_flashcards.append(
                        FlashcardData(
                            front=fc.front,
                            back=fc.back,
                            category=fc.category,
                            chunk_id=chunk.chunk_id,
                            chunk_index=chunk.chunk_index,
                        )
                    )

                for sq in result.short_questions:
                    chunk_short_questions.append(
                        ShortQuestionData(
                            question_text=sq.question_text,
                            sample_answer=sq.sample_answer,
                            difficulty=sq.difficulty,
                            chunk_id=chunk.chunk_id,
                            chunk_index=chunk.chunk_index,
                        )
                    )

                if result.prompt_tokens is not None:
                    total_prompt_tokens += result.prompt_tokens
                if result.completion_tokens is not None:
                    total_completion_tokens += result.completion_tokens
                if result.total_duration_seconds is not None:
                    total_duration += result.total_duration_seconds
                if model_used is None:
                    model_used = result.model_used
                last_exc = None
                break

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "workflow.generate_learning_outputs.chunk_failed",
                    extra={
                        "transcript_id": str(transcript_id),
                        "chunk_index": chunk.chunk_index,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                if attempt <= _LEARNING_MAX_RETRIES:
                    time.sleep(_LEARNING_RETRY_DELAY_SECONDS)

        all_flashcards.extend(chunk_flashcards)
        all_short_questions.extend(chunk_short_questions)

        if chunk_flashcards or chunk_short_questions:
            logger.info(
                "workflow.generate_learning_outputs.chunk_completed",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunk_index": chunk.chunk_index,
                    "flashcards": len(chunk_flashcards),
                    "short_questions": len(chunk_short_questions),
                },
            )
        else:
            chunks_failed.append(chunk.chunk_index)
            reason = str(last_exc) if last_exc else "zero_outputs"
            warnings.append(f"Chunk {chunk.chunk_index}: learning output generation failed ({reason})")
            logger.error(
                "workflow.generate_learning_outputs.chunk_exhausted_retries",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunk_index": chunk.chunk_index,
                    "last_error": reason,
                },
            )

    if chunks_failed:
        warnings.insert(
            0,
            f"{len(chunks_failed)}/{len(chunks)} chunks produced no learning outputs (failed: {chunks_failed})",
        )

    existing_warnings = state.get("warnings", [])
    merged_warnings = existing_warnings + warnings

    logger.info(
        "workflow.generate_learning_outputs.completed",
        extra={
            "transcript_id": str(transcript_id),
            "total_flashcards": len(all_flashcards),
            "total_short_questions": len(all_short_questions),
            "chunks_failed": len(chunks_failed),
        },
    )

    return {
        "flashcards_raw": all_flashcards,
        "short_questions_raw": all_short_questions,
        "learning_model_used": model_used,
        "learning_total_prompt_tokens": total_prompt_tokens if total_prompt_tokens > 0 else None,
        "learning_total_completion_tokens": total_completion_tokens if total_completion_tokens > 0 else None,
        "learning_total_duration_seconds": total_duration if total_duration > 0 else None,
        "warnings": merged_warnings,
        "status": WorkflowStatus.GENERATING_LEARNING,
        "current_node": "generate_learning_outputs",
    }


def validate_learning_outputs_node(state: WorkflowState, *, config: Settings | None = None) -> dict:
    transcript_id = state["transcript_id"]
    flashcards_raw = state.get("flashcards_raw", [])
    short_questions_raw = state.get("short_questions_raw", [])

    logger.info(
        "workflow.validate_learning_outputs.started",
        extra={
            "transcript_id": str(transcript_id),
            "flashcards_to_validate": len(flashcards_raw),
            "short_questions_to_validate": len(short_questions_raw),
        },
    )

    flashcards_valid: list[FlashcardData] = []
    flashcards_invalid: list[FlashcardData] = []

    for fc in flashcards_raw:
        errors: list[str] = []
        if not fc.front or len(fc.front.strip()) < 5:
            errors.append("front too short or empty")
        if not fc.back or len(fc.back.strip()) < 5:
            errors.append("back too short or empty")
        fc.validation_passed = len(errors) == 0
        fc.validation_errors = errors
        if fc.validation_passed:
            flashcards_valid.append(fc)
        else:
            flashcards_invalid.append(fc)

    short_questions_valid: list[ShortQuestionData] = []
    short_questions_invalid: list[ShortQuestionData] = []

    for sq in short_questions_raw:
        errors: list[str] = []
        if not sq.question_text or len(sq.question_text.strip()) < 10:
            errors.append("question_text too short or empty")
        if not sq.sample_answer or len(sq.sample_answer.strip()) < 5:
            errors.append("sample_answer too short or empty")
        if sq.difficulty not in ("easy", "medium", "hard"):
            errors.append(f"invalid difficulty: {sq.difficulty}")
        sq.validation_passed = len(errors) == 0
        sq.validation_errors = errors
        if sq.validation_passed:
            short_questions_valid.append(sq)
        else:
            short_questions_invalid.append(sq)

    logger.info(
        "workflow.validate_learning_outputs.completed",
        extra={
            "transcript_id": str(transcript_id),
            "flashcards_valid": len(flashcards_valid),
            "flashcards_invalid": len(flashcards_invalid),
            "short_questions_valid": len(short_questions_valid),
            "short_questions_invalid": len(short_questions_invalid),
        },
    )

    return {
        "flashcards_valid": flashcards_valid,
        "short_questions_valid": short_questions_valid,
        "status": WorkflowStatus.VALIDATING_LEARNING,
        "current_node": "validate_learning_outputs",
    }


def persist_learning_outputs_node(state: WorkflowState, *, db_session=None) -> dict:
    transcript_id = state["transcript_id"]
    meeting_id = state.get("meeting_id")
    flashcards_valid = state.get("flashcards_valid", [])
    short_questions_valid = state.get("short_questions_valid", [])

    logger.info(
        "workflow.persist_learning_outputs.started",
        extra={
            "transcript_id": str(transcript_id),
            "flashcards_to_persist": len(flashcards_valid),
            "short_questions_to_persist": len(short_questions_valid),
        },
    )

    if db_session is None:
        return {
            "status": WorkflowStatus.FAILED,
            "error": "No database session provided for learning output persistence",
            "current_node": "persist_learning_outputs",
        }

    if meeting_id is None:
        logger.warning(
            "workflow.persist_learning_outputs.skipped_no_meeting",
            extra={"transcript_id": str(transcript_id)},
        )
        return {
            "learning_outputs_persisted": 0,
            "status": WorkflowStatus.PERSISTING_LEARNING,
            "current_node": "persist_learning_outputs",
        }

    outputs: list[dict] = []

    for fc in flashcards_valid:
        content = {"front": fc.front, "back": fc.back}
        if fc.category:
            content["category"] = fc.category
        outputs.append({
            "chunk_id": fc.chunk_id,
            "output_type": "flashcard",
            "content": content,
        })

    for sq in short_questions_valid:
        outputs.append({
            "chunk_id": sq.chunk_id,
            "output_type": "short_question",
            "content": {
                "question_text": sq.question_text,
                "sample_answer": sq.sample_answer,
            },
            "difficulty": sq.difficulty,
        })

    try:
        learning_output_repo.delete_by_transcript_id(db_session, transcript_id)
        persisted = learning_output_repo.bulk_insert(
            db_session,
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            outputs=outputs,
        )
    except Exception as exc:
        logger.exception(
            "workflow.persist_learning_outputs.failed",
            extra={
                "transcript_id": str(transcript_id),
                "error": str(exc),
            },
        )
        existing_warnings = state.get("warnings", [])
        merged_warnings = existing_warnings + [f"Learning output persistence failed: {exc}"]
        return {
            "learning_outputs_persisted": 0,
            "warnings": merged_warnings,
            "status": WorkflowStatus.PERSISTING_LEARNING,
            "current_node": "persist_learning_outputs",
        }

    logger.info(
        "workflow.persist_learning_outputs.completed",
        extra={
            "transcript_id": str(transcript_id),
            "outputs_persisted": persisted,
        },
    )

    return {
        "learning_outputs_persisted": persisted,
        "status": WorkflowStatus.PERSISTING_LEARNING,
        "current_node": "persist_learning_outputs",
    }


def synthesize_meeting_insights_node(
    state: WorkflowState,
    *,
    db_session=None,
    insights_service: MeetingInsightsService | None = None,
    config: Settings | None = None,
) -> dict:
    cfg = config or settings
    transcript_id = state["transcript_id"]
    meeting_id = state.get("meeting_id")

    logger.info(
        "workflow.synthesize_meeting_insights.started",
        extra={"transcript_id": str(transcript_id)},
    )

    if db_session is None:
        return {
            "status": WorkflowStatus.FAILED,
            "error": "No database session provided for meeting insights synthesis",
            "current_node": "synthesize_meeting_insights",
        }

    if meeting_id is None:
        logger.warning(
            "workflow.synthesize_meeting_insights.skipped_no_meeting",
            extra={"transcript_id": str(transcript_id)},
        )
        return {
            "insights_summary": "",
            "insights_key_concepts": [],
            "insights_action_items": [],
            "insights_key_takeaways": [],
            "insights_learning_outcomes": [],
            "insights_topics": [],
            "insights_decisions": [],
            "insights_recommendations": [],
            "insights_persisted": False,
            "status": WorkflowStatus.SYNTHESIZING,
            "current_node": "synthesize_meeting_insights",
        }

    service = insights_service or MeetingInsightsService(db_session, config=cfg)

    try:
        result = service.synthesize(
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            model=cfg.ollama_primary_model,
        )
    except Exception as exc:
        logger.exception(
            "workflow.synthesize_meeting_insights.failed",
            extra={
                "transcript_id": str(transcript_id),
                "error": str(exc),
            },
        )
        existing_warnings = state.get("warnings", [])
        merged_warnings = existing_warnings + [f"Insights synthesis failed: {exc}"]
        return {
            "insights_summary": "",
            "insights_key_concepts": [],
            "insights_action_items": [],
            "insights_key_takeaways": [],
            "insights_learning_outcomes": [],
            "insights_topics": [],
            "insights_decisions": [],
            "insights_recommendations": [],
            "insights_persisted": False,
            "warnings": merged_warnings,
            "status": WorkflowStatus.SYNTHESIZING,
            "current_node": "synthesize_meeting_insights",
        }

    return {
        "insights_summary": result.summary_text,
        "insights_key_concepts": [
            {"concept": kc.concept, "description": kc.description, "importance_order": kc.importance_order}
            for kc in result.key_concepts
        ],
        "insights_action_items": [
            {"item_text": ai.item_text, "assignee": ai.assignee, "priority": ai.priority, "due_date": ai.due_date}
            for ai in result.action_items
        ],
        "insights_key_takeaways": [
            {"takeaway": kt.takeaway, "context": kt.context}
            for kt in result.key_takeaways
        ],
        "insights_learning_outcomes": [
            {"outcome": lo.outcome, "category": lo.category}
            for lo in result.learning_outcomes
        ],
        "insights_topics": [
            {"topic": t.topic, "relevance": t.relevance}
            for t in result.topics
        ],
        "insights_decisions": [
            {"decision": d.decision, "rationale": d.rationale, "decided_by": d.decided_by}
            for d in result.decisions
        ],
        "insights_recommendations": [
            {"recommendation": r.recommendation, "priority": r.priority, "target_audience": r.target_audience}
            for r in result.recommendations
        ],
        "insights_model_used": result.model_used,
        "insights_total_prompt_tokens": result.prompt_tokens,
        "insights_total_completion_tokens": result.completion_tokens,
        "insights_total_duration_seconds": result.total_duration_seconds,
        "status": WorkflowStatus.SYNTHESIZING,
        "current_node": "synthesize_meeting_insights",
    }


def persist_meeting_insights_node(state: WorkflowState, *, db_session=None) -> dict:
    transcript_id = state["transcript_id"]
    meeting_id = state.get("meeting_id")
    summary = state.get("insights_summary", "")
    key_concepts = state.get("insights_key_concepts", [])
    action_items = state.get("insights_action_items", [])
    key_takeaways = state.get("insights_key_takeaways", [])
    learning_outcomes = state.get("insights_learning_outcomes", [])
    topics = state.get("insights_topics", [])
    decisions = state.get("insights_decisions", [])
    recommendations = state.get("insights_recommendations", [])

    logger.info(
        "workflow.persist_meeting_insights.started",
        extra={
            "transcript_id": str(transcript_id),
            "key_concepts_count": len(key_concepts),
            "action_items_count": len(action_items),
        },
    )

    if db_session is None:
        return {
            "status": WorkflowStatus.FAILED,
            "error": "No database session provided for meeting insights persistence",
            "current_node": "persist_meeting_insights",
        }

    if meeting_id is None or not summary:
        logger.warning(
            "workflow.persist_meeting_insights.skipped",
            extra={
                "transcript_id": str(transcript_id),
                "has_meeting_id": meeting_id is not None,
                "has_summary": bool(summary),
            },
        )
        return {
            "insights_persisted": False,
            "status": WorkflowStatus.PERSISTING_INSIGHTS,
            "current_node": "persist_meeting_insights",
        }

    model_used = state.get("insights_model_used")
    prompt_tokens = state.get("insights_total_prompt_tokens")
    completion_tokens = state.get("insights_total_completion_tokens")
    total_duration = state.get("insights_total_duration_seconds")

    try:
        meeting_insights_repo.upsert_insights(
            db_session,
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            summary_text=summary,
            key_concepts=key_concepts,
            action_items=action_items,
            key_takeaways=key_takeaways,
            learning_outcomes=learning_outcomes,
            topics=topics,
            decisions=decisions,
            recommendations=recommendations,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_duration_seconds=total_duration,
        )
    except Exception as exc:
        logger.exception(
            "workflow.persist_meeting_insights.failed",
            extra={
                "transcript_id": str(transcript_id),
                "error": str(exc),
            },
        )
        existing_warnings = state.get("warnings", [])
        merged_warnings = existing_warnings + [f"Insights persistence failed: {exc}"]
        return {
            "insights_persisted": False,
            "warnings": merged_warnings,
            "status": WorkflowStatus.PERSISTING_INSIGHTS,
            "current_node": "persist_meeting_insights",
        }

    logger.info(
        "workflow.persist_meeting_insights.completed",
        extra={"transcript_id": str(transcript_id)},
    )

    return {
        "insights_persisted": True,
        "status": WorkflowStatus.PERSISTING_INSIGHTS,
        "current_node": "persist_meeting_insights",
    }
