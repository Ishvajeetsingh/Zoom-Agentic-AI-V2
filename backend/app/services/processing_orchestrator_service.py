from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError, ExternalServiceError
from app.core.logging import get_logger
from app.db.models.learning_output import LearningOutput
from app.db.models.meeting_insights import MeetingInsights
from app.db.repositories import failures as failure_repo
from app.db.repositories import runs as run_repo
from app.db.repositories import transcripts as transcript_repo
from app.integrations.zoom.client import ZoomApiClient as LegacyZoomApiClient
from app.integrations.zoom.client_multi import get_zoom_api_client_from_db
from app.services.chunking_service import ChunkingError, ChunkingService
from app.services.learning_output_service import LearningOutputService
from app.services.meeting_insights_service import MeetingInsightsService
from app.services.preprocessing_service import PreprocessingService, WorkflowError
from app.services.transcript_cleaning_service import TranscriptCleaningError, TranscriptCleaningService
from app.services.docx_export_service import DocxExportError, DocxExportService
from app.services.classification_service import ClassificationService
from app.services.transcript_download_service import TranscriptDownloadError, TranscriptDownloadService
from app.services.transcript_parse_service import TranscriptParseError, TranscriptParseService

logger = get_logger(__name__)


class OrchestrationError(AppError):
    pass


@dataclass
class OrchestrationResult:
    run_id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None
    status: str
    steps_completed: int
    total_steps: int
    step_results: list[dict] = field(default_factory=list)
    questions_generated: int = 0
    model_used: str | None = None
    error_message: str | None = None
    total_duration_seconds: float | None = None


_DEGRADABLE_STEPS = {"generate_learning_outputs", "classify", "synthesize", "export_docx"}


class ProcessingOrchestratorService:
    def __init__(
        self,
        db: Session,
        *,
        zoom_client: LegacyZoomApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.config = config
        self.zoom_client = zoom_client or self._resolve_default_zoom_client()

    def process_transcript(
        self,
        transcript_id: uuid.UUID,
        *,
        existing_run_id: uuid.UUID | None = None,
    ) -> OrchestrationResult:
        transcript = transcript_repo.get_by_id(self.db, transcript_id)
        if transcript is None:
            raise OrchestrationError(f"Transcript not found: {transcript_id}")

        if existing_run_id is not None:
            run = run_repo.get_by_id(self.db, existing_run_id)
            if run is None:
                raise OrchestrationError(f"Processing run not found: {existing_run_id}")
            if run.status not in ("running", "queued", "pending"):
                raise OrchestrationError(
                    f"Processing run {existing_run_id} has status '{run.status}' – cannot process"
                )
            if run.status != "running":
                run_repo.mark_running(self.db, run)
                self.db.commit()
        else:
            run = run_repo.create_run(
                self.db,
                transcript_id=transcript.id,
                meeting_id=transcript.meeting_id,
            )
            run_repo.mark_running(self.db, run)
            self.db.commit()

        logger.info(
            "orchestrator.started",
            extra={"run_id": str(run.id), "transcript_id": str(transcript_id)},
        )

        try:
            self._execute_pipeline(transcript_id, run)
        except Exception as exc:
            self.db.rollback()
            run_after = run_repo.get_by_id(self.db, run.id)
            if run_after is not None:
                run_repo.mark_failed(self.db, run_after, error_message=str(exc))
                failure_repo.record_failure(
                    self.db,
                    run_id=run_after.id,
                    step=run_after.current_step or "pipeline",
                    error_message=str(exc),
                    error_type=type(exc).__name__,
                    retry_number=run_after.retry_count,
                )
                self.db.commit()
                run = run_after
            logger.exception(
                "orchestrator.failed",
                extra={"run_id": str(run.id), "transcript_id": str(transcript_id), "error": str(exc)},
            )
            raise OrchestrationError(str(exc)) from exc

        self.db.refresh(run)
        logger.info(
            "orchestrator.completed",
            extra={
                "run_id": str(run.id),
                "transcript_id": str(transcript_id),
                "status": run.status,
                "steps_completed": run.steps_completed,
            },
        )

        return OrchestrationResult(
            run_id=run.id,
            transcript_id=run.transcript_id,
            meeting_id=run.meeting_id,
            status=run.status,
            steps_completed=run.steps_completed,
            total_steps=run.total_steps,
            step_results=run.step_results or [],
            questions_generated=run.questions_generated,
            model_used=run.model_used,
            error_message=run.error_message,
            total_duration_seconds=run.total_duration_seconds,
        )

    def _execute_pipeline(self, transcript_id: uuid.UUID, run) -> None:
        steps = [
            ("download", self._step_download),
            ("parse", self._step_parse),
            ("clean", self._step_clean),
            ("chunk", self._step_chunk),
            ("generate", self._step_generate),
            ("generate_learning_outputs", self._step_generate_learning_outputs),
            ("classify", self._step_classify),
            ("synthesize", self._step_synthesize),
            ("export_docx", self._step_export_docx),
        ]

        for step_name, step_fn in steps:
            transcript = transcript_repo.get_by_id(self.db, transcript_id)
            if transcript is None:
                raise OrchestrationError(f"Transcript disappeared during pipeline: {transcript_id}")

            if not self._should_run_step(step_name, transcript.status):
                logger.info(
                    "orchestrator.skipping_step",
                    extra={
                        "run_id": str(run.id),
                        "step": step_name,
                        "transcript_status": transcript.status,
                    },
                )
                continue

            logger.info(
                "orchestrator.step_started",
                extra={"run_id": str(run.id), "step": step_name, "transcript_status": transcript.status},
            )

            try:
                result_data = step_fn(transcript_id)
                run_repo.mark_step_completed(self.db, run, step_name=step_name, result=result_data)
                self.db.commit()
            except Exception as exc:
                run_repo.mark_step_failed(self.db, run, step_name=step_name, error=str(exc))
                failure_repo.record_failure(
                    self.db,
                    run_id=run.id,
                    step=step_name,
                    error_message=str(exc),
                    error_type=type(exc).__name__,
                    retry_number=run.retry_count,
                )

                if step_name in _DEGRADABLE_STEPS:
                    current_transcript = transcript_repo.get_by_id(self.db, transcript_id)
                    if current_transcript is not None:
                        if step_name == "generate_learning_outputs":
                            transcript_repo.mark_learning_generation_failed(self.db, current_transcript, error_message=str(exc))
                        elif step_name == "synthesize":
                            transcript_repo.mark_synthesis_failed(self.db, current_transcript, error_message=str(exc))
                    self.db.commit()
                    logger.warning(
                        "orchestrator.degradable_step_failed_continuing",
                        extra={
                            "run_id": str(run.id),
                            "step": step_name,
                            "error": str(exc),
                        },
                    )
                else:
                    current_transcript = transcript_repo.get_by_id(self.db, transcript_id)
                    if current_transcript is not None:
                        if step_name == "generate_learning_outputs":
                            transcript_repo.mark_learning_generation_failed(self.db, current_transcript, error_message=str(exc))
                        elif step_name == "synthesize":
                            transcript_repo.mark_synthesis_failed(self.db, current_transcript, error_message=str(exc))
                    self.db.commit()
                    raise

        transcript = transcript_repo.get_by_id(self.db, transcript_id)
        if transcript and transcript.status == "synthesizing":
            question_count = transcript.question_count or 0
            model = transcript.generation_model
            run_repo.mark_completed(self.db, run, questions_generated=question_count, model_used=model)
            transcript_repo.mark_generation_completed(
                self.db, transcript,
                question_count=question_count,
                generation_model=model or self.config.ollama_primary_model,
            )
            self.db.commit()
        elif transcript and transcript.status in ("completed", "completed_with_warnings"):
            question_count = transcript.question_count or 0
            model = transcript.generation_model
            run_repo.mark_completed(self.db, run, questions_generated=question_count, model_used=model)
            self.db.commit()
        else:
            run_repo.mark_failed(
                self.db, run, error_message=f"Pipeline ended with transcript status: {transcript.status if transcript else 'unknown'}"
            )
            self.db.commit()

    def _should_run_step(self, step_name: str, transcript_status: str) -> bool:
        step_prerequisites = {
            "download": {"metadata_received", "failed", "download_started"},
            "parse": {"downloaded", "parsing_failed"},
            "clean": {"parsed", "cleaning_failed"},
            "chunk": {"cleaned", "chunking_failed"},
            "generate": {"chunked", "generation_failed"},
            "generate_learning_outputs": {"completed", "completed_with_warnings", "generating_learning_outputs", "learning_generation_failed"},
            "classify": {"completed", "completed_with_warnings", "generating_learning_outputs", "learning_generation_failed"},
            "synthesize": {"completed", "completed_with_warnings", "generating_learning_outputs", "synthesizing", "synthesis_failed"},
            "export_docx": {"completed", "completed_with_warnings"},
        }
        allowed = step_prerequisites.get(step_name, set())
        return transcript_status in allowed

    def _step_download(self, transcript_id: uuid.UUID) -> dict:
        zoom_client = self._resolve_zoom_client_for_transcript(transcript_id)
        service = TranscriptDownloadService(self.db, zoom_client=zoom_client, config=self.config)
        result = service.download_transcript(transcript_id)
        return {
            "transcript_filename": result.transcript_filename,
            "file_size_bytes": result.file_size_bytes,
            "checksum_sha256": result.checksum_sha256,
        }

    def _step_parse(self, transcript_id: uuid.UUID) -> dict:
        service = TranscriptParseService(self.db)
        result = service.parse_transcript(transcript_id)
        return {"segment_count": result.segment_count, "word_count": result.word_count}

    def _step_clean(self, transcript_id: uuid.UUID) -> dict:
        service = TranscriptCleaningService(self.db)
        result = service.clean_transcript(transcript_id)
        return {
            "segments_cleaned": result.segments_cleaned,
            "speakers_normalized": result.speakers_normalized,
            "total_fillers_removed": result.total_fillers_removed,
        }

    def _step_chunk(self, transcript_id: uuid.UUID) -> dict:
        service = ChunkingService(self.db)
        result = service.chunk_transcript(transcript_id)
        return {"total_chunks": result.total_chunks, "total_words": result.total_words}

    def _step_generate(self, transcript_id: uuid.UUID) -> dict:
        service = PreprocessingService(self.db, config=self.config)
        result = service.run_workflow(transcript_id)
        return {
            "total_questions": result.total_questions,
            "questions_persisted": result.questions_persisted,
            "model_used": result.model_used,
            "total_duration_seconds": result.total_duration_seconds,
        }

    def _step_generate_learning_outputs(self, transcript_id: uuid.UUID) -> dict:
        from app.db.models.transcript_chunk import TranscriptChunk

        transcript = transcript_repo.get_by_id(self.db, transcript_id)
        if transcript is None:
            raise OrchestrationError(f"Transcript not found: {transcript_id}")

        existing_count = self.db.scalar(
            select(func.count()).select_from(LearningOutput).where(
                LearningOutput.transcript_id == transcript_id
            )
        )
        if existing_count and existing_count > 0:
            transcript_repo.mark_generating_learning_outputs(self.db, transcript)
            self.db.commit()
            return {"learning_outputs_persisted": existing_count, "skipped_reason": "already_exists"}

        if transcript.meeting_id is None:
            transcript_repo.mark_generating_learning_outputs(self.db, transcript)
            self.db.commit()
            return {"learning_outputs_persisted": 0, "skipped_reason": "no_meeting_id"}

        chunks = self.db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == transcript_id)
            .order_by(TranscriptChunk.chunk_index)
        ).all()

        if not chunks:
            transcript_repo.mark_generating_learning_outputs(self.db, transcript)
            self.db.commit()
            return {"learning_outputs_persisted": 0, "skipped_reason": "no_chunks"}

        transcript_repo.mark_generating_learning_outputs(self.db, transcript)
        self.db.commit()

        service = LearningOutputService(config=self.config)
        from app.db.repositories import learning_outputs as learning_output_repo

        total_persisted = 0
        outputs: list[dict] = []

        for chunk in chunks:
            try:
                result = service.generate_from_chunk(
                    chunk_text=chunk.text,
                    chunk_id=chunk.chunk_id,
                    model=self.config.ollama_primary_model,
                )
                for fc in result.flashcards:
                    content = {"front": fc.front, "back": fc.back}
                    if fc.category:
                        content["category"] = fc.category
                    outputs.append({
                        "chunk_id": chunk.chunk_id,
                        "output_type": "flashcard",
                        "content": content,
                    })
                for sq in result.short_questions:
                    outputs.append({
                        "chunk_id": chunk.chunk_id,
                        "output_type": "short_question",
                        "content": {
                            "question_text": sq.question_text,
                            "sample_answer": sq.sample_answer,
                        },
                        "difficulty": sq.difficulty,
                    })
            except Exception as exc:
                logger.warning(
                    "orchestrator.learning_output_chunk_failed",
                    extra={
                        "transcript_id": str(transcript_id),
                        "chunk_index": chunk.chunk_index,
                        "error": str(exc),
                    },
                )

        if outputs:
            learning_output_repo.delete_by_transcript_id(self.db, transcript_id)
            total_persisted = learning_output_repo.bulk_insert(
                self.db,
                transcript_id=transcript_id,
                meeting_id=transcript.meeting_id,
                outputs=outputs,
            )
            self.db.commit()

        return {"learning_outputs_persisted": total_persisted}

    def _step_classify(self, transcript_id: uuid.UUID) -> dict:
        from app.db.models.question import Question
        from app.db.models.learning_output import LearningOutput
        from sqlalchemy import select, func as sa_func

        has_questions = self.db.scalar(
            select(sa_func.count()).select_from(Question).where(
                Question.transcript_id == transcript_id,
                Question.is_duplicate == False,
            )
        )
        has_lo = self.db.scalar(
            select(sa_func.count()).select_from(LearningOutput).where(
                LearningOutput.transcript_id == transcript_id,
            )
        )

        if not has_questions and not has_lo:
            return {"questions_classified": 0, "learning_outputs_classified": 0, "skipped_reason": "no_content"}

        service = ClassificationService(self.db)
        try:
            result = service.classify_transcript(transcript_id)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning(
                "orchestrator.classify_failed",
                extra={"transcript_id": str(transcript_id), "error": str(exc)},
            )
            return {"questions_classified": 0, "learning_outputs_classified": 0, "error": str(exc)}

        return result

    def _step_synthesize(self, transcript_id: uuid.UUID) -> dict:
        transcript = transcript_repo.get_by_id(self.db, transcript_id)
        if transcript is None:
            raise OrchestrationError(f"Transcript not found: {transcript_id}")

        existing = self.db.scalar(
            select(MeetingInsights).where(MeetingInsights.transcript_id == transcript_id)
        )
        if existing is not None:
            transcript_repo.mark_synthesizing(self.db, transcript)
            self.db.commit()
            return {"insights_persisted": True, "skipped_reason": "already_exists"}

        if transcript.meeting_id is None:
            transcript_repo.mark_synthesizing(self.db, transcript)
            self.db.commit()
            return {"insights_persisted": False, "skipped_reason": "no_meeting_id"}

        transcript_repo.mark_synthesizing(self.db, transcript)
        self.db.commit()

        service = MeetingInsightsService(self.db, config=self.config)

        try:
            result = service.synthesize(
                transcript_id=transcript_id,
                meeting_id=transcript.meeting_id,
                model=self.config.ollama_primary_model,
            )
        except Exception as exc:
            logger.exception(
                "orchestrator.synthesize_failed",
                extra={"transcript_id": str(transcript_id), "error": str(exc)},
            )
            return {"insights_persisted": False, "error": str(exc)}

        from app.db.repositories import meeting_insights as meeting_insights_repo

        try:
            meeting_insights_repo.upsert_insights(
                self.db,
                transcript_id=transcript_id,
                meeting_id=transcript.meeting_id,
                summary_text=result.summary_text,
                key_concepts=[
                    {"concept": kc.concept, "description": kc.description, "importance_order": kc.importance_order}
                    for kc in result.key_concepts
                ],
                action_items=[
                    {"item_text": ai.item_text, "assignee": ai.assignee, "priority": ai.priority, "due_date": ai.due_date}
                    for ai in result.action_items
                ],
                key_takeaways=[
                    {"takeaway": kt.takeaway, "context": kt.context}
                    for kt in result.key_takeaways
                ],
                learning_outcomes=[
                    {"outcome": lo.outcome, "category": lo.category}
                    for lo in result.learning_outcomes
                ],
                topics=[
                    {"topic": t.topic, "relevance": t.relevance}
                    for t in result.topics
                ],
                decisions=[
                    {"decision": d.decision, "rationale": d.rationale, "decided_by": d.decided_by}
                    for d in result.decisions
                ],
                recommendations=[
                    {"recommendation": r.recommendation, "priority": r.priority, "target_audience": r.target_audience}
                    for r in result.recommendations
                ],
                model_used=result.model_used,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_duration_seconds=result.total_duration_seconds,
            )
            self.db.commit()
        except Exception as exc:
            logger.exception(
                "orchestrator.insights_persist_failed",
                extra={"transcript_id": str(transcript_id), "error": str(exc)},
            )
            return {"insights_persisted": False, "error": str(exc)}

        return {
            "insights_persisted": True,
            "key_concepts_count": len(result.key_concepts),
            "action_items_count": len(result.action_items),
        }

    def _step_export_docx(self, transcript_id: uuid.UUID) -> dict:
        service = DocxExportService(self.db, config=self.config)
        file_path = service.generate_docx(transcript_id)
        return {"docx_path": str(file_path)}

    def _resolve_default_zoom_client(self):
        try:
            from app.integrations.zoom.client_multi import get_default_zoom_api_client
            client = get_default_zoom_api_client(self.db)
            if client is not None:
                return client
        except Exception:
            pass
        return LegacyZoomApiClient(config=self.config)

    def _resolve_zoom_client_for_transcript(self, transcript_id: uuid.UUID):
        transcript = transcript_repo.get_by_id(self.db, transcript_id)
        if transcript is not None and transcript.meeting_id is not None:
            from app.db.models.meeting import Meeting
            meeting = self.db.get(Meeting, transcript.meeting_id)
            if meeting is not None and meeting.zoom_account_id is not None:
                try:
                    return get_zoom_api_client_from_db(self.db, meeting.zoom_account_id)
                except Exception:
                    logger.warning(
                        "orchestrator.zoom_account_client_failed",
                        extra={"meeting_id": str(meeting.id), "zoom_account_id": str(meeting.zoom_account_id)},
                    )
        return self.zoom_client
