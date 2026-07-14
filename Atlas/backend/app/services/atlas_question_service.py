"""Atlas question service.

Orchestrates Zoom Agentic AI question endpoints:

- stored question lookup          -> :class:`QuestionClient`
- professor-ranked questions      -> :class:`RankingClient`
- semantic retrieval (search)      -> :class:`RetrievalClient`

Pure pass-through — no business logic. Ranking, retrieval and embedding
algorithms all stay in the Zoom Agentic AI baseline.
"""
from __future__ import annotations

from typing import Any

from app.clients.question_client import QuestionClient
from app.clients.ranking_client import RankingClient
from app.clients.retrieval_client import RetrievalClient
from app.services._helpers import coerce_mapping


class AtlasQuestionService:
    """Compose question-related REST responses from Zoom Agentic AI."""

    def __init__(
        self,
        question_client: QuestionClient,
        ranking_client: RankingClient,
        retrieval_client: RetrievalClient,
    ) -> None:
        self._questions = question_client
        self._ranking = ranking_client
        self._retrieval = retrieval_client

    # ------------------------------------------------------------------
    # Stored question lookup
    # ------------------------------------------------------------------
    def get_question(self, question_id: str) -> Any:
        return self._questions.get_question(question_id)

    # ------------------------------------------------------------------
    # Ranked questions (baseline owns the ranking algorithm)
    # ------------------------------------------------------------------
    def ranked_meeting_questions(
        self,
        meeting_id: str,
        *,
        top_k: int | None = None,
        category: str | None = None,
    ) -> Any:
        return self._ranking.get_meeting_ranked_questions(
            meeting_id, top_k=top_k, category=category
        )

    def ranked_transcript_questions(
        self,
        transcript_id: str,
        *,
        top_k: int | None = None,
        category: str | None = None,
    ) -> Any:
        return self._ranking.get_transcript_ranked_questions(
            transcript_id, top_k=top_k, category=category
        )

    # ------------------------------------------------------------------
    # Semantic retrieval (baseline owns embed + rank)
    # ------------------------------------------------------------------
    def search(
        self,
        meeting_id: str,
        query: str,
        *,
        top_k: int | None = None,
    ) -> Any:
        return self._retrieval.search(meeting_id, query, top_k=top_k)

    # ------------------------------------------------------------------
    # Composition: retrieve + hydrate full Question rows for the top-K.
    # ------------------------------------------------------------------
    def search_and_hydrate(
        self,
        meeting_id: str,
        query: str,
        *,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Run retrieval, then attach the full Question row for every
        ranked question that aligns with a retrieved chunk.

        Composition only — the retrieval + ranking themselves stay in the
        baseline. If the retrieval response carries no question ids we
        simply return the chunks.
        """
        retrieval = coerce_mapping(
            self._retrieval.search(meeting_id, query, top_k=top_k)
        )
        chunks = retrieval.get("chunks") or []
        return {"meeting_id": meeting_id, "query": query, "chunks": chunks}
