"""Intent Router for Atlas Educational Intelligence."""
from enum import Enum
import re


class AtlasIntent(Enum):
    SUMMARY = "summary"
    CONCEPT_EXPLANATION = "concept_explanation"
    QUIZ_REQUEST = "quiz_request"
    REVISION_REQUEST = "revision_request"
    ACTION_ITEMS = "action_items"
    DECISIONS = "decisions"
    RECOMMENDATIONS = "recommendations"
    GENERAL_QUESTION = "general_question"


# Simple keyword-based intent detection
_INTENT_KEYWORDS: dict[AtlasIntent, list[str]] = {
    AtlasIntent.SUMMARY: [
        "summarize", "summary", "overview", "brief", "recap", "what happened",
        "key points", "main points", "highlights",
    ],
    AtlasIntent.CONCEPT_EXPLANATION: [
        "explain", "what is", "what are", "how does", "why is", "definition",
        "clarify", "describe", "meaning of", "concept",
    ],
    AtlasIntent.QUIZ_REQUEST: [
        "quiz", "test me", "question me", "assess", "practice", "exercise",
        "generate quiz", "quiz me", "test my knowledge",
    ],
    AtlasIntent.REVISION_REQUEST: [
        "revise", "review", "study", "flashcard", "revision", "study guide",
        "help me study", "prepare for exam", "revision guide",
    ],
    AtlasIntent.ACTION_ITEMS: [
        "action item", "action items", "todo", "to-do", "tasks", "next steps",
        "what needs to be done", "who should", "responsibilities",
    ],
    AtlasIntent.DECISIONS: [
        "decision", "decisions", "decided", "concluded", "agreed", "consensus",
        "what was decided", "outcome",
    ],
    AtlasIntent.RECOMMENDATIONS: [
        "recommendation", "recommendations", "suggest", "advice", "proposed",
        "what should we do", "next recommendation",
    ],
}


def detect_intent(user_message: str) -> AtlasIntent:
    """Detect the user's intent from their message."""
    lower = user_message.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return intent
    return AtlasIntent.GENERAL_QUESTION
