"""Dependency-injection container for the standalone Atlas backend.

One place constructs the entire client + service graph from shared
:class:`Settings`. API routes obtain services through :func:`get_container`
(which FastAPI can ``Depends`` on) so there is exactly one wiring site and
no service ever imports another service's constructor dependencies.

The container is process-wide (single instance). Tests can call
:func:`reset_container` to drop the cached instance after monkey-patching
the environment or the client classes.
"""
from __future__ import annotations

from app.clients.atlas_client import AtlasClient
from app.clients.base_http_client import BaseHTTPClient
from app.clients.insights_client import InsightsClient
from app.clients.meeting_client import MeetingClient
from app.clients.question_client import QuestionClient
from app.clients.ranking_client import RankingClient
from app.clients.retrieval_client import RetrievalClient
from app.clients.transcript_client import TranscriptClient
from app.core.config.settings import Settings, get_settings
from app.core.logging import get_logger
from app.services.atlas_chat_service import AtlasChatService
from app.services.atlas_conversation_service import AtlasConversationService
from app.services.atlas_meeting_service import AtlasMeetingService
from app.services.atlas_question_service import AtlasQuestionService
from app.services.atlas_transcript_service import AtlasTranscriptService

logger = get_logger(__name__)


class AtlasServiceContainer:
    """Owns one instance of every HTTP client and every service.

    All clients share the same :class:`Settings` (base URL, timeout, auth,
    retry policy) but each gets its own ``requests.Session`` unless one is
    explicitly injected (useful for tests that want to mock the transport).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        # Optional pre-built clients (primarily for tests). When None, the
        # container constructs the standard client wired to ``settings``.
        atlas_client: AtlasClient | None = None,
        meeting_client: MeetingClient | None = None,
        transcript_client: TranscriptClient | None = None,
        insights_client: InsightsClient | None = None,
        question_client: QuestionClient | None = None,
        ranking_client: RankingClient | None = None,
        retrieval_client: RetrievalClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()

        # ------------------------------------------------------------------
        # HTTP clients (one per Zoom Agentic AI REST surface).
        # ------------------------------------------------------------------
        self.atlas_client = atlas_client or AtlasClient(settings=self.settings)
        self.meeting_client = meeting_client or MeetingClient(settings=self.settings)
        self.transcript_client = (
            transcript_client or TranscriptClient(settings=self.settings)
        )
        self.insights_client = (
            insights_client or InsightsClient(settings=self.settings)
        )
        self.question_client = (
            question_client or QuestionClient(settings=self.settings)
        )
        self.ranking_client = (
            ranking_client or RankingClient(settings=self.settings)
        )
        self.retrieval_client = (
            retrieval_client or RetrievalClient(settings=self.settings)
        )

        # ------------------------------------------------------------------
        # Services (orchestration only — no business logic).
        # ------------------------------------------------------------------
        self.atlas_chat_service = AtlasChatService(self.atlas_client)
        self.atlas_conversation_service = AtlasConversationService(
            self.atlas_client
        )
        self.atlas_meeting_service = AtlasMeetingService(self.meeting_client)
        self.atlas_question_service = AtlasQuestionService(
            question_client=self.question_client,
            ranking_client=self.ranking_client,
            retrieval_client=self.retrieval_client,
        )
        self.atlas_transcript_service = AtlasTranscriptService(
            transcript_client=self.transcript_client,
            insights_client=self.insights_client,
        )

    # ------------------------------------------------------------------
    # Convenience accessors — API routes will ``Depends`` on these.
    # ------------------------------------------------------------------
    def chat_service(self) -> AtlasChatService:
        return self.atlas_chat_service

    def conversation_service(self) -> AtlasConversationService:
        return self.atlas_conversation_service

    def meeting_service(self) -> AtlasMeetingService:
        return self.atlas_meeting_service

    def question_service(self) -> AtlasQuestionService:
        return self.atlas_question_service

    def transcript_service(self) -> AtlasTranscriptService:
        return self.atlas_transcript_service

    def close(self) -> None:
        """Release any underlying HTTP sessions held by the clients."""
        for client in (
            self.atlas_client,
            self.meeting_client,
            self.transcript_client,
            self.insights_client,
            self.question_client,
            self.ranking_client,
            self.retrieval_client,
        ):
            session = getattr(client, "_session", None)
            close = getattr(session, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - best-effort teardown
                    logger.debug("atlas_container.session_close_failed")


# ---------------------------------------------------------------------------
# Process-wide singleton accessor (use this from FastAPI ``Depends``).
# ---------------------------------------------------------------------------
_container: AtlasServiceContainer | None = None


def get_container() -> AtlasServiceContainer:
    """Return the process-wide :class:`AtlasServiceContainer`.

    FastAPI route providers should ``Depends`` on this to obtain any
    service. The container is constructed lazily on first use so that
    importing this module has no side effects.
    """
    global _container
    if _container is None:
        _container = AtlasServiceContainer()
    return _container


def reset_container() -> None:
    """Drop the cached container.

    Intended for tests that change the environment or swap in mock clients.
    Also closes any HTTP sessions held by the previous container.
    """
    global _container
    if _container is not None:
        _container.close()
    _container = None


# Re-exported here so ``from app.services import ...`` is a single import.
__all__ = [
    "AtlasServiceContainer",
    "get_container",
    "reset_container",
]
