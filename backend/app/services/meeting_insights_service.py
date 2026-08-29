"""Meeting insights synthesis service.

Generates meeting-level summary, key concepts, and action items
from the full transcript (all chunks concatenated) using a single LLM call.
"""

from __future__ import annotations
from app.llm.provider import create_llm_client, get_generation_model
import json
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.transcript_chunk import TranscriptChunk
from app.integrations.ollama.client import (
    GenerationResponse,
    OllamaApiClient,
    OllamaConnectionError,
    OllamaGenerateError,
    OllamaModelError,
)

logger = get_logger(__name__)

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINKING_RE = re.compile(rf"^{re.escape(_THINK_OPEN)}.*?{re.escape(_THINK_CLOSE)}", re.DOTALL)


class MeetingInsightsError(AppError):
    pass


@dataclass(frozen=True)
class KeyConceptData:
    concept: str
    description: str
    importance_order: int


@dataclass(frozen=True)
class ActionItemData:
    item_text: str
    assignee: str | None = None
    priority: str | None = None
    due_date: str | None = None


@dataclass(frozen=True)
class KeyTakeawayData:
    takeaway: str
    context: str | None = None


@dataclass(frozen=True)
class LearningOutcomeData:
    outcome: str
    category: str | None = None


@dataclass(frozen=True)
class TopicData:
    topic: str
    relevance: str | None = None


@dataclass(frozen=True)
class DecisionData:
    decision: str
    rationale: str | None = None
    decided_by: str | None = None


@dataclass(frozen=True)
class RecommendationData:
    recommendation: str
    priority: str | None = None
    target_audience: str | None = None


@dataclass(frozen=True)
class MeetingInsightsResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None
    summary_text: str
    key_concepts: list[KeyConceptData]
    action_items: list[ActionItemData]
    key_takeaways: list[KeyTakeawayData]
    learning_outcomes: list[LearningOutcomeData]
    topics: list[TopicData]
    decisions: list[DecisionData]
    recommendations: list[RecommendationData]
    model_used: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_duration_seconds: float | None = None


MEETING_INSIGHTS_SYSTEM_PROMPT = """You are an expert meeting analyst. Given the full transcript of a meeting, produce a comprehensive analysis with all of the following sections.

Rules:
- The summary should capture the main topics discussed, decisions made, and outcomes. Write 3-5 paragraphs.
- Key concepts should be the most important ideas, terms, or topics discussed. Order by importance (1 = most important). Provide 5-10 concepts.
- Action items should be concrete tasks, follow-ups, or commitments mentioned. Include assignee if mentioned, priority (low/medium/high), and due date if mentioned.
- Key takeaways should be the most important points or conclusions from the meeting that participants should remember.
- Learning outcomes should be what knowledge or skills were gained or reinforced by participants.
- Topics should list the main subjects or themes discussed in the meeting with a brief note on relevance.
- Decisions should capture any decisions that were made during the meeting, who decided, and the rationale.
- Recommendations should be suggestions or advice emerging from the discussion with priority level.
- Do NOT invent information not present in the transcript.
- Return a JSON object with eight keys.

JSON schema:
{
  "summary": "string (3-5 paragraphs)",
  "key_concepts": [
    {"concept": "string", "description": "string", "importance_order": 1}
  ],
  "action_items": [
    {"item_text": "string", "assignee": "string or null", "priority": "low|medium|high or null", "due_date": "string or null"}
  ],
  "key_takeaways": [
    {"takeaway": "string", "context": "string or null"}
  ],
  "learning_outcomes": [
    {"outcome": "string", "category": "string or null"}
  ],
  "topics": [
    {"topic": "string", "relevance": "string or null"}
  ],
  "decisions": [
    {"decision": "string", "rationale": "string or null", "decided_by": "string or null"}
  ],
  "recommendations": [
    {"recommendation": "string", "priority": "low|medium|high or null", "target_audience": "string or null"}
  ]
}"""


class MeetingInsightsService:
    def __init__(
        self,
        db: Session,
        *,
        ollama_client: OllamaApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.db = db
        self.config = config
        self.ollama = ollama_client or create_llm_client(config)

    def synthesize(
        self,
        transcript_id: uuid.UUID,
        meeting_id: uuid.UUID | None = None,
        *,
        model: str | None = None,
    ) -> MeetingInsightsResult:
        chunks_text = self._load_chunks_text(transcript_id)
        if not chunks_text:
            raise MeetingInsightsError(
                f"No chunks found for transcript {transcript_id}"
            )

        prompt = (
            f"Analyze the following meeting transcript and produce a summary, "
            f"key concepts, action items, key takeaways, learning outcomes, "
            f"topics, decisions, and recommendations.\n\n"
            f"--- FULL MEETING TRANSCRIPT ---\n{chunks_text}\n--- END TRANSCRIPT ---\n\n"
            f"Return a JSON object with 'summary', 'key_concepts', 'action_items', "
            f"'key_takeaways', 'learning_outcomes', 'topics', 'decisions', and 'recommendations'."
        )

        logger.info(
            "meeting_insights.synthesis_started",
            extra={
                "transcript_id": str(transcript_id),
                "input_length": len(chunks_text),
            },
        )

        try:
            response = self.ollama.generate_json(
                prompt,
                model=model or get_generation_model(self.config),
                system=MEETING_INSIGHTS_SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=self.config.synthesize_max_output_tokens,
            )
        except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
            logger.exception(
                "meeting_insights.llm_failed",
                extra={
                    "transcript_id": str(transcript_id),
                    "error": str(exc),
                },
            )
            raise MeetingInsightsError(f"LLM synthesis failed: {exc}") from exc

        result = self._parse_response(response, transcript_id, meeting_id)

        logger.info(
            "meeting_insights.synthesis_completed",
            extra={
                "transcript_id": str(transcript_id),
                "key_concepts_count": len(result.key_concepts),
                "action_items_count": len(result.action_items),
                "key_takeaways_count": len(result.key_takeaways),
                "learning_outcomes_count": len(result.learning_outcomes),
                "topics_count": len(result.topics),
                "decisions_count": len(result.decisions),
                "recommendations_count": len(result.recommendations),
                "summary_length": len(result.summary_text),
                "model_used": result.model_used,
            },
        )

        return result

    def _load_chunks_text(self, transcript_id: uuid.UUID) -> str:
        rows = self.db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == transcript_id)
            .order_by(TranscriptChunk.chunk_index)
        ).all()

        if not rows:
            return ""

        parts = []
        total_tokens_estimate = 0
        max_tokens = self.config.synthesize_max_input_tokens

        for row in rows:
            chunk_text = row.text or ""
            chunk_token_estimate = len(chunk_text.split()) * 2
            if total_tokens_estimate + chunk_token_estimate > max_tokens:
                logger.info(
                    "meeting_insights.truncating_chunks",
                    extra={
                        "transcript_id": str(transcript_id),
                        "chunks_included": len(parts),
                        "total_chunks": len(rows),
                    },
                )
                break
            parts.append(chunk_text)
            total_tokens_estimate += chunk_token_estimate

        return "\n\n".join(parts)

    def _parse_response(
        self,
        response: GenerationResponse,
        transcript_id: uuid.UUID,
        meeting_id: uuid.UUID | None,
    ) -> MeetingInsightsResult:
        raw = response.response.strip()
        if not raw:
            raise MeetingInsightsError("LLM returned empty response for meeting insights")

        cleaned = _THINKING_RE.sub("", raw).strip()

        data = self._parse_json_response(cleaned)
        if data is None or not isinstance(data, dict):
            raise MeetingInsightsError(
                f"Failed to parse meeting insights JSON. Preview: {cleaned[:300]}"
            )

        summary_text = str(data.get("summary", "")).strip()
        if not summary_text:
            raise MeetingInsightsError("LLM returned empty summary")

        key_concepts = self._parse_key_concepts(data.get("key_concepts", []))
        action_items = self._parse_action_items(data.get("action_items", []))
        key_takeaways = self._parse_key_takeaways(data.get("key_takeaways", []))
        learning_outcomes = self._parse_learning_outcomes(data.get("learning_outcomes", []))
        topics = self._parse_topics(data.get("topics", []))
        decisions = self._parse_decisions(data.get("decisions", []))
        recommendations = self._parse_recommendations(data.get("recommendations", []))

        return MeetingInsightsResult(
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            summary_text=summary_text,
            key_concepts=key_concepts,
            action_items=action_items,
            key_takeaways=key_takeaways,
            learning_outcomes=learning_outcomes,
            topics=topics,
            decisions=decisions,
            recommendations=recommendations,
            model_used=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_duration_seconds=response.total_duration_seconds,
        )

    @staticmethod
    def _parse_key_concepts(items: list) -> list[KeyConceptData]:
        result: list[KeyConceptData] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            concept = str(item.get("concept", "")).strip()
            description = str(item.get("description", "")).strip()
            if not concept:
                continue
            importance = item.get("importance_order", len(result) + 1)
            try:
                importance = int(importance)
            except (ValueError, TypeError):
                importance = len(result) + 1
            result.append(
                KeyConceptData(
                    concept=concept,
                    description=description,
                    importance_order=importance,
                )
            )
        return sorted(result, key=lambda x: x.importance_order)

    @staticmethod
    def _parse_action_items(items: list) -> list[ActionItemData]:
        result: list[ActionItemData] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_text = str(item.get("item_text", "")).strip()
            if not item_text:
                continue
            assignee = item.get("assignee")
            if assignee is not None:
                assignee = str(assignee).strip() or None
            priority = item.get("priority")
            if priority is not None:
                priority = str(priority).strip().lower()
                if priority not in ("low", "medium", "high"):
                    priority = None
            due_date = item.get("due_date")
            if due_date is not None:
                due_date = str(due_date).strip() or None
            result.append(
                ActionItemData(
                    item_text=item_text,
                    assignee=assignee,
                    priority=priority,
                    due_date=due_date,
                )
            )
        return result

    @staticmethod
    def _parse_key_takeaways(items: list) -> list[KeyTakeawayData]:
        result: list[KeyTakeawayData] = []
        for item in items:
            if isinstance(item, str):
                val = item.strip()
                if val:
                    result.append(KeyTakeawayData(takeaway=val, context=None))
                continue
            if not isinstance(item, dict):
                continue
            takeaway = str(item.get("takeaway", "")).strip()
            if not takeaway:
                continue
            context = item.get("context")
            if context is not None:
                context = str(context).strip() or None
            result.append(KeyTakeawayData(takeaway=takeaway, context=context))
        return result

    @staticmethod
    def _parse_learning_outcomes(items: list) -> list[LearningOutcomeData]:
        result: list[LearningOutcomeData] = []
        for item in items:
            if isinstance(item, str):
                val = item.strip()
                if val:
                    result.append(LearningOutcomeData(outcome=val, category=None))
                continue
            if not isinstance(item, dict):
                continue
            outcome = str(item.get("outcome", "")).strip()
            if not outcome:
                continue
            category = item.get("category")
            if category is not None:
                category = str(category).strip() or None
            result.append(LearningOutcomeData(outcome=outcome, category=category))
        return result

    @staticmethod
    def _parse_topics(items: list) -> list[TopicData]:
        result: list[TopicData] = []
        for item in items:
            if isinstance(item, str):
                val = item.strip()
                if val:
                    result.append(TopicData(topic=val, relevance=None))
                continue
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue
            relevance = item.get("relevance")
            if relevance is not None:
                relevance = str(relevance).strip() or None
            result.append(TopicData(topic=topic, relevance=relevance))
        return result

    @staticmethod
    def _parse_decisions(items: list) -> list[DecisionData]:
        result: list[DecisionData] = []
        for item in items:
            if isinstance(item, str):
                val = item.strip()
                if val:
                    result.append(DecisionData(decision=val, rationale=None, decided_by=None))
                continue
            if not isinstance(item, dict):
                continue
            decision = str(item.get("decision", "")).strip()
            if not decision:
                continue
            rationale = item.get("rationale")
            if rationale is not None:
                rationale = str(rationale).strip() or None
            decided_by = item.get("decided_by")
            if decided_by is not None:
                decided_by = str(decided_by).strip() or None
            result.append(DecisionData(decision=decision, rationale=rationale, decided_by=decided_by))
        return result

    @staticmethod
    def _parse_recommendations(items: list) -> list[RecommendationData]:
        result: list[RecommendationData] = []
        for item in items:
            if isinstance(item, str):
                val = item.strip()
                if val:
                    result.append(RecommendationData(recommendation=val, priority=None, target_audience=None))
                continue
            if not isinstance(item, dict):
                continue
            recommendation = str(item.get("recommendation", "")).strip()
            if not recommendation:
                continue
            priority = item.get("priority")
            if priority is not None:
                priority = str(priority).strip().lower()
                if priority not in ("low", "medium", "high"):
                    priority = None
            target_audience = item.get("target_audience")
            if target_audience is not None:
                target_audience = str(target_audience).strip() or None
            result.append(RecommendationData(recommendation=recommendation, priority=priority, target_audience=target_audience))
        return result

    @staticmethod
    def _parse_json_response(text: str) -> dict | list | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        return MeetingInsightsService._extract_balanced_json(text)

    @staticmethod
    def _extract_balanced_json(text: str) -> dict | list | None:
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            pos = 0
            while True:
                idx = text.find(start_char, pos)
                if idx == -1:
                    break
                depth = 0
                in_string = False
                escape_next = False
                end_idx = -1
                for i in range(idx, len(text)):
                    ch = text[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if ch == "\\" and in_string:
                        escape_next = True
                        continue
                    if ch == '"':
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if ch == start_char:
                        depth += 1
                    elif ch == end_char:
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
                if end_idx != -1:
                    candidate = text[idx:end_idx]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                pos = idx + 1
        return None
