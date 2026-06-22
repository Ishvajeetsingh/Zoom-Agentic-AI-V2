from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NotRequired, TypedDict


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    LOADING_CHUNKS = "loading_chunks"
    ASSESSING = "assessing"
    GENERATING = "generating"
    GENERATING_LEARNING = "generating_learning"
    VALIDATING = "validating"
    VALIDATING_LEARNING = "validating_learning"
    DEDUPLICATING = "deduplicating"
    PERSISTING = "persisting"
    PERSISTING_LEARNING = "persisting_learning"
    SYNTHESIZING = "synthesizing"
    PERSISTING_INSIGHTS = "persisting_insights"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


@dataclass
class ChunkData:
    chunk_id: uuid.UUID
    chunk_index: int
    text: str
    word_count: int
    speakers: list[str] = field(default_factory=list)


@dataclass
class FlashcardData:
    front: str
    back: str
    category: str | None = None
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    validation_passed: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class ShortQuestionData:
    question_text: str
    sample_answer: str
    difficulty: str
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    validation_passed: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class QuestionData:
    question_text: str
    question_type: str
    options: list[str]
    correct_answer: str
    explanation: str
    difficulty: str
    chunk_id: uuid.UUID | None = None
    chunk_index: int | None = None
    validation_passed: bool = True
    validation_errors: list[str] = field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of: str | None = None


class ContentAssessment(TypedDict, total=False):
    word_count: int
    transcript_category: str
    mcq_feasible: bool
    mcq_reason: str
    flashcard_feasible: bool
    flashcard_reason: str
    summary_feasible: bool
    summary_reason: str
    insights_feasible: bool
    insights_reason: str
    short_questions_feasible: bool
    short_questions_reason: str
    recommended_chunk_strategy: str


class WorkflowState(TypedDict, total=False):
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None
    status: WorkflowStatus
    current_node: str
    error: str | None
    warnings: list[str]

    chunks: list[ChunkData]
    chunks_loaded: int

    content_assessment: ContentAssessment

    questions_raw: list[QuestionData]
    questions_generated: int
    questions_by_chunk: dict[int, int]

    questions_valid: list[QuestionData]
    questions_invalid: list[QuestionData]
    questions_validated: int

    questions_unique: list[QuestionData]
    duplicates_removed: int

    questions_persisted: int

    flashcards_raw: list[FlashcardData]
    short_questions_raw: list[ShortQuestionData]
    flashcards_valid: list[FlashcardData]
    short_questions_valid: list[ShortQuestionData]
    learning_outputs_persisted: int

    insights_summary: str
    insights_key_concepts: list[dict]
    insights_action_items: list[dict]
    insights_key_takeaways: list[dict]
    insights_learning_outcomes: list[dict]
    insights_topics: list[dict]
    insights_decisions: list[dict]
    insights_recommendations: list[dict]
    insights_persisted: bool

    questions_model_used: str | None
    questions_total_prompt_tokens: int | None
    questions_total_completion_tokens: int | None
    questions_total_duration_seconds: float | None

    learning_model_used: str | None
    learning_total_prompt_tokens: int | None
    learning_total_completion_tokens: int | None
    learning_total_duration_seconds: float | None

    insights_model_used: str | None
    insights_total_prompt_tokens: int | None
    insights_total_completion_tokens: int | None
    insights_total_duration_seconds: float | None

    total_questions: int
    model_used: str | None
    total_prompt_tokens: int | None
    total_completion_tokens: int | None
    total_duration_seconds: float | None

    metadata: dict[str, Any]


def make_initial_state(
    transcript_id: uuid.UUID,
    meeting_id: uuid.UUID | None = None,
) -> WorkflowState:
    return WorkflowState(
        transcript_id=transcript_id,
        meeting_id=meeting_id,
        status=WorkflowStatus.PENDING,
        current_node="",
        error=None,
        warnings=[],
        chunks=[],
        chunks_loaded=0,
        content_assessment=ContentAssessment(),
        questions_raw=[],
        questions_generated=0,
        questions_by_chunk={},
        questions_valid=[],
        questions_invalid=[],
        questions_validated=0,
        questions_unique=[],
        duplicates_removed=0,
        questions_persisted=0,
        flashcards_raw=[],
        short_questions_raw=[],
        flashcards_valid=[],
        short_questions_valid=[],
        learning_outputs_persisted=0,
        insights_summary="",
        insights_key_concepts=[],
        insights_action_items=[],
        insights_key_takeaways=[],
        insights_learning_outcomes=[],
        insights_topics=[],
        insights_decisions=[],
        insights_recommendations=[],
        insights_persisted=False,
        questions_model_used=None,
        questions_total_prompt_tokens=None,
        questions_total_completion_tokens=None,
        questions_total_duration_seconds=None,
        learning_model_used=None,
        learning_total_prompt_tokens=None,
        learning_total_completion_tokens=None,
        learning_total_duration_seconds=None,
        insights_model_used=None,
        insights_total_prompt_tokens=None,
        insights_total_completion_tokens=None,
        insights_total_duration_seconds=None,
        total_questions=0,
        model_used=None,
        total_prompt_tokens=None,
        total_completion_tokens=None,
        total_duration_seconds=None,
        metadata={},
    )


def state_summary(state: WorkflowState) -> dict[str, Any]:
    return {
        "transcript_id": str(state.get("transcript_id", "")),
        "meeting_id": str(state["meeting_id"]) if state.get("meeting_id") else None,
        "status": state.get("status", WorkflowStatus.PENDING).value
        if isinstance(state.get("status"), WorkflowStatus)
        else state.get("status"),
        "current_node": state.get("current_node", ""),
        "error": state.get("error"),
        "warnings": state.get("warnings", []),
        "chunks_loaded": state.get("chunks_loaded", 0),
        "questions_generated": state.get("questions_generated", 0),
        "questions_validated": state.get("questions_validated", 0),
        "duplicates_removed": state.get("duplicates_removed", 0),
        "questions_persisted": state.get("questions_persisted", 0),
        "total_questions": state.get("total_questions", 0),
        "learning_outputs_persisted": state.get("learning_outputs_persisted", 0),
        "insights_persisted": state.get("insights_persisted", False),
        "model_used": state.get("model_used"),
        "total_prompt_tokens": state.get("total_prompt_tokens"),
        "total_completion_tokens": state.get("total_completion_tokens"),
        "total_duration_seconds": state.get("total_duration_seconds"),
        "questions_model_used": state.get("questions_model_used"),
        "questions_total_prompt_tokens": state.get("questions_total_prompt_tokens"),
        "questions_total_completion_tokens": state.get("questions_total_completion_tokens"),
        "questions_total_duration_seconds": state.get("questions_total_duration_seconds"),
        "learning_model_used": state.get("learning_model_used"),
        "learning_total_prompt_tokens": state.get("learning_total_prompt_tokens"),
        "learning_total_completion_tokens": state.get("learning_total_completion_tokens"),
        "learning_total_duration_seconds": state.get("learning_total_duration_seconds"),
        "insights_model_used": state.get("insights_model_used"),
        "insights_total_prompt_tokens": state.get("insights_total_prompt_tokens"),
        "insights_total_completion_tokens": state.get("insights_total_completion_tokens"),
        "insights_total_duration_seconds": state.get("insights_total_duration_seconds"),
    }
