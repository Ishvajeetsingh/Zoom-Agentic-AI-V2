"""Question generation orchestration service.

Consumes transcript chunks and calls the Ollama LLM to generate
assessment questions. This module wires the OllamaApiClient to the
chunking output but does NOT own the LangGraph workflow — that will
be added later as a separate orchestration layer.
"""

from __future__ import annotations
from app.llm.provider import create_llm_client, get_generation_model

import json
import re
import uuid
from dataclasses import dataclass

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.integrations.ollama.client import (
    GenerationResponse,
    OllamaApiClient,
    OllamaConnectionError,
    OllamaGenerateError,
    OllamaModelError,
)

logger = get_logger(__name__)

_THINK_OPEN = "\u003Cthink\u003E"
_THINK_CLOSE = "\u003C/think\u003E"
_THINKING_RE = re.compile(rf"^{re.escape(_THINK_OPEN)}.*?{re.escape(_THINK_CLOSE)}", re.DOTALL)

_JSON_SCHEMA_KEYS = frozenset({"$schema", "$id", "#/$id", "additionalProperties", "properties", "required", "type"})


class QuestionGenerationError(AppError):
    """Raised when question generation cannot be completed."""


@dataclass(frozen=True)
class ExtractedConcept:
    concept: str
    category: str
    summary: str
    bloom_level: str


@dataclass(frozen=True)
class GeneratedQuestion:
    question_text: str
    question_type: str
    question_style: str
    bloom_level: str
    options: list[str]
    correct_answer: str
    explanation: str
    difficulty: str
    chunk_id: uuid.UUID | None = None
    educational_score: float | None = None
    rewritten: bool = False
    options_rewritten: bool = False
    original_question_text: str | None = None
    review_reason: str | None = None


@dataclass(frozen=True)
class QuestionGenerationResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    questions: list[GeneratedQuestion]
    total_questions: int
    model_used: str
    total_prompt_tokens: int | None = None
    total_completion_tokens: int | None = None
    total_duration_seconds: float | None = None


CONCEPT_EXTRACTION_PROMPT = """You are an educational content analyst. Extract key educational concepts from the transcript chunk.

Categories: definition, process, comparison, advantage, disadvantage, application, decision, best_practice, cause_effect, principle.

For each concept return:
- "concept": concise label
- "category": one of the categories above
- "summary": 1-2 sentence educational summary (rephrase as educational content, NOT a copy of transcript wording)
- "bloom_level": highest Bloom level this concept supports — "understand", "apply", or "analyze"

Extract ALL distinct concepts. Return a JSON array:
[{"concept": "...", "category": "...", "summary": "...", "bloom_level": "..."}]"""

MCQ_SYSTEM_PROMPT = """You are a university-level assessment author creating rigorous, concept-driven MCQs from educational content extracted from meeting transcripts.

## QUESTION STYLES (use at least 2 per batch)
- "concept_understanding" — Understand a concept/definition/principle
- "application" — Apply a concept to a new situation
- "analysis" — Break down or identify components/relationships
- "comparison" — Compare approaches/solutions/ideas
- "cause_effect" — Why something happens or what results
- "scenario_based" — Given a realistic scenario, determine correct action/outcome
- "best_practice" — Which approach is recommended in a given situation
- "decision_making" — Evaluate options and select the best action

## BLOOM'S TAXONOMY
Avoid pure Remember (rote recall). Target: Understand, Apply, Analyze. At least 60% at Apply/Analyze level.

## ANTI-PATTERNS (STRICTLY AVOID)
Do NOT ask: "What did the speaker/person...", "According to the meeting/Name...", "Who said/mentioned...", "What happened during the meeting...", or paraphrase transcript sentences as questions.

Exception: meeting-centric phrasing is OK only for formally agreed decisions/action items.

Instead frame around the CONCEPT: "Which principle explains why..." / "In a scenario where X..." / "What is the primary advantage of X over Y..."

## ANTI-HALLUCINATION (STRICTLY FOLLOW)
All questions, options, and concepts must be traceable to the transcript. You may transform and rephrase transcript content educationally, but NEVER introduce concepts, technologies, terminology, or knowledge NOT discussed in the transcript. Every MCQ must be grounded in the provided transcript and concepts.

## DISTRACTOR QUALITY
Each distractor must be: plausible, conceptually related (same domain/vocabulary), a common misconception or near-miss. NOT absurd, NOT joke answers, NOT trivial word-swaps. Each distractor should test a different misunderstanding.

BAD: Photosynthesis / Cooking / Sleeping / Walking (absurd, unrelated)
GOOD: Photosynthesis / Chemosynthesis / Photorespiration / Cellular respiration (all plausible, same domain)

## COVERAGE
Generate questions about DIFFERENT concepts. Do NOT generate multiple questions about the same concept. Spread across all concepts provided.

## OUTPUT
4 options (A-D), exactly 1 correct, brief explanation, difficulty (easy|medium|hard), question_style and bloom_level.
Example object:
{
    "question_text": "Which mechanism explains why X occurs in scenario Y?",
    "question_type": "mcq",
    "question_style": "cause_effect",
    "bloom_level": "apply",
    "options": ["A: First plausible answer", "B: Second plausible answer", "C: Third plausible answer", "D: Fourth plausible answer"],
    "correct_answer": "A",
    "explanation": "This occurs because...",
    "difficulty": "medium"
}"""

REVIEW_SYSTEM_PROMPT = """You are an experienced university professor reviewing an examination paper before it is given to students.

For EVERY MCQ, apply these SIX screening questions. If ANY answer is unsatisfactory, you MUST act:

1. Would this appear in a good university examination?     → If NO: rewrite
2. Does this test conceptual understanding, not transcript memory? → If NO: rewrite
3. Can a student answer it just by reading the options?     → If YES: rewrite_options (or rewrite if stem is also weak)
4. Are the distractors realistic misconceptions from partial understanding? → If NO: rewrite_options
5. Is the correct answer identifiable because it is longer/more detailed/obviously different? → If YES: rewrite_options
6. Would two partially-informed students genuinely disagree between at least two options? → If NO: rewrite_options

CRITICAL: Questions 3, 5, 6 check OPTION quality. Questions 1, 2, 4 check QUESTION quality.
If only options are weak → action "rewrite_options". If stem is also weak → action "rewrite".

## AUTOMATIC REWRITE RULES (no exceptions)
You MUST rewrite (action "rewrite") any question containing:
- "According to the transcript..." / "According to the discussion..." / "According to the speaker..."
- "What did the speaker..." / "Who said/mentioned/asked..." / "Which participant..."
- Meeting logistics, participant names, or transcript recall

You MUST rewrite options (action "rewrite_options") if:
- Any option is a single-word label (e.g., Role, Task, Context, Generate, Analyze, Prompt, Accuracy)
- The correct answer is noticeably longer, more detailed, or uses more specific/technical language than distractors
- Distractors are absurd, obviously wrong, or trivially distinguishable from the correct answer
- The scenario in the stem makes one option obviously the only reasonable choice

Replace single-word options with conceptual action-based alternatives:
  BAD: A: Role | B: Task | C: Context | D: Output Format
  GOOD: A: Assign the AI an expert identity | B: Describe the specific action the AI must perform | C: Provide background information shaping interpretation | D: Specify the required response structure

## STRONG QUESTION PATTERN
Prefer: application, analysis, evaluation, trade-offs, decision-making, scenario-based reasoning.
Frame as: "Which approach is MOST appropriate?" / "Which modification would MOST improve..." / "Which explanation BEST justifies..."
Avoid: "What is..." / "Which component..." / "Which keyword..." / "Which role..."

## GOOD vs BAD — QUICK REFERENCE
GOOD: Scenario + balanced options + reasoning required + 2-3 options appear correct at first glance
BAD: Single-word options | obvious distractors | correct answer is the only specific/technical option | stem reveals answer via options | definition/keyword recall

## COVERAGE
Preferred order: Rewrite Options → Rewrite Question → Reject
Do NOT aggressively reject. Maintain similar transcript coverage.

## REWRITE RULES
- Ground EVERY rewrite in the SAME transcript concepts — never invent facts
- Maintain 4 options (A-D), exactly 1 correct
- Each distractor must test a DIFFERENT misconception
- Prefer Apply or Analyze Bloom levels
- Remove speaker/meeting-logistics references
- If ONLY options are weak but stem is strong → "rewrite_options"
- If stem AND options are weak → "rewrite"
- If unsalvageable → "reject"

## ACTION TYPES
- "keep": Both stem and options are strong. You would include this in a university examination.
- "rewrite_options": Stem is good but options are weak (single-word, obvious, imbalanced, reveal answer).
- "rewrite": Stem needs improvement (possibly options too).
- "reject": Cannot be salvaged educationally while remaining transcript-grounded.

## OUTPUT
Return a JSON array. Each element:
{"question_text": "...", "question_type": "mcq", "question_style": "...", "bloom_level": "...", "options": ["A: ...", "B: ...", "C: ...", "D: ..."], "correct_answer": "A", "explanation": "...", "difficulty": "easy|medium|hard", "action": "keep|rewrite_options|rewrite|reject", "original_question_text": "...", "review_reason": "..."}

- "action": your decision for this MCQ
- "original_question_text": copy of the input question text
- "review_reason": brief explanation
Do NOT include any other text. Return ONLY the JSON array."""


class QuestionService:
    def __init__(
        self,
        ollama_client: OllamaApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.config = config
        self.ollama = ollama_client or create_llm_client(config)

    _MIN_QUESTIONS_PER_CHUNK = 2
    _MAX_QUESTIONS_PER_CHUNK = 5

    @classmethod
    def _compute_question_count(cls, word_count: int) -> int:
        if word_count < 100:
            return 2
        if word_count < 250:
            return 3
        if word_count < 500:
            return 4
        return 5

    def _extract_concepts(
        self,
        chunk_text: str,
        chunk_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> list[ExtractedConcept]:
        if not chunk_text or not chunk_text.strip():
            return []

        concept_prompt = (
            "Extract educational concepts from this transcript chunk.\n\n"
            f"--- TRANSCRIPT ---\n{chunk_text}\n--- END ---\n\n"
            "Return a JSON array of concept objects."
        )

        try:
            response = self.ollama.generate_json(
                concept_prompt,
                model=model or get_generation_model(self.config),
                system=CONCEPT_EXTRACTION_PROMPT,
                temperature=0.3,
                max_tokens=2048,
            )
        except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
            logger.warning(
                "concept_extraction.failed",
                extra={
                    "chunk_id": str(chunk_id) if chunk_id else None,
                    "error": str(exc),
                },
            )
            return []

        raw = response.response.strip()
        if not raw:
            return []

        cleaned = self._strip_thinking_tokens(raw)
        items = self._robust_json_parse(cleaned)

        if items is None:
            logger.warning(
                "concept_extraction.json_parse_failed",
                extra={"response_preview": cleaned[:300]},
            )
            return []

        if isinstance(items, dict):
            if self._is_json_schema(items):
                logger.warning(
                    "concept_extraction.llm_returned_json_schema",
                    extra={"response_preview": cleaned[:300]},
                )
                return []
            unwrapped = self._unwrap_dict_response(items, cleaned)
            if unwrapped is not None:
                items = unwrapped
            elif "concept" in items:
                items = [items]
            else:
                logger.warning(
                    "concept_extraction.unexpected_dict_shape",
                    extra={"dict_keys": list(items.keys()), "response_preview": cleaned[:300]},
                )
                return []

        if not isinstance(items, list):
            return []

        concepts: list[ExtractedConcept] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                concepts.append(
                    ExtractedConcept(
                        concept=str(item.get("concept", "")),
                        category=str(item.get("category", "definition")),
                        summary=str(item.get("summary", "")),
                        bloom_level=str(item.get("bloom_level", "understand")),
                    )
                )
            except Exception:
                continue

        logger.info(
            "concept_extraction.completed",
            extra={
                "chunk_id": str(chunk_id) if chunk_id else None,
                "concepts_extracted": len(concepts),
            },
        )
        return concepts

    @staticmethod
    def _build_concepts_summary(concepts: list[ExtractedConcept]) -> str:
        if not concepts:
            return "No concepts extracted."
        lines: list[str] = []
        for c in concepts:
            lines.append(f"- [{c.category.upper()}] {c.concept}: {c.summary}")
        return "\n".join(lines)

    @staticmethod
    def compute_educational_score(
        question_text: str,
        explanation: str,
        options: list[str],
        correct_answer: str,
        difficulty: str,
        question_style: str,
        bloom_level: str,
        *,
        chunk_text: str | None = None,
    ) -> float:
        _WEAK_PHRASES = frozenset({
            "what did the speaker", "who said", "who mentioned", "who asked",
            "according to the meeting", "according to the transcript",
            "according to the discussion", "according to the speaker",
            "what was discussed", "who presented", "who attended",
            "what happened during", "during the meeting", "in the meeting",
            "the speaker said", "the speaker mentioned", "the speaker asked",
            "which keyword was mentioned", "what action was requested",
            "which example was mentioned", "which participant",
            "which keyword should", "what keyword should",
        })
        _SCENARIO_KEYWORDS = frozenset({
            "scenario", "suppose", "imagine", "if you", "in a situation",
            "given a", "consider the following", "a company", "a team",
            "a developer", "a student", "a user", "if you were",
            "a researcher", "an instructor", "a manager", "an engineer",
        })
        _REASONING_KEYWORDS = frozenset({
            "why does", "how does", "what causes", "what leads to",
            "what prevents", "what is the primary advantage",
            "which principle explains", "what is the main reason",
            "which approach is best", "what would happen if",
            "most likely", "most appropriate", "best explains",
            "primary reason", "key factor", "which strategy",
            "which modification would most", "which decision would best",
            "which explanation best", "most effectively",
        })
        _ADMIN_LOGISTICS = frozenset({
            "attendance", "attendee", "good morning", "good afternoon",
            "hello everyone", "agenda item", "housekeeping", "roll call",
            "muted", "unmuted", "screen share", "breakout room",
            "next meeting", "calendar invite", "greeting",
        })
        _DEFINITION_ONLY_PHRASES = frozenset({
            "what is the definition of", "what is defined as",
            "what does the term", "what is meant by",
            "define the term", "the definition of",
            "which of the following is the definition",
            "what is a", "what are", "what does",
            "which option best defines", "which best defines",
        })
        _KEYWORD_MATCH_PHRASES = frozenset({
            "which keyword", "what keyword", "which term was",
            "what term was", "which phrase was", "what phrase was",
            "which word was", "what word was",
        })
        _COMPONENT_SELECTION_PHRASES = frozenset({
            "which component", "which element", "which role",
            "which part of the prompt", "which prompt component",
            "which section of the prompt", "identify the component",
            "which aspect of the prompt", "which feature",
        })

        lower_q = question_text.lower()
        lower_all = f"{question_text} {explanation}".lower()

        concept_coverage = 0.05
        if len(question_text.strip()) > 20:
            concept_coverage += 0.05
        if any(kw in lower_q for kw in ("principle", "concept", "mechanism", "approach", "method")):
            concept_coverage += 0.05

        grounding = 0.05
        if chunk_text:
            chunk_lower = chunk_text.lower()
            key_tokens = [t for t in question_text.lower().split() if len(t) > 4 and t.isalpha()]
            if key_tokens:
                hit_rate = sum(1 for t in key_tokens if t in chunk_lower) / len(key_tokens)
                grounding += 0.05 * hit_rate

        reasoning = 0.0
        if any(kw in lower_q for kw in _REASONING_KEYWORDS):
            reasoning += 0.20
        elif any(kw in lower_q for kw in ("how", "why", "what if")):
            reasoning += 0.08

        bloom_score = 0.0
        if bloom_level == "analyze":
            bloom_score += 0.15
        elif bloom_level == "apply":
            bloom_score += 0.12
        elif bloom_level == "evaluate":
            bloom_score += 0.15
        elif bloom_level == "understand":
            bloom_score += 0.05
        elif bloom_level == "remember":
            bloom_score -= 0.03

        distractor_quality = 0.05
        if options and len(options) == 4:
            opts_text = " ".join(options).lower()
            opt_words = [set(o.split()) for o in options]
            all_same = all(opt_words[0] == ow for ow in opt_words[1:]) if len(opt_words) > 1 else False
            if not all_same and len(opts_text) > 20:
                distractor_quality += 0.05
            trivial_distractors = sum(1 for o in options if len(o.strip()) < 5)
            distractor_quality -= 0.03 * trivial_distractors
            opt_bodies = []
            for o in options:
                body = re.sub(r"^[A-D]:\s*", "", o.strip(), count=1)
                opt_bodies.append(body)
            opt_lengths = [len(b) for b in opt_bodies]
            if opt_lengths:
                max_len = max(opt_lengths)
                min_len = min(opt_lengths)
                if max_len > 0:
                    length_range_ratio = (max_len - min_len) / max_len
                    if length_range_ratio > 0.6:
                        distractor_quality -= 0.08
                    if length_range_ratio > 0.8:
                        distractor_quality -= 0.07
                    correct_idx = ord(correct_answer.strip()[0].upper()) - ord('A') if correct_answer and correct_answer.strip() else -1
                    if 0 <= correct_idx < len(opt_lengths):
                        correct_len = opt_lengths[correct_idx]
                        non_correct = [l for i, l in enumerate(opt_lengths) if i != correct_idx]
                        if non_correct:
                            avg_distractor_len = sum(non_correct) / len(non_correct)
                            if avg_distractor_len > 0 and correct_len > 0:
                                if correct_len > avg_distractor_len * 1.8:
                                    distractor_quality -= 0.10
                                elif correct_len > avg_distractor_len * 1.5:
                                    distractor_quality -= 0.06
            single_word_count = sum(1 for b in opt_bodies if len(b.split()) <= 2)
            if single_word_count >= 3:
                distractor_quality -= 0.12
            elif single_word_count >= 2:
                distractor_quality -= 0.06
            opt_starts = [b[0].lower() for b in opt_bodies if b]
            if len(set(opt_starts)) < 3 and len(opt_starts) == 4:
                distractor_quality -= 0.03
            if correct_answer and options:
                correct_body = ""
                correct_idx = ord(correct_answer.strip()[0].upper()) - ord('A') if correct_answer.strip() else -1
                if 0 <= correct_idx < len(opt_bodies):
                    correct_body = opt_bodies[correct_idx].lower()
                if correct_body:
                    specific_markers = sum(1 for kw in ("specifically", "explicitly", "precisely", "comprehensive", "detailed", "structured", "clearly defined") if kw in correct_body)
                    generic_markers = sum(1 for b in opt_bodies if b.lower() != correct_body for kw in ("increase", "reduce", "remove", "ignore", "avoid", "use", "try") if kw in b.lower())
                    if specific_markers > 0 and generic_markers >= 2:
                        distractor_quality -= 0.08

        educational_value = 0.05
        if question_style in ("scenario_based", "application", "decision_making", "best_practice"):
            educational_value += 0.15
        elif question_style in ("cause_effect", "comparison", "analysis"):
            educational_value += 0.10
        elif question_style in ("concept_understanding",):
            educational_value += 0.02
        if any(kw in lower_q for kw in _SCENARIO_KEYWORDS):
            educational_value += 0.10

        clarity = 0.05
        if len(question_text.strip()) > 15 and "?" in question_text:
            clarity += 0.05
        if any(kw in lower_q for kw in _WEAK_PHRASES):
            clarity -= 0.15

        ambiguity_penalty = 0.0
        if any(kw in lower_q for kw in _WEAK_PHRASES):
            ambiguity_penalty = -0.25
        if any(kw in lower_all for kw in _ADMIN_LOGISTICS):
            ambiguity_penalty -= 0.20
        if correct_answer and options and len(options) == 4:
            correct_text = ""
            for o in options:
                if o.strip().startswith(correct_answer.strip()[0].upper()):
                    correct_text = o.lower()
                    break
            if correct_text and all(correct_text in o.lower() for o in [x for x in options if x != correct_text]):
                ambiguity_penalty -= 0.15

        transcript_recall_penalty = 0.0
        if any(kw in lower_q for kw in ("according to the transcript", "according to the meeting", "as mentioned in")):
            transcript_recall_penalty = -0.30
        if any(kw in lower_q for kw in ("what did", "who said", "who mentioned", "who asked")):
            transcript_recall_penalty -= 0.25

        speaker_name_penalty = 0.0
        if _contains_name_reference(question_text):
            speaker_name_penalty = -0.35

        definition_only_penalty = 0.0
        if any(kw in lower_q for kw in _DEFINITION_ONLY_PHRASES):
            definition_only_penalty = -0.20

        keyword_match_penalty = 0.0
        if any(kw in lower_q for kw in _KEYWORD_MATCH_PHRASES):
            keyword_match_penalty = -0.30

        component_selection_penalty = 0.0
        if any(kw in lower_q for kw in _COMPONENT_SELECTION_PHRASES):
            component_selection_penalty = -0.25

        obvious_distractor_penalty = 0.0
        if options and len(options) == 4 and correct_answer:
            opt_bodies_check = []
            for o in options:
                body = re.sub(r"^[A-D]:\s*", "", o.strip(), count=1)
                opt_bodies_check.append(body.strip().lower())
            if len(opt_bodies_check) == 4:
                short_threshold = 15
                word_counts = [len(b.split()) for b in opt_bodies_check]
                max_words = max(word_counts) if word_counts else 0
                min_words = min(word_counts) if word_counts else 0
                if max_words <= 3:
                    obvious_distractor_penalty -= 0.25
                short_count = sum(1 for b in opt_bodies_check if len(b) < short_threshold)
                long_count = sum(1 for b in opt_bodies_check if len(b) >= short_threshold)
                if short_count >= 3 and long_count == 1:
                    obvious_distractor_penalty -= 0.15
                if max_words > 0 and (max_words - min_words) >= 8:
                    obvious_distractor_penalty -= 0.10
                absurd_indicators = ["slow", "gpu", "increase exponentially", "become longer",
                                     "unusable", "corrupted", "crashes", "useless", "impossible",
                                     "never", "always", "nothing", "everything"]
                absurd_count = sum(1 for b in opt_bodies_check
                                   if any(ind in b for ind in absurd_indicators))
                if absurd_count >= 2:
                    obvious_distractor_penalty -= 0.15
                correct_idx_ch = ord(correct_answer.strip()[0].upper()) - ord('A') if correct_answer.strip() else -1
                if 0 <= correct_idx_ch < len(opt_bodies_check):
                    correct_body_ch = opt_bodies_check[correct_idx_ch]
                    other_bodies = [b for i, b in enumerate(opt_bodies_check) if i != correct_idx_ch]
                    correct_word_count = len(correct_body_ch.split())
                    other_word_counts = [len(b.split()) for b in other_bodies]
                    avg_other_words = sum(other_word_counts) / len(other_word_counts) if other_word_counts else 0
                    if avg_other_words > 0 and correct_word_count > avg_other_words * 2.0:
                        obvious_distractor_penalty -= 0.10
                    correct_concrete = any(kw in correct_body_ch for kw in
                        ("assign", "define", "specify", "provide", "include", "describe",
                         "explicitly", "clearly", "structure", "detailed"))
                    others_abstract = sum(1 for b in other_bodies if
                        any(kw in b for kw in ("increase", "reduce", "remove", "ignore", "avoid", "omit", "simplify")))
                    if correct_concrete and others_abstract >= 2:
                        obvious_distractor_penalty -= 0.10
                    stem_lower = question_text.lower()
                    scenario_action_words = {"generate", "evaluate", "analyze", "compare", "create",
                                             "design", "build", "write", "improve", "optimize"}
                    scenario_mentioned_actions = [w for w in scenario_action_words if w in stem_lower]
                    if scenario_mentioned_actions and max_words <= 3:
                        obvious_distractor_penalty -= 0.15

        total = (
            concept_coverage + grounding + reasoning + bloom_score +
            distractor_quality + educational_value + clarity +
            ambiguity_penalty + transcript_recall_penalty + speaker_name_penalty +
            definition_only_penalty + keyword_match_penalty +
            component_selection_penalty + obvious_distractor_penalty
        )
        if total >= 0.95:
            has_scenario = any(kw in lower_q for kw in _SCENARIO_KEYWORDS)
            has_reasoning = any(kw in lower_q for kw in _REASONING_KEYWORDS)
            has_high_bloom = bloom_level in ("apply", "analyze", "evaluate")
            if not (has_scenario and has_reasoning and has_high_bloom and distractor_quality >= 0.10):
                total = min(total, 0.90)
        return max(0.0, min(round(total, 3), 1.0))

    def _review_questions(
        self,
        questions: list[GeneratedQuestion],
        chunk_text: str,
        concepts_summary: str,
        chunk_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> list[GeneratedQuestion]:
        if not questions:
            return []

        mcq_json = json.dumps([
            {
                "question_text": q.question_text,
                "question_type": q.question_type,
                "question_style": q.question_style,
                "bloom_level": q.bloom_level,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
            }
            for q in questions
        ], indent=2)

        review_prompt = (
            "Review the following MCQs for BOTH question stem quality AND answer option quality.\n\n"
            f"--- TRANSCRIPT CONTEXT ---\n{chunk_text[:1500]}\n--- END ---\n\n"
            f"--- CONCEPTS ---\n{concepts_summary}\n--- END ---\n\n"
            f"--- MCQs TO REVIEW ---\n{mcq_json}\n--- END ---\n\n"
            "Return ONLY a JSON array. Each element MUST include ALL fields: question_text, question_type, question_style, bloom_level, options (4 options), correct_answer, explanation, difficulty, action, original_question_text, review_reason. Even for 'keep' actions, return all fields."
        )

        try:
            response = self.ollama.generate(
                review_prompt,
                model=model or get_generation_model(self.config),
                system=REVIEW_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=self.config.max_chunk_tokens,
            )
        except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
            logger.warning(
                "educational_review.llm_failed",
                extra={"chunk_id": str(chunk_id) if chunk_id else None, "error": str(exc)},
            )
            return questions

        raw = response.response.strip()
        if not raw:
            return questions

        cleaned = self._strip_thinking_tokens(raw)
        items = self._robust_json_parse(cleaned)

        if items is None:
            logger.warning(
                "educational_review.json_parse_failed",
                extra={"response_preview": cleaned[:300]},
            )
            return questions

        if isinstance(items, dict):
            unwrapped = self._unwrap_dict_response(items, cleaned)
            if unwrapped is not None:
                items = unwrapped
            elif "question_text" in items:
                items = [items]
            else:
                return questions

        if not isinstance(items, list):
            return questions

        reviewed: list[GeneratedQuestion] = []
        rejected_count = 0
        input_by_text: dict[str, GeneratedQuestion] = {}
        for q in questions:
            input_by_text[q.question_text.strip().lower()[:80]] = q
        for item in items:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "keep")).lower().strip()
            original_text = str(item.get("original_question_text", ""))
            reason = str(item.get("review_reason", ""))
            opts = item.get("options", [])
            if isinstance(opts, list):
                opts = [str(o) for o in opts]
            q_text = str(item.get("question_text", ""))
            if action == "reject":
                rejected_count += 1
                logger.info(
                    "educational_review.question_rejected",
                    extra={
                        "chunk_id": str(chunk_id) if chunk_id else None,
                        "question_text": q_text[:100],
                        "review_reason": reason,
                    },
                )
                continue
            if not opts or len(opts) != 4:
                lookup_key = (original_text or q_text).strip().lower()[:80]
                source = input_by_text.get(lookup_key)
                if source and source.options and len(source.options) == 4:
                    if action in ("rewrite", "rewrite_options"):
                        logger.info(
                            "educational_review.options_restored_from_input",
                            extra={
                                "chunk_id": str(chunk_id) if chunk_id else None,
                                "action": action,
                                "reason": "LLM omitted options for rewrite action; restored from input",
                            },
                        )
                    opts = source.options
                else:
                    if action in ("rewrite", "rewrite_options"):
                        logger.warning(
                            "educational_review.rewrite_missing_options",
                            extra={
                                "chunk_id": str(chunk_id) if chunk_id else None,
                                "action": action,
                                "question_text": q_text[:100],
                            },
                        )
                    continue
            if action not in ("keep", "rewrite_options", "rewrite"):
                action = "keep"
            is_options_rewrite = action == "rewrite_options"
            is_full_rewrite = action == "rewrite"
            try:
                reviewed.append(
                    GeneratedQuestion(
                        question_text=q_text if q_text else (original_text or ""),
                        question_type=str(item.get("question_type", "mcq")),
                        question_style=str(item.get("question_style", "concept_understanding")),
                        bloom_level=str(item.get("bloom_level", "understand")),
                        options=opts,
                        correct_answer=str(item.get("correct_answer", "")),
                        explanation=str(item.get("explanation", "")),
                        difficulty=str(item.get("difficulty", "medium")),
                        chunk_id=chunk_id,
                        rewritten=is_full_rewrite,
                        options_rewritten=is_options_rewrite,
                        original_question_text=original_text if (is_full_rewrite or is_options_rewrite) else None,
                        review_reason=reason if reason else None,
                    )
                )
            except Exception:
                continue

        logger.info(
            "educational_review.completed",
            extra={
                "chunk_id": str(chunk_id) if chunk_id else None,
                "input_count": len(questions),
                "reviewed_count": len(reviewed),
                "rewrites": sum(1 for q in reviewed if q.rewritten),
                "options_rewrites": sum(1 for q in reviewed if q.options_rewritten),
                "rejected": rejected_count,
            },
        )
        return reviewed if reviewed else questions

    def generate_questions_from_chunk(
        self,
        chunk_text: str,
        chunk_id: uuid.UUID | None = None,
        *,
        num_questions: int | None = None,
        model: str | None = None,
    ) -> QuestionGenerationResult:
        if not chunk_text or not chunk_text.strip():
            logger.warning(
                "question_generation.empty_chunk",
                extra={"chunk_id": str(chunk_id) if chunk_id else None},
            )
            return QuestionGenerationResult(
                transcript_id=uuid.uuid4(),
                meeting_id=uuid.uuid4(),
                questions=[],
                total_questions=0,
                model_used=model or get_generation_model(self.config),
            )

        word_count = len(chunk_text.split())

        if num_questions is not None:
            target_count = num_questions
        else:
            target_count = self._compute_question_count(word_count)

        target_count = max(self._MIN_QUESTIONS_PER_CHUNK, min(target_count, self._MAX_QUESTIONS_PER_CHUNK))

        final_questions: list[GeneratedQuestion] = []
        final_response: GenerationResponse | None = None

        concepts = self._extract_concepts(chunk_text, chunk_id, model=model)
        concepts_summary = self._build_concepts_summary(concepts)

        for attempt_target in [target_count, max(target_count - 1, 2), 2]:
            prompt = (
                f"Generate {attempt_target} MCQs from the educational concepts below.\n\n"
                f"--- TRANSCRIPT ---\n{chunk_text}\n--- END ---\n\n"
                f"--- CONCEPTS ---\n{concepts_summary}\n--- END ---\n\n"
                f"Return ONLY a JSON array of {attempt_target} question objects. No other text."
            )

            logger.info(
                "question_generation.started",
                extra={
                    "chunk_id": str(chunk_id) if chunk_id else None,
                    "word_count": word_count,
                    "target_question_count": attempt_target,
                    "chunk_length": len(chunk_text),
                    "prompt_length": len(prompt),
                },
            )

            try:
                response = self.ollama.generate(
                    prompt,
                    model=model or get_generation_model(self.config),
                    system=MCQ_SYSTEM_PROMPT,
                    temperature=0.7,
                    max_tokens=self.config.max_chunk_tokens,
                )
            except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
                logger.exception(
                    "question_generation.llm_failed",
                    extra={
                        "chunk_id": str(chunk_id) if chunk_id else None,
                        "error": str(exc),
                    },
                )
                raise QuestionGenerationError(f"LLM generation failed: {exc}") from exc

            questions = self._parse_questions(response, chunk_id)

            if questions:
                final_questions = questions
                final_response = response
                break

            raw = response.response.strip()
            is_llm_error = False
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "error" in parsed:
                    is_llm_error = True
                    logger.warning(
                        "question_generation.llm_returned_error_retrying",
                        extra={
                            "chunk_id": str(chunk_id) if chunk_id else None,
                            "error_msg": str(parsed["error"])[:200],
                            "retrying_with_target": max(attempt_target - 1, 2) if attempt_target > 2 else None,
                        },
                    )
            except json.JSONDecodeError:
                pass

            final_response = response

        if final_questions:
            reviewed = self._review_questions(
                final_questions, chunk_text, concepts_summary, chunk_id, model=model,
            )
            scored: list[GeneratedQuestion] = []
            for q in reviewed:
                edu_score = self.compute_educational_score(
                    question_text=q.question_text,
                    explanation=q.explanation,
                    options=q.options,
                    correct_answer=q.correct_answer,
                    difficulty=q.difficulty,
                    question_style=q.question_style,
                    bloom_level=q.bloom_level,
                    chunk_text=chunk_text,
                )
                scored.append(
                    GeneratedQuestion(
                        question_text=q.question_text,
                        question_type=q.question_type,
                        question_style=q.question_style,
                        bloom_level=q.bloom_level,
                        options=q.options,
                        correct_answer=q.correct_answer,
                        explanation=q.explanation,
                        difficulty=q.difficulty,
                        chunk_id=chunk_id,
                        educational_score=edu_score,
                        rewritten=q.rewritten,
                        options_rewritten=q.options_rewritten,
                        original_question_text=q.original_question_text,
                        review_reason=q.review_reason,
                    )
                )
            final_questions = scored

        logger.info(
            "question_generation.completed",
            extra={
                "chunk_id": str(chunk_id) if chunk_id else None,
                "questions_generated": len(final_questions),
                "rewrites": sum(1 for q in final_questions if q.rewritten),
                "options_rewrites": sum(1 for q in final_questions if q.options_rewritten),
                "avg_educational_score": (
                    round(sum(q.educational_score for q in final_questions if q.educational_score is not None) / len([q for q in final_questions if q.educational_score is not None]), 3)
                    if any(q.educational_score is not None for q in final_questions) else None
                ),
                "model_used": final_response.model if final_response else None,
                "prompt_tokens": final_response.prompt_tokens if final_response else None,
                "completion_tokens": final_response.completion_tokens if final_response else None,
                "duration_seconds": final_response.total_duration_seconds if final_response else None,
            },
        )

        return QuestionGenerationResult(
            transcript_id=uuid.uuid4(),
            meeting_id=uuid.uuid4(),
            questions=final_questions,
            total_questions=len(final_questions),
            model_used=final_response.model if final_response else (model or get_generation_model(self.config)),
            total_prompt_tokens=final_response.prompt_tokens if final_response else None,
            total_completion_tokens=final_response.completion_tokens if final_response else None,
            total_duration_seconds=final_response.total_duration_seconds if final_response else None,
        )

    def _parse_questions(
        self,
        response: GenerationResponse,
        chunk_id: uuid.UUID | None = None,
    ) -> list[GeneratedQuestion]:
        raw = response.response.strip()
        if not raw:
            logger.warning("question_generation.empty_response")
            return []

        cleaned = self._strip_thinking_tokens(raw)

        items = self._robust_json_parse(cleaned)
        if items is None:
            logger.warning(
                "question_generation.json_parse_failed_all_methods",
                extra={"response_preview": cleaned[:500]},
            )
            return []

        if isinstance(items, dict):
            if self._is_json_schema(items):
                logger.warning(
                    "question_generation.llm_returned_json_schema",
                    extra={"response_preview": cleaned[:500]},
                )
                return []
            unwrapped = self._unwrap_dict_response(items, cleaned)
            if unwrapped is not None:
                items = unwrapped
            elif "question_text" in items:
                items = [items]
            elif "question" in items:
                items = [items]
            else:
                logger.warning(
                    "question_generation.unexpected_dict_shape",
                    extra={"dict_keys": list(items.keys()), "response_preview": cleaned[:500]},
                )
                return []

        if not isinstance(items, list):
            logger.warning(
                "question_generation.unexpected_response_format",
                extra={
                    "response_preview": cleaned[:500],
                    "parsed_type": type(items).__name__,
                },
            )
            return []

        questions: list[GeneratedQuestion] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                questions.append(
                    GeneratedQuestion(
                        question_text=str(item.get("question_text", "")),
                        question_type=str(item.get("question_type", "mcq")),
                        question_style=str(item.get("question_style", "concept_understanding")),
                        bloom_level=str(item.get("bloom_level", "understand")),
                        options=list(item.get("options", [])),
                        correct_answer=str(item.get("correct_answer", "")),
                        explanation=str(item.get("explanation", "")),
                        difficulty=str(item.get("difficulty", "medium")),
                        chunk_id=chunk_id,
                    )
                )
            except Exception:
                logger.warning(
                    "question_generation.question_parse_skipped",
                    extra={"item": str(item)[:100]},
                )
                continue

        return questions

    @staticmethod
    def _strip_thinking_tokens(text: str) -> str:
        stripped = _THINKING_RE.sub("", text).strip()
        if stripped != text.strip():
            logger.debug(
                "question_generation.thinking_tokens_stripped",
                extra={"original_len": len(text), "cleaned_len": len(stripped)},
            )
        return stripped

    @staticmethod
    def _is_json_schema(data: dict) -> bool:
        keys = set(data.keys())
        overlap = keys & _JSON_SCHEMA_KEYS
        return len(overlap) >= 2 or "$schema" in keys

    @staticmethod
    def _robust_json_parse(text: str) -> list | dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        return QuestionService._extract_balanced_json(text)

    @staticmethod
    def _extract_balanced_json(text: str) -> list | dict | None:
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

    _KNOWN_WRAPPER_KEYS = ("questions", "mcq_questions", "concepts", "items", "result", "results", "data")

    def _unwrap_dict_response(self, data: dict, raw: str) -> list | None:
        for key in self._KNOWN_WRAPPER_KEYS:
            if key in data and isinstance(data[key], list):
                logger.info(
                    "question_generation.dict_unwrapped",
                    extra={"wrapper_key": key, "item_count": len(data[key])},
                )
                return data[key]

        list_keys = [k for k, v in data.items() if isinstance(v, list)]
        if len(list_keys) == 1:
            logger.info(
                "question_generation.dict_auto_unwrapped",
                extra={"wrapper_key": list_keys[0], "item_count": len(data[list_keys[0]])},
            )
            return data[list_keys[0]]

        if "error" in data:
            logger.warning(
                "question_generation.llm_returned_error",
                extra={"error": str(data["error"])[:200]},
            )
            return None

        logger.warning(
            "question_generation.unexpected_response_format",
            extra={
                "response_preview": raw[:500],
                "dict_keys": list(data.keys()),
                "list_valued_keys": list_keys,
            },
        )
        return None


def _contains_name_reference(text: str) -> bool:
    lower = text.lower()
    patterns = [
        r"\b[A-Z][a-z]+\s+(said|asked|proposed|mentioned|agreed|decided|requested|stated|shared|announced|reported|presented|noted)\b",
        r"\b(does|did|will|would|should|can|could)\s+the\s+speaker\b",
    ]
    for p in patterns:
        if re.search(p, text):
            return True
    return False


@dataclass(frozen=True)
class RegenerateResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    previous_count: int
    new_count: int
    chunks_processed: int
    duplicates_removed: int
    classified: int
    ranked: int
    model_used: str
    aborted: bool = False
    abort_reason: str | None = None


_COVERAGE_RATIO_THRESHOLD = 0.5


def regenerate_mcqs_for_transcript(
    db: "Session",
    transcript_id: uuid.UUID,
    *,
    config: Settings = settings,
) -> RegenerateResult:
    from sqlalchemy import select, func as sa_func

    from app.db.models.question import Question
    from app.db.models.transcript_chunk import TranscriptChunk
    from app.db.models.transcript import Transcript
    from app.db.repositories import questions as question_repo
    from app.services.classification_service import ClassificationService
    from app.workflows.dedup import deduplicate_questions
    from app.workflows.state import QuestionData

    logger.info(
        "regenerate_mcqs.started",
        extra={"transcript_id": str(transcript_id)},
    )

    transcript = db.get(Transcript, transcript_id)
    if transcript is None:
        raise QuestionGenerationError(f"Transcript not found: {transcript_id}")

    meeting_id = transcript.meeting_id

    previous_count = db.scalar(
        select(sa_func.count()).select_from(Question).where(Question.transcript_id == transcript_id)
    ) or 0

    chunk_rows = db.scalars(
        select(TranscriptChunk)
        .where(TranscriptChunk.transcript_id == transcript_id)
        .order_by(TranscriptChunk.chunk_index)
    ).all()

    if not chunk_rows:
        raise QuestionGenerationError(f"No chunks found for transcript {transcript_id}")

    service = QuestionService(config=config)

    all_questions: list[QuestionData] = []

    for chunk_row in chunk_rows:
        chunk_text = chunk_row.text
        if not chunk_text or not chunk_text.strip():
            continue

        try:
            result = service.generate_questions_from_chunk(
                chunk_text=chunk_text,
                chunk_id=chunk_row.chunk_id,
                model=get_generation_model(config),
            )
        except Exception as exc:
            logger.warning(
                "regenerate_mcqs.chunk_generation_failed",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunk_index": chunk_row.chunk_index,
                    "error": str(exc),
                },
            )
            continue

        for q in result.questions:
            all_questions.append(
                QuestionData(
                    question_text=q.question_text,
                    question_type=q.question_type,
                    question_style=q.question_style,
                    options=q.options,
                    correct_answer=q.correct_answer,
                    explanation=q.explanation,
                    difficulty=q.difficulty,
                    chunk_id=chunk_row.chunk_id,
                    chunk_index=chunk_row.chunk_index,
                    category=q.question_style,
                    bloom_taxonomy=q.bloom_level,
                    educational_score=q.educational_score,
                )
            )

    if not all_questions:
        return RegenerateResult(
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            previous_count=previous_count,
            new_count=0,
            chunks_processed=len(chunk_rows),
            duplicates_removed=0,
            classified=0,
            ranked=0,
            model_used=get_generation_model(config),
            aborted=True,
            abort_reason="Zero questions generated — preserving existing MCQs",
        )

    valid: list[QuestionData] = []
    for q in all_questions:
        errors: list[str] = []
        if not q.question_text or len(q.question_text.strip()) < 10:
            errors.append("question_text too short")
        if not q.options or len(q.options) != 4:
            errors.append(f"expected 4 options, got {len(q.options) if q.options else 0}")
        if not q.correct_answer or q.correct_answer.strip()[0].upper() not in "ABCD":
            errors.append("invalid correct_answer")
        if not q.explanation or len(q.explanation.strip()) < 5:
            errors.append("explanation too short")
        if q.difficulty not in ("easy", "medium", "hard"):
            errors.append(f"invalid difficulty: {q.difficulty}")
        q.validation_passed = len(errors) == 0
        q.validation_errors = errors
        if q.validation_passed:
            valid.append(q)

    if not valid:
        return RegenerateResult(
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            previous_count=previous_count,
            new_count=0,
            chunks_processed=len(chunk_rows),
            duplicates_removed=0,
            classified=0,
            ranked=0,
            model_used=get_generation_model(config),
            aborted=True,
            abort_reason="Zero valid questions after validation — preserving existing MCQs",
        )

    unique, duplicates_removed = deduplicate_questions(valid)

    if not unique:
        return RegenerateResult(
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            previous_count=previous_count,
            new_count=0,
            chunks_processed=len(chunk_rows),
            duplicates_removed=duplicates_removed,
            classified=0,
            ranked=0,
            model_used=get_generation_model(config),
            aborted=True,
            abort_reason="Zero unique questions after dedup — preserving existing MCQs",
        )

    if previous_count > 0 and len(unique) < previous_count * _COVERAGE_RATIO_THRESHOLD:
        return RegenerateResult(
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            previous_count=previous_count,
            new_count=len(unique),
            chunks_processed=len(chunk_rows),
            duplicates_removed=duplicates_removed,
            classified=0,
            ranked=0,
            model_used=get_generation_model(config),
            aborted=True,
            abort_reason=f"Coverage drop too large: {len(unique)} new vs {previous_count} previous (below {_COVERAGE_RATIO_THRESHOLD:.0%} threshold) — preserving existing MCQs",
        )

    try:
        question_repo.delete_by_transcript_id(db, transcript_id)
        question_repo.bulk_insert_questions(
            db,
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            questions=unique,
        )
        db.flush()
    except Exception as exc:
        db.rollback()
        logger.exception(
            "regenerate_mcqs.db_write_failed",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise QuestionGenerationError(f"Database write failed during regeneration: {exc}") from exc

    classification_service = ClassificationService(db)
    classified = 0
    try:
        classified = classification_service.classify_questions(transcript_id)
        db.flush()
    except Exception as exc:
        db.rollback()
        logger.exception(
            "regenerate_mcqs.classification_failed",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise QuestionGenerationError(f"Classification failed during regeneration: {exc}") from exc

    ranked = 0
    try:
        rank_result = classification_service.recompute_rankings(transcript_id)
        ranked = rank_result.get("questions_rescored", 0)
        db.flush()
    except Exception as exc:
        db.rollback()
        logger.exception(
            "regenerate_mcqs.ranking_failed",
            extra={"transcript_id": str(transcript_id), "error": str(exc)},
        )
        raise QuestionGenerationError(f"Ranking failed during regeneration: {exc}") from exc

    final_count = db.scalar(
        select(sa_func.count()).select_from(Question).where(Question.transcript_id == transcript_id)
    ) or 0

    logger.info(
        "regenerate_mcqs.completed",
        extra={
            "transcript_id": str(transcript_id),
            "previous_count": previous_count,
            "new_count": final_count,
            "chunks_processed": len(chunk_rows),
            "duplicates_removed": duplicates_removed,
            "classified": classified,
            "ranked": ranked,
        },
    )

    return RegenerateResult(
        transcript_id=transcript_id,
        meeting_id=meeting_id,
        previous_count=previous_count,
        new_count=final_count,
        chunks_processed=len(chunk_rows),
        duplicates_removed=duplicates_removed,
        classified=classified,
        ranked=ranked,
        model_used=get_generation_model(config),
    )


@dataclass(frozen=True)
class PreviewMcqItem:
    question_text: str
    question_style: str
    bloom_level: str
    options: list[str]
    correct_answer: str
    explanation: str
    difficulty: str
    educational_score: float | None = None
    chunk_index: int | None = None


@dataclass(frozen=True)
class PreviewResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    previous_count: int
    regenerated_count: int
    chunks_processed: int
    duplicates_removed: int
    questions: list[PreviewMcqItem]
    model_used: str


def preview_regenerate_mcqs(
    db: "Session",
    transcript_id: uuid.UUID,
    *,
    config: Settings = settings,
) -> PreviewResult:
    from sqlalchemy import select, func as sa_func

    from app.db.models.question import Question
    from app.db.models.transcript_chunk import TranscriptChunk
    from app.db.models.transcript import Transcript
    from app.workflows.dedup import deduplicate_questions
    from app.workflows.state import QuestionData

    logger.info(
        "preview_regenerate.started",
        extra={"transcript_id": str(transcript_id)},
    )

    transcript = db.get(Transcript, transcript_id)
    if transcript is None:
        raise QuestionGenerationError(f"Transcript not found: {transcript_id}")

    meeting_id = transcript.meeting_id

    previous_count = db.scalar(
        select(sa_func.count()).select_from(Question).where(Question.transcript_id == transcript_id)
    ) or 0

    chunk_rows = db.scalars(
        select(TranscriptChunk)
        .where(TranscriptChunk.transcript_id == transcript_id)
        .order_by(TranscriptChunk.chunk_index)
    ).all()

    if not chunk_rows:
        raise QuestionGenerationError(f"No chunks found for transcript {transcript_id}")

    service = QuestionService(config=config)

    all_questions: list[QuestionData] = []

    for chunk_row in chunk_rows:
        chunk_text = chunk_row.text
        if not chunk_text or not chunk_text.strip():
            continue

        try:
            result = service.generate_questions_from_chunk(
                chunk_text=chunk_text,
                chunk_id=chunk_row.chunk_id,
                model=get_generation_model(config),
            )
        except Exception as exc:
            logger.warning(
                "preview_regenerate.chunk_failed",
                extra={
                    "transcript_id": str(transcript_id),
                    "chunk_index": chunk_row.chunk_index,
                    "error": str(exc),
                },
            )
            continue

        for q in result.questions:
            all_questions.append(
                QuestionData(
                    question_text=q.question_text,
                    question_type=q.question_type,
                    question_style=q.question_style,
                    options=q.options,
                    correct_answer=q.correct_answer,
                    explanation=q.explanation,
                    difficulty=q.difficulty,
                    chunk_id=chunk_row.chunk_id,
                    chunk_index=chunk_row.chunk_index,
                    category=q.question_style,
                    bloom_taxonomy=q.bloom_level,
                    educational_score=q.educational_score,
                )
            )

    valid: list[QuestionData] = []
    for q in all_questions:
        errors: list[str] = []
        if not q.question_text or len(q.question_text.strip()) < 10:
            errors.append("question_text too short")
        if not q.options or len(q.options) != 4:
            errors.append(f"expected 4 options, got {len(q.options) if q.options else 0}")
        if not q.correct_answer or q.correct_answer.strip()[0].upper() not in "ABCD":
            errors.append("invalid correct_answer")
        if not q.explanation or len(q.explanation.strip()) < 5:
            errors.append("explanation too short")
        if q.difficulty not in ("easy", "medium", "hard"):
            errors.append(f"invalid difficulty: {q.difficulty}")
        q.validation_passed = len(errors) == 0
        q.validation_errors = errors
        if q.validation_passed:
            valid.append(q)

    unique, duplicates_removed = deduplicate_questions(valid)

    preview_items: list[PreviewMcqItem] = []
    for q in unique:
        preview_items.append(
            PreviewMcqItem(
                question_text=q.question_text,
                question_style=q.question_style,
                bloom_level=q.bloom_taxonomy or "understand",
                options=q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                difficulty=q.difficulty,
                chunk_index=q.chunk_index,
            )
        )

    logger.info(
        "preview_regenerate.completed",
        extra={
            "transcript_id": str(transcript_id),
            "previous_count": previous_count,
            "regenerated_count": len(preview_items),
            "chunks_processed": len(chunk_rows),
        },
    )

    return PreviewResult(
        transcript_id=transcript_id,
        meeting_id=meeting_id,
        previous_count=previous_count,
        regenerated_count=len(preview_items),
        chunks_processed=len(chunk_rows),
        duplicates_removed=duplicates_removed,
        questions=preview_items,
        model_used=get_generation_model(config),
    )
