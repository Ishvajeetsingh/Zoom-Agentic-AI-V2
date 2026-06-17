from __future__ import annotations

import uuid
from langgraph.graph import END, StateGraph

from app.core.config import Settings, settings
from app.core.logging import get_logger
from app.integrations.ollama.client import OllamaApiClient
from app.services.question_service import QuestionService
from app.services.learning_output_service import LearningOutputService
from app.services.meeting_insights_service import MeetingInsightsService
from app.workflows.nodes import (
    assess_content_node,
    deduplicate_questions_node,
    finalize_node,
    generate_learning_outputs_node,
    generate_questions_node,
    handle_failure_node,
    load_chunks_node,
    persist_learning_outputs_node,
    persist_meeting_insights_node,
    persist_questions_node,
    synthesize_meeting_insights_node,
    validate_learning_outputs_node,
    validate_questions_node,
)
from app.workflows.state import (
    WorkflowState,
    WorkflowStatus,
    make_initial_state,
    state_summary,
)

logger = get_logger(__name__)


def _should_continue_after_load(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "assess_content"


def _should_continue_after_assess(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "generate_questions"


def _should_continue_after_generate(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    if not state.get("questions_raw") and not state.get("warnings"):
        return "handle_failure"
    return "validate_questions"


def _should_continue_after_validate(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    if not state.get("questions_valid"):
        return "generate_learning_outputs"
    return "deduplicate"


def _should_continue_after_dedup(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "persist_questions"


def _should_continue_after_persist(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "generate_learning_outputs"


def _should_continue_after_learning_gen(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "validate_learning_outputs"


def _should_continue_after_learning_validate(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "persist_learning_outputs"


def _should_continue_after_learning_persist(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "synthesize_meeting_insights"


def _should_continue_after_synthesize(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "persist_meeting_insights"


def _should_continue_after_insights_persist(state: WorkflowState) -> str:
    if state.get("status") == WorkflowStatus.FAILED:
        return "handle_failure"
    return "finalize"


class QuestionGenerationWorkflow:
    def __init__(
        self,
        *,
        db_session=None,
        question_service: QuestionService | None = None,
        ollama_client: OllamaApiClient | None = None,
        config: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.config = config or settings
        self.ollama_client = ollama_client or OllamaApiClient(config=self.config)
        self.question_service = question_service or QuestionService(
            ollama_client=self.ollama_client,
            config=self.config,
        )
        self.learning_service = LearningOutputService(
            ollama_client=self.ollama_client,
            config=self.config,
        )
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(WorkflowState)

        graph.add_node(
            "load_chunks",
            lambda state: load_chunks_node(state, db_session=self.db_session),
        )
        graph.add_node(
            "assess_content",
            lambda state: assess_content_node(state, db_session=self.db_session),
        )
        graph.add_node(
            "generate_questions",
            lambda state: generate_questions_node(
                state,
                question_service=self.question_service,
                config=self.config,
            ),
        )
        graph.add_node(
            "validate_questions",
            lambda state: validate_questions_node(state, config=self.config),
        )
        graph.add_node("deduplicate", deduplicate_questions_node)
        graph.add_node(
            "persist_questions",
            lambda state: persist_questions_node(state, db_session=self.db_session),
        )
        graph.add_node(
            "generate_learning_outputs",
            lambda state: generate_learning_outputs_node(
                state,
                learning_service=self.learning_service,
                config=self.config,
            ),
        )
        graph.add_node(
            "validate_learning_outputs",
            lambda state: validate_learning_outputs_node(state, config=self.config),
        )
        graph.add_node(
            "persist_learning_outputs",
            lambda state: persist_learning_outputs_node(state, db_session=self.db_session),
        )
        graph.add_node(
            "synthesize_meeting_insights",
            lambda state: synthesize_meeting_insights_node(
                state,
                db_session=self.db_session,
                insights_service=None,
                config=self.config,
            ),
        )
        graph.add_node(
            "persist_meeting_insights",
            lambda state: persist_meeting_insights_node(state, db_session=self.db_session),
        )
        graph.add_node("finalize", finalize_node)
        graph.add_node("handle_failure", handle_failure_node)

        graph.set_entry_point("load_chunks")

        graph.add_conditional_edges(
            "load_chunks",
            _should_continue_after_load,
            {
                "assess_content": "assess_content",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "assess_content",
            _should_continue_after_assess,
            {
                "generate_questions": "generate_questions",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "generate_questions",
            _should_continue_after_generate,
            {
                "validate_questions": "validate_questions",
                "generate_learning_outputs": "generate_learning_outputs",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "validate_questions",
            _should_continue_after_validate,
            {
                "deduplicate": "deduplicate",
                "generate_learning_outputs": "generate_learning_outputs",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "deduplicate",
            _should_continue_after_dedup,
            {
                "persist_questions": "persist_questions",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "persist_questions",
            _should_continue_after_persist,
            {
                "generate_learning_outputs": "generate_learning_outputs",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "generate_learning_outputs",
            _should_continue_after_learning_gen,
            {
                "validate_learning_outputs": "validate_learning_outputs",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "validate_learning_outputs",
            _should_continue_after_learning_validate,
            {
                "persist_learning_outputs": "persist_learning_outputs",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "persist_learning_outputs",
            _should_continue_after_learning_persist,
            {
                "synthesize_meeting_insights": "synthesize_meeting_insights",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "synthesize_meeting_insights",
            _should_continue_after_synthesize,
            {
                "persist_meeting_insights": "persist_meeting_insights",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_conditional_edges(
            "persist_meeting_insights",
            _should_continue_after_insights_persist,
            {
                "finalize": "finalize",
                "handle_failure": "handle_failure",
            },
        )

        graph.add_edge("finalize", END)
        graph.add_edge("handle_failure", END)

        return graph

    def compile(self):
        return self._graph.compile()

    def run(
        self,
        transcript_id: uuid.UUID,
        meeting_id: uuid.UUID | None = None,
    ) -> WorkflowState:
        initial_state = make_initial_state(transcript_id, meeting_id)

        logger.info(
            "workflow.run.started",
            extra={
                "transcript_id": str(transcript_id),
                "meeting_id": str(meeting_id) if meeting_id else None,
            },
        )

        compiled = self.compile()
        final_state: WorkflowState = compiled.invoke(initial_state)

        logger.info(
            "workflow.run.completed",
            extra={
                "transcript_id": str(transcript_id),
                **state_summary(final_state),
            },
        )

        return final_state
