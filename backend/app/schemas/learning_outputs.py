"""Meeting insights and learning output API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class KeyConceptItem(BaseModel):
    concept: str
    description: str
    importance_order: int


class ActionItemItem(BaseModel):
    item_text: str
    assignee: str | None = None
    priority: str | None = None
    due_date: str | None = None


class KeyTakeawayItem(BaseModel):
    takeaway: str
    context: str | None = None


class LearningOutcomeItem(BaseModel):
    outcome: str
    category: str | None = None


class TopicItem(BaseModel):
    topic: str
    relevance: str | None = None


class DecisionItem(BaseModel):
    decision: str
    rationale: str | None = None
    decided_by: str | None = None


class RecommendationItem(BaseModel):
    recommendation: str
    priority: str | None = None
    target_audience: str | None = None


class MeetingInsightsOut(BaseModel):
    id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    summary_text: str
    key_concepts: list[KeyConceptItem]
    action_items: list[ActionItemItem]
    key_takeaways: list[KeyTakeawayItem]
    learning_outcomes: list[LearningOutcomeItem]
    topics: list[TopicItem]
    decisions: list[DecisionItem]
    recommendations: list[RecommendationItem]
    model_used: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_duration_seconds: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SummaryOut(BaseModel):
    transcript_id: uuid.UUID
    summary_text: str
    model_used: str | None = None


class KeyConceptsOut(BaseModel):
    transcript_id: uuid.UUID
    key_concepts: list[KeyConceptItem]


class ActionItemsOut(BaseModel):
    transcript_id: uuid.UUID
    action_items: list[ActionItemItem]


class KeyTakeawaysOut(BaseModel):
    transcript_id: uuid.UUID
    key_takeaways: list[KeyTakeawayItem]


class LearningOutcomesOut(BaseModel):
    transcript_id: uuid.UUID
    learning_outcomes: list[LearningOutcomeItem]


class TopicsOut(BaseModel):
    transcript_id: uuid.UUID
    topics: list[TopicItem]


class DecisionsOut(BaseModel):
    transcript_id: uuid.UUID
    decisions: list[DecisionItem]


class RecommendationsOut(BaseModel):
    transcript_id: uuid.UUID
    recommendations: list[RecommendationItem]


class FullInsightsOut(BaseModel):
    transcript_id: uuid.UUID
    summary_text: str
    model_used: str | None = None
    key_concepts: list[KeyConceptItem]
    action_items: list[ActionItemItem]
    key_takeaways: list[KeyTakeawayItem]
    learning_outcomes: list[LearningOutcomeItem]
    topics: list[TopicItem]
    decisions: list[DecisionItem]
    recommendations: list[RecommendationItem]


class LearningOutputItem(BaseModel):
    id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    output_type: str
    content: dict
    difficulty: str | None = None
    category: str | None = None
    bloom_taxonomy: str | None = None
    educational_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LearningOutputListOut(BaseModel):
    items: list[LearningOutputItem]
    total: int
    offset: int
    limit: int


class OutputCountItem(BaseModel):
    output_type: str
    count: int


class OutputCountsOut(BaseModel):
    transcript_id: uuid.UUID
    counts: list[OutputCountItem]
