import sys
import uuid
import time
import re

sys.path.insert(0, "backend")

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models.question import Question
from app.db.models.transcript_chunk import TranscriptChunk
from app.db.models.transcript import Transcript
from app.services.question_service import QuestionService

TRANSCRIPT_ID = uuid.UUID("4b4e9600-5e4c-4c38-8ea7-ca6c36a85c0c")
MAX_CHUNKS = 15
MAX_MCQS = 30

SINGLE_WORD_OPTIONS = {
    "role", "task", "context", "examples", "constraints",
    "output format", "outputformat", "persona", "tone", "style",
    "format", "instruction", "instructions", "action", "objective",
    "goal", "purpose", "scope", "domain", "field", "topic", "subject",
    "category", "type", "kind", "level", "model", "prompt", "system",
    "input", "output", "query", "response", "answer", "result",
}


def is_single_word_option(opt_text):
    body = re.sub(r"^[A-D]:\s*", "", opt_text.strip(), count=1).strip()
    return len(body.split()) <= 2 and body.lower() in SINGLE_WORD_OPTIONS


def main():
    db = SessionLocal()
    try:
        transcript = db.get(Transcript, TRANSCRIPT_ID)
        if transcript is None:
            print(f"ERROR: Transcript {TRANSCRIPT_ID} not found")
            return

        meeting_id = transcript.meeting_id

        chunk_rows = db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == TRANSCRIPT_ID)
            .order_by(TranscriptChunk.chunk_index)
            .limit(MAX_CHUNKS)
        ).all()

        if not chunk_rows:
            print("ERROR: No chunks found")
            return

        total_chunks = 0
        total_mcqs = 0
        total_q_rewritten = 0
        total_opts_rewritten = 0
        chunks_with_zero = []
        all_mcqs = []

        CRITICAL_CHUNKS = {3, 8, 9, 10}
        critical_chunk_results = {3: "FAIL", 8: "FAIL", 9: "FAIL", 10: "FAIL"}

        print(f"Transcript: {TRANSCRIPT_ID}")
        print(f"Meeting: {meeting_id}")
        print(f"Max chunks: {MAX_CHUNKS} | Stop at {MAX_MCQS} MCQs")
        print("=" * 60)

        service = QuestionService(config=settings)

        for chunk_row in chunk_rows:
            if total_mcqs >= MAX_MCQS:
                print(f"\n>>> STOPPING: Reached {MAX_MCQS} MCQ target")
                break

            if total_chunks >= MAX_CHUNKS:
                print(f"\n>>> STOPPING: Reached {MAX_CHUNKS} chunk limit")
                break

            chunk_text = chunk_row.text
            chunk_idx = chunk_row.chunk_index
            total_chunks += 1

            if not chunk_text or not chunk_text.strip():
                print(f"\nChunk {chunk_idx}: No educational content")
                if chunk_idx in CRITICAL_CHUNKS:
                    critical_chunk_results[chunk_idx] = "FAIL (empty chunk)"
                chunks_with_zero.append(chunk_idx)
                continue

            chunk_preview = chunk_text[:200] + ("..." if len(chunk_text) > 200 else "")

            print(f"\n{'='*60}")
            print(f"Chunk {chunk_idx}: {chunk_preview}")
            sys.stdout.flush()

            t0 = time.time()
            try:
                result = service.generate_questions_from_chunk(
                    chunk_text=chunk_text,
                    chunk_id=chunk_row.chunk_id,
                    model=settings.ollama_primary_model,
                )
            except Exception as exc:
                t1 = time.time()
                print(f"Chunk {chunk_idx}: MCQ generation FAILED - {exc} [{t1-t0:.1f}s]")
                sys.stdout.flush()
                if chunk_idx in CRITICAL_CHUNKS:
                    critical_chunk_results[chunk_idx] = "FAIL"
                chunks_with_zero.append(chunk_idx)
                continue

            t1 = time.time()
            mcqs = result.questions

            if not mcqs:
                print(f"Chunk {chunk_idx}: ZERO MCQs generated [{t1-t0:.1f}s]")
                if chunk_idx in CRITICAL_CHUNKS:
                    critical_chunk_results[chunk_idx] = "FAIL"
                chunks_with_zero.append(chunk_idx)
                sys.stdout.flush()
                continue
            else:
                if chunk_idx in CRITICAL_CHUNKS:
                    critical_chunk_results[chunk_idx] = "PASS"

            print(f"Generated + Reviewed: {len(mcqs)} MCQs [{t1-t0:.1f}s]")

            for i, q in enumerate(mcqs, 1):
                if total_mcqs >= MAX_MCQS:
                    break

                total_mcqs += 1
                score = q.educational_score

                if q.rewritten:
                    total_q_rewritten += 1
                if q.options_rewritten:
                    total_opts_rewritten += 1

                all_mcqs.append({
                    "chunk_idx": chunk_idx,
                    "mcq_num": i,
                    "question": q,
                    "score": score,
                })

                orig = q.original_question_text or q.question_text
                q_rewritten = "YES" if q.rewritten else "NO"
                opts_rewritten = "YES" if q.options_rewritten else "NO"

                print(f"\n  --- MCQ #{i} (Chunk {chunk_idx}) ---")
                print(f"  Chunk number:          {chunk_idx}")
                print(f"  Original Question:     {orig}")
                print(f"  Final Question:        {q.question_text}")
                print(f"  Question rewritten?     {q_rewritten}")
                print(f"  Options rewritten?     {opts_rewritten}")
                print(f"  Educational Score:      {score}")
                print(f"  Bloom Level:           {q.bloom_level}")
                print(f"  Difficulty:             {q.difficulty}")
                print(f"  Options:")
                if q.options and len(q.options) >= 4:
                    print(f"    A: {q.options[0]}")
                    print(f"    B: {q.options[1]}")
                    print(f"    C: {q.options[2]}")
                    print(f"    D: {q.options[3]}")
                elif q.options:
                    for j, opt in enumerate(q.options):
                        print(f"    Option {j+1}: {opt}")
                print(f"  Correct Answer:        {q.correct_answer}")
                print(f"  Explanation:           {q.explanation}")

            sys.stdout.flush()

        print(f"\n{'='*60}")
        print("VERIFICATION CHECKS")
        print(f"{'='*60}")

        # CHECK 1: "According to the transcript..." surviving?
        print("\n--- CHECK 1: 'According to the transcript...' surviving? ---")
        according_survivors = []
        for m in all_mcqs:
            q = m["question"]
            if q.question_text.lower().startswith("according to the transcript"):
                according_survivors.append(q)
        if according_survivors:
            for q in according_survivors:
                print(f"  FAIL: {q.question_text}")
        else:
            print("  PASS")

        # CHECK 2: Single-word options surviving?
        print("\n--- CHECK 2: Single-word options surviving? ---")
        single_word_survivors = []
        for m in all_mcqs:
            q = m["question"]
            for opt in (q.options or []):
                if is_single_word_option(opt):
                    single_word_survivors.append((q, opt))
                    break
        if single_word_survivors:
            for q, opt in single_word_survivors:
                print(f"  FAIL: Q=\"{q.question_text[:80]}\" has single-word option: {opt}")
        else:
            print("  PASS")

        # CHECK 3: Chunks 3, 8, 9, 10 now generate MCQs?
        print("\n--- CHECK 3: Chunks 3, 8, 9, 10 now generate MCQs? ---")
        for ci in sorted(CRITICAL_CHUNKS):
            print(f"  Chunk {ci}: {critical_chunk_results[ci]}")

        # CHECK 4: Rewrite actions not lost to fallback?
        print("\n--- CHECK 4: Rewrite actions lost to fallback? ---")
        rewritten_mcqs = [m for m in all_mcqs if m["question"].rewritten or m["question"].options_rewritten]
        if rewritten_mcqs:
            m = rewritten_mcqs[0]
            q = m["question"]
            print(f"  Tracing first rewritten MCQ end-to-end:")
            print(f"    Chunk:        {m['chunk_idx']}")
            print(f"    Action:       {'rewrite' if q.rewritten else 'rewrite_options'}")
            print(f"    Original Q:   {q.original_question_text}")
            print(f"    Final Q:       {q.question_text}")
            print(f"    Options:       {q.options}")
            print(f"    Score:         {m['score']}")
            print(f"    Review Reason: {q.review_reason}")
            if q.original_question_text and q.original_question_text != q.question_text:
                print(f"    Stem changed:  YES (rewrite NOT lost)")
            elif q.options_rewritten:
                orig_opts_note = "options differ from original (check log for 'options_restored_from_input')"
                print(f"    Options rewritten flag set: YES (rewrite NOT lost)")
            else:
                print(f"    RESULT:        FAIL — rewrite may have been lost (original == final)")
            print(f"  PASS (at least one rewrite persisted)")
        else:
            print(f"  INCONCLUSIVE — no rewrites produced in this run; cannot verify")

        # FINAL SUMMARY
        print(f"\n{'='*60}")
        print("FINAL SUMMARY")
        print(f"{'='*60}")
        print(f"  MCQs reviewed:          {total_mcqs}")
        print(f"  Questions rewritten:    {total_q_rewritten}")
        print(f"  Options rewritten:      {total_opts_rewritten}")
        print(f"  Chunks with zero MCQs:  {chunks_with_zero if chunks_with_zero else 'None'}")

        blockers = []
        if according_survivors:
            blockers.append("'According to the transcript...' questions survived")
        if single_word_survivors:
            blockers.append("Single-word options survived")
        for ci in CRITICAL_CHUNKS:
            if critical_chunk_results[ci] != "PASS":
                blockers.append(f"Chunk {ci} still produces zero MCQs")
        if not rewritten_mcqs:
            blockers.append("No rewrites produced — cannot verify rewrite persistence")

        print(f"  Remaining production blockers: {blockers if blockers else 'None'}")
        print(f"  Ready for production? {'YES' if not blockers else 'NO'}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
