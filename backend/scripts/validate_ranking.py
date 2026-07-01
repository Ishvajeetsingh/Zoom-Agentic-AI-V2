"""Validate Professor Ranking — runs ranking on existing data without regeneration.

Usage:
    python -m backend.scripts.validate_ranking <transcript_id>
    python -m backend.scripts.validate_ranking --all
"""

from __future__ import annotations

import argparse
import sys
import uuid


def _bootstrap() -> None:
    try:
        import app.core.config
    except ImportError:
        sys.path.insert(0, "backend")
        import app.core.config


def run_validation(transcript_id_str: str | None = None) -> None:
    _bootstrap()

    from sqlalchemy import create_engine, select, func as sa_func
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.db.models.question import Question
    from app.db.models.transcript_chunk import TranscriptChunk
    from app.db.models.transcript import Transcript
    from app.services.professor_ranking_service import (
        ProfessorRankingService,
        _BLOOM_ORDER,
        _compute_reasoning_score,
        _compute_option_quality,
        _extract_key_phrases,
        _jaccard,
    )

    engine = create_engine(str(settings.database_url))
    with Session(engine) as db:
        if transcript_id_str:
            tid = uuid.UUID(transcript_id_str)
        else:
            tids = db.scalars(
                select(Transcript.id).where(
                    Transcript.status.in_(("completed", "completed_with_warnings"))
                )
            ).all()
            if not tids:
                print("No completed transcripts found.")
                return
            tid = tids[0]
            print(f"Using first completed transcript: {tid}")

        total_chunks = db.scalar(
            select(sa_func.count()).select_from(TranscriptChunk).where(
                TranscriptChunk.transcript_id == tid
            )
        ) or 0

        service = ProfessorRankingService(db)
        result = service.rank_questions(tid)

        print(f"\n{'='*70}")
        print(f"PROFESSOR RANKING VALIDATION")
        print(f"Transcript: {tid}")
        print(f"{'='*70}")

        print(f"\n--- SUMMARY ---")
        print(f"Total questions:    {result.total_questions}")
        print(f"Ranked questions:   {len(result.ranked)}")
        print(f"Top-10:             {len(result.top_10)}")
        print(f"Top-20:             {len(result.top_20)}")
        print(f"Top-50:             {len(result.top_50)}")
        print(f"Total chunks:       {total_chunks}")

        # ── HIERARCHY VERIFICATION ──
        top10_ids = {rq.question_id for rq in result.top_10}
        top20_ids = {rq.question_id for rq in result.top_20}
        top50_ids = {rq.question_id for rq in result.top_50}
        all_ids = {rq.question_id for rq in result.ranked}

        h1 = top10_ids.issubset(top20_ids)
        h2 = top20_ids.issubset(top50_ids)
        h3 = top50_ids.issubset(all_ids)

        print(f"\n--- HIERARCHY VERIFICATION ---")
        print(f"Top-10 ⊂ Top-20:  {h1}")
        print(f"Top-20 ⊂ Top-50:  {h2}")
        print(f"Top-50 ⊂ All:     {h3}")
        print(f"HIERARCHY VALID:  {h1 and h2 and h3}")
        print(f"Algorithm-verified: {result.hierarchy_verified}")

        # ── TOP 10 ──
        print(f"\n--- TOP 10 ---")
        for rq in result.top_10:
            _print_ranked(rq)

        # ── TOP 20 positions 11-20 ──
        print(f"\n--- TOP 20 (positions 11-20) ---")
        for rq in result.top_20[10:]:
            _print_ranked(rq)

        # ── TOP 50 positions 21-50 ──
        print(f"\n--- TOP 50 (positions 21-50) ---")
        for rq in result.top_50[20:]:
            _print_ranked(rq, brief=True)

        # ── CONCEPT DIVERSITY ──
        cov = result.concept_coverage
        print(f"\n--- CONCEPT DIVERSITY ---")
        print(f"Unique key phrases:   {cov.get('unique_concepts', 'N/A')}")
        print(f"Chunks covered:      {cov.get('chunks_covered', 'N/A')} / {total_chunks}")
        print(f"Pairwise redundancy: {cov.get('pairwise_redundancy', 'N/A')}")
        print(f"Diversity score:     {cov.get('diversity_score', 'N/A')}")

        # ── BLOOM DISTRIBUTION in Top-50 ──
        bloom_counts: dict[str, int] = {}
        for rq in result.top_50:
            bloom_counts[rq.bloom_level] = bloom_counts.get(rq.bloom_level, 0) + 1
        print(f"\n--- BLOOM DISTRIBUTION (Top-50) ---")
        for bl in ("remember", "understand", "apply", "analyze", "evaluate"):
            if bl in bloom_counts:
                print(f"  {bl:>10s}: {bloom_counts[bl]}")

        # ── CHUNK COVERAGE in Top-50 ──
        chunks_in_top50: set[int | None] = set()
        for rq in result.top_50:
            chunks_in_top50.add(rq.chunk_index)
        print(f"\n--- MEETING COVERAGE (Top-50) ---")
        print(f"Chunks represented: {len(chunks_in_top50)} / {total_chunks}")

        # ── RANKING STABILITY ──
        high_edu = sum(1 for rq in result.top_10 if rq.educational_score >= 0.6)
        low_edu = sum(1 for rq in result.top_50 if rq.educational_score < 0.4)
        print(f"\n--- RANKING STABILITY ---")
        print(f"Questions with edu_score >= 0.6 in Top-10: {high_edu}/10")
        print(f"Questions with edu_score < 0.4 in Top-50:  {low_edu}")

        print(f"\n{'='*70}")
        print("VALIDATION COMPLETE — no database changes made")
        print(f"{'='*70}")


def _print_ranked(rq, brief: bool = False) -> None:
    edu = rq.educational_score
    bloom = rq.bloom_level

    if brief:
        print(f"  #{rq.rank:3d}  [{bloom:>8s}] edu={edu:.2f}  comp={rq.composite_score:.3f}  "
              f"{rq.question_text[:70]}")
    else:
        print(f"  #{rq.rank:3d}  [{bloom:>8s}] edu={edu:.2f}  comp={rq.composite_score:.3f}  "
              f"chunk={rq.chunk_index}")
        print(f"        Q: {rq.question_text[:100]}")
        print(f"        reasons: {', '.join(rq.rank_reasons)}")
        print(f"        concepts: {', '.join(rq.concepts)}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Professor Ranking")
    parser.add_argument("transcript_id", nargs="?", default=None,
                        help="Transcript UUID (uses first completed if omitted)")
    args = parser.parse_args()
    run_validation(args.transcript_id)
