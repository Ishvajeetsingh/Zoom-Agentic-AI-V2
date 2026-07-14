"""Atlas service layer.

Services here are pure orchestration over the typed HTTP clients in
``app.clients``. They contain no business logic, no AI logic, no ranking /
retrieval / embedding logic: every method composes REST responses that the
Zoom Agentic AI baseline already computes.

Dependency wiring lives in :mod:`app.services.container` (one place to
instantiate clients + services with shared configuration).
"""
from app.services.atlas_chat_service import AtlasChatService
from app.services.atlas_conversation_service import AtlasConversationService
from app.services.atlas_meeting_service import AtlasMeetingService
from app.services.atlas_question_service import AtlasQuestionService
from app.services.atlas_transcript_service import AtlasTranscriptService
from app.services.container import (
    AtlasServiceContainer,
    get_container,
    reset_container,
)

__all__ = [
    "AtlasChatService",
    "AtlasConversationService",
    "AtlasMeetingService",
    "AtlasQuestionService",
    "AtlasServiceContainer",
    "AtlasTranscriptService",
    "get_container",
    "reset_container",
]
