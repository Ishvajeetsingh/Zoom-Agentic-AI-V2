"""Post-generation classification service.

Classifies already-generated MCQs, short questions, and flashcards
by adding category, bloom_taxonomy, and scoring metadata.
Does NOT regenerate or modify existing content — only adds metadata.
"""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import Float, String, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.logging import get_logger
from app.db.models.learning_output import LearningOutput
from app.db.models.question import Question

logger = get_logger(__name__)

MCQ_CATEGORIES = ("quiz", "concept", "application", "meeting")
SQ_CATEGORIES = ("concept", "application", "meeting")
FC_CATEGORIES = ("core_concept", "definition", "important_term", "revision")
MCQ_BLOOM = ("remember", "understand", "apply", "analyze")
SQ_BLOOM = ("understand", "apply", "analyze")
FC_DIFFICULTY_MAP = {"easy": "easy", "medium": "medium", "hard": "hard"}

_APPLICATION_KEYWORDS = frozenset({
    "how would", "how could", "how might", "how should", "how do you use",
    "apply", "implement", "design", "create", "build", "solve", "use case",
    "scenario", "practical", "real-world", "in practice", "example of using",
    "what would happen if", "what if", "imagine", "suppose",
})

_CONCEPT_KEYWORDS = frozenset({
    "explain", "describe", "what is", "what are", "define", "meaning of",
    "difference between", "purpose of", "why does", "how does", "concept",
    "principle", "theory", "mechanism", "understand", "compare",
})

_MEETING_KEYWORDS = frozenset({
    "meeting", "discussed", "agreed", "decided", "action item", "follow-up",
    "deadline", "next step", "stakeholder", "assignee", "responsible",
    "owner", "priority", "mentioned", "proposed", "announced",
    "presented", "reported", "concern", "risk", "blocker", "mitigation",
})

_ANALYZE_KEYWORDS = frozenset({
    "analyze", "evaluate", "assess", "compare and contrast", "critique",
    "judge", "justify", "which approach", "trade-off", "pros and cons",
    "strengths and weaknesses", "implications", "impact of",
})

_REMEMBER_KEYWORDS = frozenset({
    "what is", "what are", "who", "when", "where", "list", "name",
    "identify", "recall", "state", "define",
})

_MEETING_CONTEXT_KEYWORDS = frozenset({
    "speaker", "speaker's", "presented by", "mentioned by", "proposed by",
    "announced by", "reported by", "stated by", "shared by",
    "asked the", "requested by", "requested from", "requested the",
    "delegated to", "assigned to", "responsible for",
    "the speaker", "does the speaker", "did the speaker",
    "what action does", "what did the speaker",
})


def _contains_name_reference(text: str) -> bool:
    import re as _re
    lower = text.lower()
    if any(kw in lower for kw in _MEETING_CONTEXT_KEYWORDS):
        return True
    patterns = [
        r"\b[A-Z][a-z]+\s+(said|asked|proposed|mentioned|agreed|decided|requested|stated|shared|announced|reported|presented|noted)\b",
        r"\b(does|did|will|would|should|can|could)\s+the\s+speaker\b",
    ]
    for p in patterns:
        if _re.search(p, text):
            return True
    return False


_ADMIN_LOGISTICS_KEYWORDS = frozenset({
    "attendance", "attendee", "attendees", "join the meeting", "joined the meeting",
    "left the meeting", "greeting", "good morning", "good afternoon", "good evening",
    "hello everyone", "hi everyone", "welcome", "thanks for joining",
    "chat moderation", "moderator", "muted", "unmuted", "screen share",
    "recording", "breakout room", "poll", "raise hand",
    "next meeting", "schedule", "calendar invite", "follow-up meeting",
    "logistics", "administrative", "housekeeping",
    "roll call", "quorum", "agenda item",
    "zoom", "chat box", "host asked", "unmute", "mic",
    "video on", "video off", "screen sharing", "breakout",
})

_STRONG_MEETING_PENALTY_KEYWORDS = frozenset({
    "speaker request", "speaker requests", "speaker said", "speaker asked",
    "speaker mentioned", "speaker proposed", "speaker announced",
    "during the meeting", "in the meeting", "at the meeting",
    "the speaker", "does the speaker", "did the speaker",
    "action does the speaker", "action does", "requested from",
    "requested by", "delegated to", "assigned to",
})


def _is_administrative(text: str) -> bool:
    lower = text.lower()
    count = sum(1 for kw in _ADMIN_LOGISTICS_KEYWORDS if kw in lower)
    if count >= 2:
        return True
    if any(kw in lower for kw in (
        "attendance", "good morning", "good afternoon", "hello everyone",
        "chat moderation", "housekeeping", "roll call",
    )):
        return True
    return False


def _is_meeting_centric(text: str) -> bool:
    lower = text.lower()
    if any(kw in lower for kw in _STRONG_MEETING_PENALTY_KEYWORDS):
        return True
    if _contains_name_reference(text):
        return True
    meeting_hits = sum(1 for kw in _MEETING_KEYWORDS if kw in lower)
    admin_hits = sum(1 for kw in _ADMIN_LOGISTICS_KEYWORDS if kw in lower)
    if meeting_hits + admin_hits >= 3:
        return True
    return False


_HIGH_EDUCATIONAL_KEYWORDS = frozenset({
    "why does", "how does", "what causes", "what leads to", "what prevents",
    "impact of", "effect of", "importance of", "significance of",
    "difference between", "relationship between", "advantage of",
    "disadvantage of", "benefit of", "purpose of",
    "improve", "optimize", "best practice", "principle",
    "real-world", "in practice", "scenario", "use case",
    "component of", "which component", "most improves", "produces the most",
    "technique produces", "prompt engineering", "design mistake",
    "reduces answer", "response quality", "design a prompt",
    "zero-shot", "few-shot", "chain-of-thought", "cot",
    "architecture", "workflow", "design decision", "trade-off",
    "compare", "contrast", "analyze", "evaluate",
})


_DEFINITION_KEYWORDS = frozenset({
    "what is", "define", "definition", "meaning", "term", "called",
    "refers to", "known as", "stands for",
})


_EDUCATIONAL_BOOST_KEYWORDS = _HIGH_EDUCATIONAL_KEYWORDS


def _classify_mcq_category(question_text: str, explanation: str) -> str:
    text = f"{question_text} {explanation}".lower()
    app_score = sum(1 for kw in _APPLICATION_KEYWORDS if kw in text)
    concept_score = sum(1 for kw in _CONCEPT_KEYWORDS if kw in text)
    meeting_score = sum(1 for kw in _MEETING_KEYWORDS if kw in text)
    if meeting_score >= 2 and meeting_score >= app_score and meeting_score >= concept_score:
        return "meeting"
    if app_score >= 2 and app_score >= concept_score:
        return "application"
    if concept_score >= 1:
        return "concept"
    return "quiz"


def _classify_sq_category(question_text: str, sample_answer: str) -> str:
    text = f"{question_text} {sample_answer}".lower()
    app_score = sum(1 for kw in _APPLICATION_KEYWORDS if kw in text)
    meeting_score = sum(1 for kw in _MEETING_KEYWORDS if kw in text)
    if meeting_score >= 2 and meeting_score >= app_score:
        return "meeting"
    if app_score >= 1:
        return "application"
    return "concept"


def _classify_fc_category(front: str, back: str) -> str:
    text = f"{front} {back}".lower()
    if sum(1 for kw in _DEFINITION_KEYWORDS if kw in text) >= 1:
        return "definition"
    if any(kw in text for kw in ("key concept", "core idea", "fundamental", "foundation", "principle")):
        return "core_concept"
    if any(kw in text for kw in ("term", "terminology", "jargon", "acronym", "abbreviation")):
        return "important_term"
    return "revision"


def _infer_fc_difficulty(front: str, back: str) -> str:
    text = f"{front} {back}".lower()
    if any(kw in text for kw in _EDUCATIONAL_BOOST_KEYWORDS):
        return "hard"
    if any(kw in text for kw in ("why", "how", "compare", "difference", "impact", "cause", "reason")):
        return "medium"
    if any(kw in text for kw in _DEFINITION_KEYWORDS):
        return "easy"
    if len(back.strip()) > 60:
        return "medium"
    return "easy"


def _classify_mcq_bloom(question_text: str, category: str) -> str:
    text = question_text.lower()
    if any(kw in text for kw in _ANALYZE_KEYWORDS):
        return "analyze"
    if category == "application":
        return "apply"
    if any(kw in text for kw in _REMEMBER_KEYWORDS):
        return "remember"
    if any(kw in text for kw in _CONCEPT_KEYWORDS):
        return "understand"
    return "understand"


def _classify_sq_bloom(question_text: str, category: str) -> str:
    text = question_text.lower()
    if any(kw in text for kw in _ANALYZE_KEYWORDS):
        return "analyze"
    if category == "application":
        return "apply"
    return "understand"


def _score_mcq(question_text: str, explanation: str, difficulty: str,
               category: str, bloom: str) -> tuple[float, float]:
    text = f"{question_text} {explanation}"
    lower = text.lower()

    edu = 0.25

    if category == "concept":
        edu += 0.2
    elif category == "application":
        edu += 0.25
    elif category == "quiz":
        edu += 0.05
    elif category == "meeting":
        edu -= 0.05

    if bloom == "analyze":
        edu += 0.15
    elif bloom == "apply":
        edu += 0.12
    elif bloom == "understand":
        edu += 0.08
    elif bloom == "remember":
        edu += 0.03

    if difficulty == "hard":
        edu += 0.08
    elif difficulty == "medium":
        edu += 0.04

    if any(kw in lower for kw in _EDUCATIONAL_BOOST_KEYWORDS):
        edu += 0.15

    if len(explanation.strip()) > 80:
        edu += 0.05
    elif len(explanation.strip()) > 50:
        edu += 0.03

    if _is_administrative(text):
        edu -= 0.45

    if _is_meeting_centric(text):
        edu -= 0.4

    if any(kw in lower for kw in _MEETING_KEYWORDS):
        if category == "meeting":
            edu -= 0.15

    edu = max(0.0, min(round(edu, 2), 1.0))

    rel = 0.5
    if any(kw in lower for kw in _MEETING_KEYWORDS):
        rel += 0.1
    if category == "meeting":
        rel += 0.1
    elif category == "concept":
        rel += 0.1
    if difficulty in ("medium", "hard"):
        rel += 0.05
    rel = min(round(rel, 2), 1.0)
    return edu, rel


def _score_sq(question_text: str, sample_answer: str, difficulty: str,
              category: str, bloom: str) -> float:
    text = f"{question_text} {sample_answer}"
    lower = text.lower()

    edu = 0.25

    if category == "application":
        edu += 0.25
    elif category == "concept":
        edu += 0.2
    elif category == "meeting":
        edu -= 0.05

    if bloom == "analyze":
        edu += 0.15
    elif bloom == "apply":
        edu += 0.12
    elif bloom == "understand":
        edu += 0.08

    if difficulty == "hard":
        edu += 0.08
    elif difficulty == "medium":
        edu += 0.04

    if any(kw in lower for kw in _EDUCATIONAL_BOOST_KEYWORDS):
        edu += 0.15

    if len(sample_answer.strip()) > 50:
        edu += 0.05
    elif len(sample_answer.strip()) > 30:
        edu += 0.03

    if _is_administrative(text):
        edu -= 0.45

    if _is_meeting_centric(text):
        edu -= 0.4

    if category == "meeting":
        edu -= 0.15

    return max(0.0, min(round(edu, 2), 1.0))


def _score_fc(front: str, back: str) -> float:
    text = f"{front} {back}"
    lower = text.lower()

    edu = 0.25

    if len(front.strip()) > 15:
        edu += 0.1
    if len(back.strip()) > 40:
        edu += 0.15
    elif len(back.strip()) > 20:
        edu += 0.1

    if any(kw in lower for kw in _DEFINITION_KEYWORDS):
        edu += 0.15
    if any(kw in lower for kw in ("key concept", "core idea", "fundamental", "principle")):
        edu += 0.1

    if any(kw in lower for kw in _EDUCATIONAL_BOOST_KEYWORDS):
        edu += 0.15

    if _is_administrative(text):
        edu -= 0.45

    if _is_meeting_centric(text):
        edu -= 0.35

    return max(0.0, min(round(edu, 2), 1.0))


class ClassificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def classify_questions(self, transcript_id: uuid.UUID) -> int:
        rows = list(self.db.scalars(
            select(Question).where(
                Question.transcript_id == transcript_id,
                Question.is_duplicate == False,
            )
        ).all())
        if not rows:
            return 0

        classified = 0
        for q in rows:
            if q.question_type == "mcq":
                cat = _classify_mcq_category(q.question_text, q.explanation)
                bloom = _classify_mcq_bloom(q.question_text, cat)
                edu, rel = _score_mcq(
                    q.question_text, q.explanation, q.difficulty, cat, bloom
                )
            elif q.question_type == "short_answer":
                content_text = q.explanation or ""
                cat = _classify_sq_category(q.question_text, content_text)
                bloom = _classify_sq_bloom(q.question_text, cat)
                edu = _score_sq(
                    q.question_text, content_text, q.difficulty, cat, bloom
                )
                rel = edu
            elif q.question_type == "true_false":
                cat = _classify_mcq_category(q.question_text, q.explanation)
                bloom = _classify_mcq_bloom(q.question_text, cat)
                edu, rel = _score_mcq(
                    q.question_text, q.explanation, q.difficulty, cat, bloom
                )
            else:
                cat = "concept"
                bloom = "understand"
                edu, rel = 0.5, 0.5

            q.category = cat
            q.bloom_taxonomy = bloom
            q.educational_score = edu
            q.relevance_score = rel
            classified += 1

        self.db.flush()
        logger.info(
            "classification.questions_classified",
            extra={
                "transcript_id": str(transcript_id),
                "count": classified,
            },
        )
        return classified

    def classify_learning_outputs(self, transcript_id: uuid.UUID) -> int:
        rows = list(self.db.scalars(
            select(LearningOutput).where(
                LearningOutput.transcript_id == transcript_id,
            )
        ).all())
        if not rows:
            return 0

        classified = 0
        for lo in rows:
            content = lo.content or {}
            if lo.output_type == "short_question":
                qt = str(content.get("question_text", ""))
                sa = str(content.get("sample_answer", ""))
                cat = _classify_sq_category(qt, sa)
                bloom = _classify_sq_bloom(qt, cat)
                diff = lo.difficulty or "medium"
                edu = _score_sq(qt, sa, diff, cat, bloom)
                lo.difficulty = diff
            elif lo.output_type == "flashcard":
                front = str(content.get("front", ""))
                back = str(content.get("back", ""))
                cat = _classify_fc_category(front, back)
                bloom = None
                edu = _score_fc(front, back)
                if lo.difficulty is None:
                    lo.difficulty = _infer_fc_difficulty(front, back)
            else:
                continue

            lo.category = cat
            lo.bloom_taxonomy = bloom
            lo.educational_score = edu
            classified += 1

        self.db.flush()
        logger.info(
            "classification.learning_outputs_classified",
            extra={
                "transcript_id": str(transcript_id),
                "count": classified,
            },
        )
        return classified

    def recompute_rankings(self, transcript_id: uuid.UUID) -> dict:
        q_rows = list(self.db.scalars(
            select(Question).where(
                Question.transcript_id == transcript_id,
                Question.is_duplicate == False,
            )
        ).all())
        q_rescored = 0
        for q in q_rows:
            if q.question_type == "mcq" or q.question_type == "true_false":
                cat = q.category or _classify_mcq_category(q.question_text, q.explanation)
                bloom = q.bloom_taxonomy or _classify_mcq_bloom(q.question_text, cat)
                edu, rel = _score_mcq(q.question_text, q.explanation, q.difficulty, cat, bloom)
                q.category = cat
                q.bloom_taxonomy = bloom
                q.educational_score = edu
                q.relevance_score = rel
                q_rescored += 1
            elif q.question_type == "short_answer":
                content_text = q.explanation or ""
                cat = q.category or _classify_sq_category(q.question_text, content_text)
                bloom = q.bloom_taxonomy or _classify_sq_bloom(q.question_text, cat)
                edu = _score_sq(q.question_text, content_text, q.difficulty, cat, bloom)
                q.category = cat
                q.bloom_taxonomy = bloom
                q.educational_score = edu
                q.relevance_score = edu
                q_rescored += 1

        lo_rows = list(self.db.scalars(
            select(LearningOutput).where(
                LearningOutput.transcript_id == transcript_id,
            )
        ).all())
        lo_rescored = 0
        for lo in lo_rows:
            content = lo.content or {}
            if lo.output_type == "short_question":
                qt = str(content.get("question_text", ""))
                sa = str(content.get("sample_answer", ""))
                cat = lo.category or _classify_sq_category(qt, sa)
                bloom = lo.bloom_taxonomy or _classify_sq_bloom(qt, cat)
                edu = _score_sq(qt, sa, lo.difficulty or "medium", cat, bloom)
                lo.category = cat
                lo.bloom_taxonomy = bloom
                lo.educational_score = edu
                lo_rescored += 1
            elif lo.output_type == "flashcard":
                front = str(content.get("front", ""))
                back = str(content.get("back", ""))
                cat = lo.category or _classify_fc_category(front, back)
                edu = _score_fc(front, back)
                lo.category = cat
                lo.educational_score = edu
                if lo.difficulty is None:
                    lo.difficulty = _infer_fc_difficulty(front, back)
                lo_rescored += 1

        self.db.flush()
        logger.info(
            "classification.rankings_recomputed",
            extra={
                "transcript_id": str(transcript_id),
                "questions_rescored": q_rescored,
                "learning_outputs_rescored": lo_rescored,
            },
        )
        return {
            "transcript_id": str(transcript_id),
            "questions_rescored": q_rescored,
            "learning_outputs_rescored": lo_rescored,
        }

    def classify_transcript(self, transcript_id: uuid.UUID) -> dict:
        q_count = self.classify_questions(transcript_id)
        lo_count = self.classify_learning_outputs(transcript_id)
        return {
            "transcript_id": str(transcript_id),
            "questions_classified": q_count,
            "learning_outputs_classified": lo_count,
        }

    @classmethod
    def classify_all_unclassified(cls, db: Session) -> dict:
        from sqlalchemy import select, func as sa_func
        from app.db.models.transcript import Transcript

        completed_statuses = ("completed", "completed_with_warnings")
        transcript_ids = db.scalars(
            select(Transcript.id).where(
                Transcript.status.in_(completed_statuses),
            )
        ).all()

        service = cls(db)
        total_q = 0
        total_lo = 0
        classified_transcripts = 0
        rescored_transcripts = 0

        for tid in transcript_ids:
            result = service.classify_transcript(tid)
            if result["questions_classified"] > 0 or result["learning_outputs_classified"] > 0:
                db.commit()
                classified_transcripts += 1
                total_q += result["questions_classified"]
                total_lo += result["learning_outputs_classified"]
            else:
                db.rollback()
                rank_result = service.recompute_rankings(tid)
                if rank_result["questions_rescored"] > 0 or rank_result["learning_outputs_rescored"] > 0:
                    db.commit()
                    rescored_transcripts += 1

        return {
            "transcripts_processed": len(transcript_ids),
            "transcripts_classified": classified_transcripts,
            "transcripts_rescored": rescored_transcripts,
            "total_questions_classified": total_q,
            "total_learning_outputs_classified": total_lo,
        }
