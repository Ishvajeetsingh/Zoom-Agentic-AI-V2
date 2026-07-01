import sys
import uuid
import time

sys.path.insert(0, "backend")

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models.question import Question
from app.db.models.transcript_chunk import TranscriptChunk
from app.db.models.transcript import Transcript
from app.services.question_service import QuestionService, MCQ_SYSTEM_PROMPT

TRANSCRIPT_ID = uuid.UUID("4b4e9600-5e4c-4c38-8ea7-ca6c36a85c0c")
MAX_CHUNKS = 20
MAX_MCQS = 30


def main():
    db = SessionLocal()
    try:
        transcript = db.get(Transcript, TRANSCRIPT_ID)
        if transcript is None:
            print(f"ERROR: Transcript {TRANSCRIPT_ID} not found")
            return

        meeting_id = transcript.meeting_id

        from sqlalchemy import func as sa_func

        previous_count = db.scalar(
            select(sa_func.count()).select_from(Question).where(Question.transcript_id == TRANSCRIPT_ID)
        ) or 0
        print(f"Existing MCQs in DB: {previous_count}")

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
        total_concepts = 0
        total_mcqs = 0
        can_map_old = False

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
                print(f"\n{'='*50}")
                print(f"Chunk {chunk_idx}")
                print(f"Transcript: (empty)")
                print(f"Extracted Concepts: (none - empty chunk)")
                print(f"No educational MCQs generated.")
                print(f"Reason: Chunk text is empty")
                print(f"{'='*50}")
                continue

            chunk_preview = chunk_text[:300] + ("..." if len(chunk_text) > 300 else "")

            print(f"\n{'='*50}")
            print(f"Chunk {chunk_idx}")
            print(f"Transcript: {chunk_preview}")
            sys.stdout.flush()

            # Step 1: Extract concepts
            t0 = time.time()
            try:
                concepts = service._extract_concepts(
                    chunk_text=chunk_text,
                    chunk_id=chunk_row.chunk_id,
                    model=settings.ollama_primary_model,
                )
            except Exception as exc:
                t1 = time.time()
                print(f"Extracted Concepts: FAILED ({exc}) [{t1-t0:.1f}s]")
                print(f"No educational MCQs generated.")
                print(f"Reason: Concept extraction failed: {exc}")
                print(f"{'='*50}")
                sys.stdout.flush()
                continue

            t1 = time.time()
            total_concepts += len(concepts)

            print(f"Extracted Concepts: {len(concepts)} [{t1-t0:.1f}s]")
            for c in concepts:
                print(f"  - [{c.category.upper()}] {c.concept}: {c.summary}")
            sys.stdout.flush()

            if not concepts:
                print(f"No educational MCQs generated.")
                print(f"Reason: No concepts extracted from this chunk")
                print(f"{'='*50}")
                continue

            # Step 2: Generate MCQs
            t0 = time.time()
            try:
                result = service.generate_questions_from_chunk(
                    chunk_text=chunk_text,
                    chunk_id=chunk_row.chunk_id,
                    model=settings.ollama_primary_model,
                )
            except Exception as exc:
                t1 = time.time()
                print(f"Generated MCQs: FAILED ({exc}) [{t1-t0:.1f}s]")
                print(f"No educational MCQs generated.")
                print(f"Reason: MCQ generation failed: {exc}")
                print(f"{'='*50}")
                sys.stdout.flush()
                continue

            t1 = time.time()
            mcqs = result.questions
            total_mcqs += len(mcqs)

            if not mcqs:
                print(f"Generated MCQs: 0 [{t1-t0:.1f}s]")
                print(f"No educational MCQs generated.")
                print(f"Reason: LLM returned no parseable MCQ objects")
                print(f"{'='*50}")
                sys.stdout.flush()
                continue

            print(f"Generated MCQs: {len(mcqs)} [{t1-t0:.1f}s]")
            for i, q in enumerate(mcqs, 1):
                print(f"\n  MCQ #{i}:")
                print(f"    Question: {q.question_text}")
                if q.options and len(q.options) >= 4:
                    print(f"    Option A: {q.options[0]}")
                    print(f"    Option B: {q.options[1]}")
                    print(f"    Option C: {q.options[2]}")
                    print(f"    Option D: {q.options[3]}")
                elif q.options:
                    for j, opt in enumerate(q.options):
                        print(f"    Option {j+1}: {opt}")
                print(f"    Correct Answer: {q.correct_answer}")
                print(f"    Explanation: {q.explanation}")
                print(f"    Question Style: {q.question_style}")
                print(f"    Bloom Level: {q.bloom_level}")
                print(f"    Difficulty: {q.difficulty}")

            print(f"\n  Existing MCQs cannot be reliably mapped to this chunk.")
            print(f"{'='*50}")
            sys.stdout.flush()

        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"  Chunks processed: {total_chunks}")
        print(f"  Concepts extracted: {total_concepts}")
        print(f"  Total MCQs generated: {total_mcqs}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
