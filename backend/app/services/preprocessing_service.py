"""Workflow orchestration service.

Wires the LangGraph QuestionGenerationWorkflow to the database
session and manages transcript status transitions around the
question generation pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from app.llm.provider import create_llm_client

from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.repositories import transcripts as transcript_repo
from app.integrations.ollama.client import OllamaApiClient
from app.services.question_service import QuestionService
from app.workflows.graph import QuestionGenerationWorkflow
from app.workflows.state import WorkflowStatus

logger = get_logger(__name__)


class WorkflowError(AppError):
    """Raised when the question generation workflow cannot be completed."""


@dataclass(frozen=True)
class WorkflowResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None
    status: str
    total_questions: int
    questions_persisted: int
    chunks_loaded: int
    questions_generated: int
    questions_validated: int
    duplicates_removed: int
    model_used: str | None = None
    total_prompt_tokens: int | None = None
    total_completion_tokens: int | None = None
    total_duration_seconds: float | None = None
    learning_outputs_persisted: int = 0
    insights_persisted: bool = False
    error: str | None = None
    warnings: tuple[str, ...] = ()


class PreprocessingService:
    def __init__(
        self,
        db: Session,
        *,
        ollama_client: OllamaApiClient | None = None,
        question_service: QuestionService | None = None,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.config = config
        self.ollama_client = ollama_client or create_llm_client(config)
        self.question_service = question_service or QuestionService(
            ollama_client=self.ollama_client,
            config=config,
        )

    def run_workflow(self, transcript_id: uuid.UUID) -> WorkflowResult:
        transcript = transcript_repo.get_by_id(self.db, transcript_id)
        if transcript is None:
            raise WorkflowError(f"Transcript not found: {transcript_id}")

        if transcript.status not in {"chunked", "generation_failed"}:
            raise WorkflowError(
                f"Transcript must be chunked before generation; current status is {transcript.status}"
            )

        transcript_repo.mark_generation_started(self.db, transcript)
        self.db.commit()

        logger.info(
            "workflow_service.started",
            extra={
                "transcript_id": str(transcript_id),
                "meeting_id": str(transcript.meeting_id),
            },
        )

        final_state = None
        workflow_error_msg: str | None = None

        try:
            workflow = QuestionGenerationWorkflow(
                db_session=self.db,
                question_service=self.question_service,
                ollama_client=self.ollama_client,
                config=self.config,
            )

            final_state = workflow.run(
                transcript_id=transcript.id,
                meeting_id=transcript.meeting_id,
            )

            workflow_status = final_state.get("status")
            warnings = final_state.get("warnings", [])

            if workflow_status == WorkflowStatus.FAILED:
                workflow_error_msg = final_state.get("error") or "Workflow ended in failure state without error message"
                raise WorkflowError(workflow_error_msg)

            if workflow_status == WorkflowStatus.COMPLETED_WITH_WARNINGS:
                transcript_repo.mark_generation_completed(
                    self.db,
                    transcript,
                    question_count=final_state.get("questions_persisted", 0),
                    generation_model=final_state.get("model_used") or self.config.ollama_primary_model,
                )
                self.db.commit()

                logger.info(
                    "workflow_service.completed_with_warnings",
                    extra={
                        "transcript_id": str(transcript_id),
                        "total_questions": final_state.get("total_questions", 0),
                        "warning_count": len(warnings),
                        "warnings": warnings,
                    },
                )
            else:
                transcript_repo.mark_generation_completed(
                    self.db,
                    transcript,
                    question_count=final_state.get("questions_persisted", 0),
                    generation_model=final_state.get("model_used") or self.config.ollama_primary_model,
                )
                self.db.commit()

        except WorkflowError as exc:
            workflow_error_msg = str(exc)
            self.db.rollback()
            transcript = transcript_repo.get_by_id(self.db, transcript_id)
            if transcript is not None:
                transcript_repo.mark_generation_failed(self.db, transcript, workflow_error_msg)
                self.db.commit()
            raise

        except Exception as exc:
            self.db.rollback()
            transcript = transcript_repo.get_by_id(self.db, transcript_id)
            if transcript is not None:
                transcript_repo.mark_generation_failed(self.db, transcript, str(exc))
                self.db.commit()
            logger.exception(
                "workflow_service.failed",
                extra={
                    "transcript_id": str(transcript_id),
                    "error": str(exc),
                },
            )
            raise WorkflowError(str(exc)) from exc

        logger.info(
            "workflow_service.completed",
            extra={
                "transcript_id": str(transcript_id),
                "total_questions": final_state.get("total_questions", 0),
                "model_used": final_state.get("model_used"),
            },
        )

        final_status = transcript.status
        if final_state.get("status") == WorkflowStatus.COMPLETED_WITH_WARNINGS:
            final_status = "completed_with_warnings"

        return WorkflowResult(
            transcript_id=transcript.id,
            meeting_id=transcript.meeting_id,
            status=final_status,
            total_questions=final_state.get("total_questions", 0),
            questions_persisted=final_state.get("questions_persisted", 0),
            chunks_loaded=final_state.get("chunks_loaded", 0),
            questions_generated=final_state.get("questions_generated", 0),
            questions_validated=final_state.get("questions_validated", 0),
            duplicates_removed=final_state.get("duplicates_removed", 0),
            model_used=final_state.get("model_used"),
            total_prompt_tokens=final_state.get("total_prompt_tokens"),
            total_completion_tokens=final_state.get("total_completion_tokens"),
            total_duration_seconds=final_state.get("total_duration_seconds"),
            learning_outputs_persisted=final_state.get("learning_outputs_persisted", 0),
            insights_persisted=final_state.get("insights_persisted", False),
            warnings=final_state.get("warnings", []),
        )
