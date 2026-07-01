"""Professor Ranking Service — domain-independent pure-deterministic question ranking.

Approximates how an experienced professor / corporate trainer / SME would
manually select the best educational questions from a meeting transcript.

Pipeline:
  1. Compute Composite Educational Score (from existing metadata only)
  2. Remove Near-Duplicate Questions (keep strongest representative)
  3. Apply Concept Diversity (MMR-inspired greedy selection)
  4. Apply Meeting Coverage Balancing (chunk spreading penalty)
  5. Produce ONE final ranked list → Top-10 ⊂ Top-20 ⊂ Top-50 ⊂ All

No LLM calls. No domain assumptions. No database writes. Pure metadata-driven.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.question import Question
from app.db.models.transcript_chunk import TranscriptChunk

logger = get_logger(__name__)

_BLOOM_ORDER = {"remember": 0, "understand": 1, "apply": 2, "analyze": 3, "evaluate": 4}

_BLOOM_COMPOSITE_VALUE = {"remember": 0.05, "understand": 0.20, "apply": 0.50, "analyze": 0.80, "evaluate": 1.00}

_STYLE_WEIGHTS = {
    "scenario_based": 1.0,
    "decision_making": 0.95,
    "application": 0.90,
    "best_practice": 0.85,
    "cause_effect": 0.80,
    "comparison": 0.75,
    "analysis": 0.70,
    "concept_understanding": 0.55,
}

_REASONING_PHRASES = frozenset({
    "why does", "how does", "what causes", "what leads to",
    "what prevents", "which principle explains", "what is the main reason",
    "which approach is best", "what would happen if",
    "most likely", "most appropriate", "best explains",
    "primary reason", "key factor", "which strategy",
    "which modification would most", "which decision would best",
    "which explanation best", "most effectively",
    "trade-off", "implication", "consequence",
    "what is the primary advantage", "what is the main disadvantage",
})


@dataclass(frozen=True)
class _QEntry:
    question_id: uuid.UUID
    question_text: str
    explanation: str
    options: list[str]
    correct_answer: str
    bloom_level: str
    category: str
    difficulty: str
    educational_score: float
    chunk_index: int | None
    composite_score: float = 0.0
    reasoning_score: float = 0.0
    option_quality: float = 0.5
    style_weight: float = 0.55


@dataclass
class RankedQuestion:
    question_id: uuid.UUID
    rank: int
    composite_score: float
    question_text: str
    explanation: str
    bloom_level: str
    category: str
    difficulty: str
    educational_score: float
    chunk_index: int | None
    rank_reasons: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)


@dataclass
class RankingResult:
    transcript_id: uuid.UUID
    total_questions: int
    ranked: list[RankedQuestion]
    top_10: list[RankedQuestion]
    top_20: list[RankedQuestion]
    top_50: list[RankedQuestion]
    concept_coverage: dict
    hierarchy_verified: bool


def _normalize(text: str) -> str:
    n = text.lower().strip()
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"[^\w\s]", "", n)
    return n


def _extract_key_phrases(text: str) -> set[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    stop = frozenset({
        "that", "this", "which", "what", "where", "when", "how", "why",
        "does", "would", "should", "could", "their", "these", "those",
        "about", "other", "being", "having", "some", "than", "them",
        "then", "also", "into", "from", "with", "such", "each", "will",
        "most", "more", "over", "only", "very", "just", "because",
        "following", "between", "through", "during", "before", "after",
        "another", "however", "therefore", "although", "whereas",
    })
    return set(w for w in words if w not in stop)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _compute_option_quality(options: list[str], correct_answer: str) -> float:
    if not options or len(options) != 4 or not correct_answer:
        return 0.3

    opt_bodies = []
    for o in options:
        body = re.sub(r"^[A-D]:\s*", "", o.strip(), count=1)
        opt_bodies.append(body.strip())

    lengths = [len(b) for b in opt_bodies]
    words = [len(b.split()) for b in opt_bodies]
    if not lengths:
        return 0.3

    max_len = max(lengths)
    min_len = min(lengths)

    quality = 0.5

    if max_len > 0:
        ratio = (max_len - min_len) / max_len
        if ratio > 0.7:
            quality -= 0.30
        elif ratio > 0.5:
            quality -= 0.15

    correct_idx = ord(correct_answer.strip()[0].upper()) - ord("A")
    if 0 <= correct_idx < 4:
        correct_len = lengths[correct_idx]
        non_correct = [lengths[i] for i in range(4) if i != correct_idx]
        if non_correct and correct_len > 0:
            avg_other = sum(non_correct) / len(non_correct)
            if avg_other > 0 and correct_len > avg_other * 1.8:
                quality -= 0.25
            elif avg_other > 0 and correct_len > avg_other * 1.4:
                quality -= 0.12

    single_word_count = sum(1 for b in opt_bodies if len(b.split()) <= 2)
    if single_word_count >= 3:
        quality -= 0.30
    elif single_word_count >= 2:
        quality -= 0.15

    absurd = ("slow", "gpu", "increase exponentially", "unusable", "corrupted",
              "crashes", "useless", "impossible", "never", "always", "nothing")
    if sum(1 for b in opt_bodies if any(a in b.lower() for a in absurd)) >= 2:
        quality -= 0.20

    if max(words) - min(words) >= 8:
        quality -= 0.10

    if 0 <= correct_idx < 4:
        correct_body = opt_bodies[correct_idx].lower()
        specificity = sum(1 for kw in ("specify", "explicitly", "clearly define",
                                       "assign", "structure", "detailed")
                         if kw in correct_body)
        other_abstract = sum(1 for i in range(4) if i != correct_idx
                             for kw in ("increase", "reduce", "remove", "ignore", "avoid")
                             if kw in opt_bodies[i].lower())
        if specificity > 0 and other_abstract >= 2:
            quality -= 0.15

    return max(0.0, min(quality, 1.0))


_TRANSCRIPT_RECALL_PATTERNS = frozenset({
    "according to the transcript",
    "according to the speaker",
    "what example was given",
    "what example is given",
    "what was mentioned",
    "what did the speaker",
    "how does the speaker",
    "why does the speaker",
    "what does the speaker",
    "what is the speaker",
    "in the example given",
    "in the example provided",
    "as mentioned in the",
    "as described in the",
    "as stated in the",
    "what was discussed",
    "what was the main topic",
})


def _compute_transcript_recall_penalty(question_text: str) -> float:
    lower = question_text.lower().strip()
    hit = sum(1 for p in _TRANSCRIPT_RECALL_PATTERNS if p in lower)
    return min(0.20, 0.10 * hit)


_BLOOM_REASONING_FLOOR = {"remember": 0.0, "understand": 0.15, "apply": 0.40, "analyze": 0.70, "evaluate": 0.85}


def _compute_effective_reasoning(
    text_reasoning: float, bloom_level: str, is_transcript_recall: bool,
) -> float:
    bloom_floor = _BLOOM_REASONING_FLOOR.get(bloom_level, 0.0)
    effective = max(text_reasoning, bloom_floor)
    if is_transcript_recall:
        effective = min(effective, 0.30)
    return effective


def _compute_reasoning_score(question_text: str) -> float:
    lower = question_text.lower()

    for phrase in _REASONING_PHRASES:
        if phrase in lower:
            return 1.0

    strong_reasoning = (
        "compare", "contrast", "distinguish", "differentiate",
        "evaluate", "judge", "assess", "critique",
        "design", "propose", "recommend", "devise",
        "predict", "forecast", "estimate",
        "optimize", "improve", "refine",
    )
    if any(kw in lower for kw in strong_reasoning):
        return 0.8

    moderate_reasoning = (
        "how does", "how can", "how would", "how should",
        "why is", "why does", "why would", "why should",
        "what if", "what would happen",
        "what changes", "what factors",
        "which approach", "which method", "which strategy",
        "under what conditions",
    )
    if any(kw in lower for kw in moderate_reasoning):
        return 0.6

    light_reasoning = ("how", "why", "explain", "describe the relationship")
    if any(kw in lower for kw in light_reasoning):
        return 0.3

    return 0.0


def _compute_composite(entry: _QEntry, recall_penalty: float = 0.0) -> float:
    edu = max(0.0, min(entry.educational_score, 1.0))
    bloom_val = _BLOOM_COMPOSITE_VALUE.get(entry.bloom_level, 0.20)

    composite = (
        0.25 * edu
        + 0.30 * bloom_val
        + 0.25 * entry.reasoning_score
        + 0.10 * entry.option_quality
        + 0.10 * entry.style_weight
    )

    composite -= recall_penalty

    return round(max(0.0, min(composite, 1.0)), 4)


def _answer_option_text(answer: str | None, options: list[str]) -> str:
    if not answer or not options:
        return ""
    letter = answer.strip().upper()[0] if answer.strip() else ""
    if not letter:
        return ""
    for opt in options:
        opt_stripped = opt.strip()
        if opt_stripped and opt_stripped[0].upper() == letter:
            return opt_stripped
    return ""


def _entries_same_learning_objective(a: _QEntry, b: _QEntry) -> bool:
    phrases_a = _extract_key_phrases(f"{a.question_text} {a.explanation}")
    phrases_b = _extract_key_phrases(f"{b.question_text} {b.explanation}")

    text_sim = _jaccard(phrases_a, phrases_b)
    if text_sim < 0.30:
        return False

    same_bloom = (a.bloom_level == b.bloom_level)
    same_bloom_tier = (
        _BLOOM_ORDER.get(a.bloom_level, 1) // 2
        == _BLOOM_ORDER.get(b.bloom_level, 1) // 2
    )

    reasoning_a = a.reasoning_score if a.reasoning_score is not None else _compute_reasoning_score(a.question_text)
    reasoning_b = b.reasoning_score if b.reasoning_score is not None else _compute_reasoning_score(b.question_text)
    same_reasoning_tier = abs(reasoning_a - reasoning_b) < 0.4

    cat_a = a.category or ""
    cat_b = b.category or ""
    same_category = (cat_a == cat_b)

    opts_sim = _jaccard(
        _extract_key_phrases(" ".join(a.options)),
        _extract_key_phrases(" ".join(b.options)),
    )

    correct_overlap = False
    ca_text = _answer_option_text(a.correct_answer, a.options)
    cb_text = _answer_option_text(b.correct_answer, b.options)
    if ca_text and cb_text:
        ca_phrases = _extract_key_phrases(ca_text)
        cb_phrases = _extract_key_phrases(cb_text)
        correct_overlap = _jaccard(ca_phrases, cb_phrases) >= 0.40

    edu_signals = sum([same_bloom, same_reasoning_tier, same_category, correct_overlap])

    if text_sim >= 0.70 and same_bloom and same_reasoning_tier and correct_overlap:
        return True

    if text_sim >= 0.70 and same_bloom and same_reasoning_tier and opts_sim >= 0.50:
        return True

    if text_sim >= 0.55 and same_bloom and same_reasoning_tier and same_category and correct_overlap:
        return True

    if text_sim >= 0.55 and same_bloom_tier and same_reasoning_tier and opts_sim >= 0.50 and correct_overlap:
        return True

    if text_sim >= 0.40 and same_bloom and same_reasoning_tier and same_category and correct_overlap:
        return True

    if text_sim >= 0.30 and edu_signals >= 4:
        return True

    if text_sim >= 0.35 and edu_signals >= 3 and opts_sim >= 0.35 and correct_overlap:
        return True

    return False


def _is_stronger(rep: _QEntry, candidate: _QEntry) -> bool:
    if rep.composite_score != candidate.composite_score:
        return rep.composite_score > candidate.composite_score
    rep_bloom = _BLOOM_ORDER.get(rep.bloom_level, 1)
    cand_bloom = _BLOOM_ORDER.get(candidate.bloom_level, 1)
    if rep_bloom != cand_bloom:
        return rep_bloom > cand_bloom
    if rep.option_quality != candidate.option_quality:
        return rep.option_quality > candidate.option_quality
    if rep.reasoning_score != candidate.reasoning_score:
        return rep.reasoning_score > candidate.reasoning_score
    if rep.educational_score != candidate.educational_score:
        return rep.educational_score > candidate.educational_score
    return True


def _deduplicate(entries: list[_QEntry]) -> list[_QEntry]:
    if not entries:
        return []

    groups: list[list[int]] = []
    assigned: set[int] = set()

    for i in range(len(entries)):
        if i in assigned:
            continue
        group = [i]
        assigned.add(i)
        for j in range(i + 1, len(entries)):
            if j in assigned:
                continue
            if _entries_same_learning_objective(entries[i], entries[j]):
                group.append(j)
                assigned.add(j)
        groups.append(group)

    result: list[_QEntry] = []
    for group in groups:
        best_idx = group[0]
        for idx in group[1:]:
            if _is_stronger(entries[idx], entries[best_idx]):
                best_idx = idx
        result.append(entries[best_idx])

    return result


def _greedy_diverse_rank(
    entries: list[_QEntry],
    total_chunks: int,
) -> list[RankedQuestion]:
    if not entries:
        return []

    scored = sorted(entries, key=lambda e: e.composite_score, reverse=True)

    selected: list[int] = []
    selected_phrases: list[set[str]] = []
    selected_chunk_counts: dict[int | None, int] = {}
    used: set[int] = set()

    chunk_limit = max(1, math.ceil(len(scored) / max(total_chunks, 1)) + 1) if total_chunks > 1 else len(scored)

    remaining = list(range(len(scored)))

    while remaining and len(selected) < len(scored):
        best_idx = -1
        best_score = -float("inf")

        for idx in remaining:
            if idx in used:
                continue

            entry = scored[idx]
            phrases = _extract_key_phrases(f"{entry.question_text} {entry.explanation}")

            redundancy = 0.0
            if selected_phrases:
                redundancy = max(_jaccard(phrases, sp) for sp in selected_phrases)

            chunk = entry.chunk_index
            chunk_penalty = 0.0
            if chunk is not None and total_chunks > 1:
                current_count = selected_chunk_counts.get(chunk, 0)
                if current_count >= chunk_limit:
                    chunk_penalty = 0.08 * (current_count - chunk_limit + 1)

            diversity_bonus = 0.0
            if selected_phrases and redundancy < 0.15:
                diversity_bonus = 0.03

            effective = (
                0.60 * entry.composite_score
                - 0.32 * redundancy
                - chunk_penalty
                + diversity_bonus
            )

            if effective > best_score:
                best_score = effective
                best_idx = idx

        if best_idx == -1:
            break

        entry = scored[best_idx]
        selected.append(best_idx)
        selected_phrases.append(
            _extract_key_phrases(f"{entry.question_text} {entry.explanation}")
        )
        chunk = entry.chunk_index
        selected_chunk_counts[chunk] = selected_chunk_counts.get(chunk, 0) + 1
        used.add(best_idx)
        remaining = [i for i in remaining if i not in used]

    ranked: list[RankedQuestion] = []
    for rank_pos, idx in enumerate(selected, start=1):
        entry = scored[idx]
        concepts = sorted(_extract_key_phrases(f"{entry.question_text} {entry.explanation}"))[:5]
        reasons = _build_rank_reasons(entry, rank_pos)

        ranked.append(RankedQuestion(
            question_id=entry.question_id,
            rank=rank_pos,
            composite_score=entry.composite_score,
            question_text=entry.question_text,
            explanation=entry.explanation,
            bloom_level=entry.bloom_level,
            category=entry.category,
            difficulty=entry.difficulty,
            educational_score=entry.educational_score,
            chunk_index=entry.chunk_index,
            rank_reasons=reasons,
            concepts=concepts,
        ))

    return ranked


def _build_rank_reasons(entry: _QEntry, rank: int) -> list[str]:
    reasons: list[str] = []

    if entry.educational_score >= 0.6:
        reasons.append(f"High educational score ({entry.educational_score:.2f})")
    bloom_val = _BLOOM_ORDER.get(entry.bloom_level, 0)
    if bloom_val >= 2:
        reasons.append(f"Higher-order Bloom: {entry.bloom_level}")
    if entry.reasoning_score >= 0.5:
        reasons.append("Requires reasoning")
    if entry.option_quality >= 0.5:
        reasons.append(f"Strong distractors (quality={entry.option_quality:.2f})")
    if entry.chunk_index is not None:
        reasons.append(f"Meeting coverage: chunk {entry.chunk_index}")
    if len(set(_extract_key_phrases(f"{entry.question_text} {entry.explanation}"))) >= 4:
        reasons.append("Increases concept diversity")

    return reasons


class ProfessorRankingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def rank_questions(self, transcript_id: uuid.UUID) -> RankingResult:
        rows = list(
            self.db.scalars(
                select(Question).where(
                    Question.transcript_id == transcript_id,
                    Question.is_duplicate == False,
                    Question.is_valid == True,
                )
            ).all()
        )

        if not rows:
            logger.info("professor_ranking.no_questions", extra={"transcript_id": str(transcript_id)})
            return RankingResult(
                transcript_id=transcript_id,
                total_questions=0,
                ranked=[],
                top_10=[],
                top_20=[],
                top_50=[],
                concept_coverage={},
                hierarchy_verified=True,
            )

        chunk_rows = list(
            self.db.scalars(
                select(TranscriptChunk)
                .where(TranscriptChunk.transcript_id == transcript_id)
                .order_by(TranscriptChunk.chunk_index)
            ).all()
        )
        total_chunks = len(chunk_rows)

        chunk_index_map: dict[uuid.UUID, int | None] = {}
        for cr in chunk_rows:
            chunk_index_map[cr.chunk_id] = cr.chunk_index

        total_all = self.db.scalar(
            select(sa_func.count()).select_from(Question).where(
                Question.transcript_id == transcript_id,
                Question.is_duplicate == False,
                Question.is_valid == True,
            )
        ) or 0

        # ── STAGE 1: Compute Composite Educational Score ──
        entries: list[_QEntry] = []
        for q in rows:
            ci = q.chunk_index
            if ci is None and q.chunk_id and q.chunk_id in chunk_index_map:
                ci = chunk_index_map[q.chunk_id]

            reasoning = _compute_reasoning_score(q.question_text)
            opt_q = _compute_option_quality(q.options or [], q.correct_answer)
            recall_penalty = _compute_transcript_recall_penalty(q.question_text)
            is_recall = recall_penalty > 0.0
            bloom_lvl = q.bloom_taxonomy or "understand"
            effective_reasoning = _compute_effective_reasoning(reasoning, bloom_lvl, is_recall)

            style_str = ""
            for kw in _STYLE_WEIGHTS:
                if kw in (q.category or "").lower() or kw in (q.question_text[:80]).lower():
                    style_str = kw
                    break
            style_w = _STYLE_WEIGHTS.get(style_str, 0.55)

            entry = _QEntry(
                question_id=q.id,
                question_text=q.question_text,
                explanation=q.explanation or "",
                options=q.options or [],
                correct_answer=q.correct_answer,
                bloom_level=bloom_lvl,
                category=q.category or "concept",
                difficulty=q.difficulty or "medium",
                educational_score=q.educational_score if q.educational_score is not None else 0.5,
                chunk_index=ci,
                reasoning_score=effective_reasoning,
                option_quality=opt_q,
                style_weight=style_w,
            )

            composite = _compute_composite(entry, recall_penalty)
            entry = _QEntry(
                question_id=entry.question_id,
                question_text=entry.question_text,
                explanation=entry.explanation,
                options=entry.options,
                correct_answer=entry.correct_answer,
                bloom_level=entry.bloom_level,
                category=entry.category,
                difficulty=entry.difficulty,
                educational_score=entry.educational_score,
                chunk_index=entry.chunk_index,
                composite_score=composite,
                reasoning_score=effective_reasoning,
                option_quality=opt_q,
                style_weight=style_w,
            )
            entries.append(entry)

        # ── STAGE 2: Remove Near-Duplicate Questions ──
        deduped = _deduplicate(entries)

        logger.info(
            "professor_ranking.dedup_completed",
            extra={
                "transcript_id": str(transcript_id),
                "before_dedup": len(entries),
                "after_dedup": len(deduped),
            },
        )

        # ── STAGE 3 + 4: Concept Diversity + Meeting Coverage → Final Ranked List ──
        ranked = _greedy_diverse_rank(deduped, total_chunks)

        # ── Derive Top-10/20/50 from the single ranked list ──
        top_10 = ranked[:10]
        top_20 = ranked[:20]
        top_50 = ranked[:50]

        # ── Verify Hierarchy ──
        top10_ids = {rq.question_id for rq in top_10}
        top20_ids = {rq.question_id for rq in top_20}
        top50_ids = {rq.question_id for rq in top_50}
        all_ids = {rq.question_id for rq in ranked}

        h1 = top10_ids.issubset(top20_ids)
        h2 = top20_ids.issubset(top50_ids)
        h3 = top50_ids.issubset(all_ids)
        hierarchy_ok = h1 and h2 and h3

        # ── Concept Coverage Analysis ──
        concept_coverage = _analyze_concept_coverage(ranked[:50], total_chunks)

        logger.info(
            "professor_ranking.completed",
            extra={
                "transcript_id": str(transcript_id),
                "total_questions": total_all,
                "after_dedup": len(deduped),
                "ranked_count": len(ranked),
                "top_10_count": len(top_10),
                "top_20_count": len(top_20),
                "top_50_count": len(top_50),
                "hierarchy_verified": hierarchy_ok,
            },
        )

        return RankingResult(
            transcript_id=transcript_id,
            total_questions=total_all,
            ranked=ranked,
            top_10=top_10,
            top_20=top_20,
            top_50=top_50,
            concept_coverage=concept_coverage,
            hierarchy_verified=hierarchy_ok,
        )

    def get_ranking_preview(self, transcript_id: uuid.UUID) -> dict:
        result = self.rank_questions(transcript_id)

        return {
            "transcript_id": str(result.transcript_id),
            "total_questions": result.total_questions,
            "ranked_count": len(result.ranked),
            "hierarchy_verified": result.hierarchy_verified,
            "top_10": [_ranked_question_dict(rq) for rq in result.top_10],
            "top_20": [_ranked_question_dict(rq) for rq in result.top_20],
            "top_50": [_ranked_question_dict(rq) for rq in result.top_50],
            "concept_coverage": result.concept_coverage,
        }


def _analyze_concept_coverage(top_questions: list[RankedQuestion], total_chunks: int) -> dict:
    if not top_questions:
        return {"unique_concepts": 0, "chunks_covered": 0,
                "total_chunks": total_chunks, "diversity_score": 1.0}

    all_phrases: set[str] = set()
    per_q: list[set[str]] = []
    chunks_seen: set[int | None] = set()

    for rq in top_questions:
        p = _extract_key_phrases(f"{rq.question_text} {rq.explanation}")
        all_phrases |= p
        per_q.append(p)
        chunks_seen.add(rq.chunk_index)

    redundancy_count = 0
    for i in range(len(per_q)):
        for j in range(i + 1, len(per_q)):
            if _jaccard(per_q[i], per_q[j]) > 0.6:
                redundancy_count += 1

    max_pairs = max(1, len(per_q) * (len(per_q) - 1) / 2)
    diversity = round(1.0 - (redundancy_count / max_pairs), 3)

    return {
        "unique_concepts": len(all_phrases),
        "chunks_covered": len(chunks_seen),
        "total_chunks": total_chunks,
        "pairwise_redundancy": redundancy_count,
        "diversity_score": diversity,
    }


def _ranked_question_dict(rq: RankedQuestion) -> dict:
    return {
        "rank": rq.rank,
        "composite_score": rq.composite_score,
        "question_text": rq.question_text[:120],
        "bloom_level": rq.bloom_level,
        "category": rq.category,
        "difficulty": rq.difficulty,
        "educational_score": rq.educational_score,
        "chunk_index": rq.chunk_index,
        "rank_reasons": rq.rank_reasons,
        "concepts_represented": rq.concepts,
        "increases_diversity": (
            _BLOOM_ORDER.get(rq.bloom_level, 0) >= 2 or len(set(rq.concepts)) >= 3
        ),
    }
