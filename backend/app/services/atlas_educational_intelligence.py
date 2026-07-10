"""Educational Intelligence Service for Atlas."""
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services.atlas_context_service import MeetingContext
from app.services.professor_ranking_service import ProfessorRankingService, RankedQuestion

logger = get_logger(__name__)


@dataclass
class EducationalResponse:
    content: str
    source_type: str
    artifacts: dict | None = None


def _format_items(items: list, key: str | None = None, max_count: int = 5) -> str:
    """Format a list of items into a string."""
    if not items:
        return ""
    lines = []
    for item in items[:max_count]:
        if isinstance(item, dict) and key:
            text = item.get(key, "")
        elif isinstance(item, str):
            text = item
        else:
            text = str(item)
        if text:
            lines.append(f"• {text}")
    return "\n".join(lines)


# Citation markers like [1], [2], [12] must never appear inside the displayed
# question text or answer options — only in explanations.
_CITATION_RE = re.compile(r"\s*\[\d{1,3}\]\s*")


def _strip_citations(text: str) -> str:
    """Remove inline citation markers from question text / option text."""
    if not text:
        return text
    cleaned = _CITATION_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_requested_count(user_message: str | None, default: int = 5, max_cap: int = 100) -> int:
    """Extract the requested number of questions from a quiz-style user message.

    Recognises:
      - digit words: "five", "ten", "twenty" ... (one to fifty, plus round tens)
      - explicit digits: "5", "15 questions", "give me 7 mcqs"
    Falls back to ``default`` when nothing is specified. Capped at ``max_cap``.
    """
    if not user_message:
        return default

    msg = user_message.lower()

    word_map = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
        "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
        "twenty-one": 21, "thirty": 30, "forty": 40, "fifty": 50,
    }

    m = re.search(r"\b(\d{1,3})\b", msg)
    if m:
        try:
            n = int(m.group(1))
            if n > 0:
                return min(n, max_cap)
        except ValueError:
            pass

    for kw in (
        "twenty-one", "thirty", "forty", "fifty", "twenty", "nineteen",
        "eighteen", "seventeen", "sixteen", "fifteen", "fourteen",
        "thirteen", "twelve", "eleven", "ten", "nine", "eight", "seven",
        "six", "five", "four", "three", "two", "one",
    ):
        if re.search(r"\b" + re.escape(kw) + r"\b", msg):
            return min(word_map[kw], max_cap)

    return default


def _option_letter(index: int) -> str:
    return chr(ord("A") + index) if 0 <= index < 26 else str(index + 1)


def _format_option(opt) -> tuple[str, str]:
    """Return (letter, body) for an option regardless of stored shape."""
    if isinstance(opt, dict):
        letter = (opt.get("letter") or _option_letter(0)).strip()
        body = opt.get("text") or opt.get("body") or ""
        if not body:
            body = str(opt)
        return letter, body
    s = str(opt).strip()
    m = re.match(r"^([A-Da-d])[:.\-)]\s*(.*)$", s)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return _option_letter(0), s


def _ranked_to_mcq_dict(question) -> dict:
    """Build the MCQ dict used by the quiz formatter from a stored Question.

    The Question ORM model is the single source of truth for the MCQ content:
    question_text, options, correct_answer, explanation. RankedQuestion is
    used only for ranking/ordering/tier selection and is NOT consulted here.
    """
    return {
        "question": getattr(question, "question_text", "") or "",
        "options": getattr(question, "options", []) or [],
        "answer": getattr(question, "correct_answer", "") or "",
        "explanation": getattr(question, "explanation", "") or "",
        "difficulty": getattr(question, "difficulty", "") or "",
        "bloom_taxonomy": getattr(question, "bloom_taxonomy", "") or "",
        "category": getattr(question, "category", "") or "",
    }


def _merge_ranked_by_score(per_transcript_results) -> list[RankedQuestion]:
    """Merge per-transcript ranked lists into one ranked list.

    Sort by composite_score descending (stable), preserving each transcript's
    internal ranking order. We never re-shuffle questions randomly.
    """
    flattened: list[tuple[float, int, RankedQuestion]] = []
    for transcript_rank_idx, ranked in enumerate(per_transcript_results):
        for position, rq in enumerate(ranked):
            # Tie-break key: (composite_score, transcript_idx, position)
            # so questions keep their professor-assigned order within a transcript
            # and across transcripts early-bundled transcripts win ties.
            flattened.append((-rq.composite_score, transcript_rank_idx, position, rq))

    flattened.sort(key=lambda t: (t[0], t[1], t[2]))
    return [t[3] for t in flattened]


def _select_ranked_questions(
    ranked: list[RankedQuestion],
    requested_count: int,
) -> list[RankedQuestion]:
    """Select ``requested_count`` questions respecting the professor tiers.

    Tiers (preserve ranking order, never re-shuffle):
      1-10 requested  -> Top 10
      11-20 requested -> Top 20
      21-50 requested -> Top 50
      >50 requested   -> Top 50 first, then remaining ranked in order
    """
    if requested_count <= 0:
        return []
    if requested_count <= 10:
        pool = ranked[:10]
    elif requested_count <= 20:
        pool = ranked[:20]
    elif requested_count <= 50:
        pool = ranked[:50]
    else:
        pool = list(ranked)  # top-50 first, continue with remaining ranked

    return pool[:requested_count]


def build_quiz_response(
    db: Session,
    context: MeetingContext,
    *,
    user_message: str | None = None,
) -> EducationalResponse:
    """Gather quiz artifacts from existing professor-ranked MCQs.

    The Atlas chatbot must NOT regenerate MCQs. The stored, professor-ranked
    questions are the primary source. We only select from the ranked pipeline
    (Top-10 ⊂ Top-20 ⊂ Top-50 ⊂ all ranked), preserve ranking order, avoid
    duplicates/near-duplicates (the professor pipeline already dedupes), and
    maximise concept diversity.

    Citation markers are stripped from the question text and the answer
    options; they are kept only inside the explanation.
    """
    if not context.meeting_id:
        return EducationalResponse(
            "No meeting selected. Select a meeting to generate a quiz.",
            "quiz_request",
        )

    from sqlalchemy import select
    from app.db.models.transcript import Transcript

    transcripts = db.scalars(
        select(Transcript).where(Transcript.meeting_id == context.meeting_id)
    ).all()

    if not transcripts:
        return EducationalResponse(
            "No quizzes are available for this meeting yet. "
            "Once the Educational Intelligence pipeline has generated questions, "
            "I'll surface a quiz for you.",
            "quiz_request",
        )

    requested_count = _parse_requested_count(user_message)

    # Run the professor ranking per transcript and merge deterministically.
    ranking_svc = ProfessorRankingService(db)
    per_transcript_ranked: list[list[RankedQuestion]] = []
    for t in transcripts:
        try:
            result = ranking_svc.rank_questions(t.id)
            if result.ranked:
                per_transcript_ranked.append(result.ranked)
        except Exception:
            logger.exception(
                "atlas.quiz.ranking_failed",
                extra={"transcript_id": str(t.id)},
            )

    if not per_transcript_ranked:
        return EducationalResponse(
            "No quizzes are available for this meeting yet. "
            "Once the Educational Intelligence pipeline has generated questions, "
            "I'll surface a quiz for you.",
            "quiz_request",
        )

    merged = _merge_ranked_by_score(per_transcript_ranked)
    selected = _select_ranked_questions(merged, requested_count)

    if not selected:
        return EducationalResponse(
            "No quizzes are available for this meeting yet. "
            "Once the Educational Intelligence pipeline has generated questions, "
            "I'll surface a quiz for you.",
            "quiz_request",
        )

    # Fetch the original Question records for the professor-selected question
    # IDs. The Question model is the source of truth for question_text,
    # options, correct_answer, explanation, difficulty, bloom level, category.
    # RankedQuestion contributes ONLY ranking/ordering/score/tier — never the
    # MCQ content itself, since RankedQuestion intentionally excludes the
    # full MCQ payload.
    from app.db.models.question import Question

    selected_ids = [rq.question_id for rq in selected if rq.question_id is not None]
    questions_by_id: dict = {}
    if selected_ids:
        rows = db.scalars(
            select(Question).where(Question.id.in_(selected_ids))
        ).all()
        questions_by_id = {q.id: q for q in rows}

    mcqs: list[dict] = []
    needs_explanation: list[bool] = []
    for rq in selected:
        question = questions_by_id.get(rq.question_id)
        if question is None:
            # Stale/corrupted ranking entry — skip rather than fabricate.
            logger.warning(
                "atlas.quiz.ranked_question_missing",
                extra={"question_id": str(rq.question_id)},
            )
            continue
        mcq = _ranked_to_mcq_dict(question)
        # Strip stray citation markers from question text and every option body.
        mcq["question"] = _strip_citations(mcq["question"])
        cleaned_options = []
        for opt in mcq["options"]:
            letter, body = _format_option(opt)
            cleaned_options.append({"letter": letter, "text": _strip_citations(body)})
        mcq["options"] = cleaned_options
        # Keep citations ONLY in the explanation.
        explanation = (mcq.get("explanation") or "").strip()
        needs_expl = (not explanation)
        needs_explanation.append(needs_expl)
        mcq["explanation_needs_generation"] = needs_expl
        mcq["rank"] = rq.rank
        mcq["composite_score"] = rq.composite_score
        mcqs.append(mcq)

    if not mcqs:
        return EducationalResponse(
            "No quizzes are available for this meeting yet. "
            "Once the Educational Intelligence pipeline has generated questions, "
            "I'll surface a quiz for you.",
            "quiz_request",
        )

    artifacts = {
        "mcqs": mcqs,
        "requested_count": requested_count,
        "returned_count": len(mcqs),
        "needs_explanation_generation": any(needs_explanation),
        "ranked": True,
    }
    return EducationalResponse(
        "",
        "quiz_request",
        artifacts=artifacts,
    )


def build_summary_response(context: MeetingContext) -> EducationalResponse:
    """Gather summary artifacts from existing meeting context."""
    artifacts = {}
    if context.meeting_topic:
        artifacts["topic"] = context.meeting_topic
    if context.meeting_date:
        artifacts["date"] = context.meeting_date
    if context.transcript_summary:
        artifacts["summary"] = context.transcript_summary
    if context.key_takeaways:
        artifacts["key_takeaways"] = context.key_takeaways[:5]
    if not artifacts:
        return EducationalResponse(
            "No summary available for this meeting.",
            "summary",
        )
    return EducationalResponse(
        "",
        "summary",
        artifacts=artifacts,
    )


def build_concept_explanation_response(context: MeetingContext, concept: str | None = None) -> EducationalResponse:
    """Gather concept explanation artifacts from existing key concepts."""
    if not context.key_concepts:
        return EducationalResponse(
            "No key concepts available for this meeting.",
            "concept_explanation",
        )
    artifacts = {
        "concepts": context.key_concepts[:5],
    }
    if concept:
        artifacts["target_concept"] = concept
    return EducationalResponse(
        "",
        "concept_explanation",
        artifacts=artifacts,
    )


def build_revision_guide_response(context: MeetingContext) -> EducationalResponse:
    """Gather revision guide artifacts from existing summary, concepts, and takeaways."""
    artifacts = {}
    if context.transcript_summary:
        artifacts["summary"] = context.transcript_summary
    if context.key_concepts:
        artifacts["key_concepts"] = context.key_concepts[:5]
    if context.key_takeaways:
        artifacts["key_takeaways"] = context.key_takeaways[:5]
    if not artifacts:
        return EducationalResponse(
            "No revision material available for this meeting yet.",
            "revision_request",
        )
    return EducationalResponse(
        "",
        "revision_request",
        artifacts=artifacts,
    )


def build_action_items_response(context: MeetingContext) -> EducationalResponse:
    """Gather action items artifacts from existing action items."""
    if not context.action_items:
        return EducationalResponse(
            "No action items recorded for this meeting.",
            "action_items",
        )
    artifacts = {
        "action_items": context.action_items[:5],
    }
    return EducationalResponse(
        "",
        "action_items",
        artifacts=artifacts,
    )


def build_decisions_response(context: MeetingContext) -> EducationalResponse:
    """Gather decisions artifacts from existing insights."""
    if not context.decisions:
        return EducationalResponse(
            "No decisions recorded for this meeting.",
            "decisions",
        )
    artifacts = {
        "decisions": context.decisions[:5],
    }
    return EducationalResponse(
        "",
        "decisions",
        artifacts=artifacts,
    )


def build_recommendations_response(context: MeetingContext) -> EducationalResponse:
    """Gather recommendations artifacts from existing insights."""
    if not context.recommendations and not context.transcript_summary:
        return EducationalResponse(
            "No recommendations available for this meeting.",
            "recommendations",
        )
    artifacts = {
        "recommendations": context.recommendations[:5] if context.recommendations else [],
        "summary": context.transcript_summary,
    }
    return EducationalResponse(
        "",
        "recommendations",
        artifacts=artifacts,
    )
