import sys
import uuid
import json

sys.path.insert(0, "backend")

from sqlalchemy import select, func as sa_func

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models.question import Question
from app.db.models.transcript_chunk import TranscriptChunk
from app.db.models.transcript import Transcript
from app.services.question_service import QuestionService, MCQ_SYSTEM_PROMPT
from app.workflows.dedup import deduplicate_questions
from app.workflows.state import QuestionData

TRANSCRIPT_ID = uuid.UUID("4b4e9600-5e4c-4c38-8ea7-ca6c36a85c0c")
CHUNK_LIMIT = 5


def main():
    db = SessionLocal()
    try:
        transcript = db.get(Transcript, TRANSCRIPT_ID)
        if transcript is None:
            print(f"ERROR: Transcript {TRANSCRIPT_ID} not found")
            return

        meeting_id = transcript.meeting_id

        previous_count = db.scalar(
            select(sa_func.count()).select_from(Question).where(Question.transcript_id == TRANSCRIPT_ID)
        ) or 0

        chunk_rows = db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == TRANSCRIPT_ID)
            .order_by(TranscriptChunk.chunk_index)
            .limit(CHUNK_LIMIT)
        ).all()

        if not chunk_rows:
            print("ERROR: No chunks found")
            return

        print(f"Processing {len(chunk_rows)} chunks (of 147 total)")
        print(f"Previous MCQ count (all chunks): {previous_count}")
        print()

        service = QuestionService(config=settings)

        all_questions: list[QuestionData] = []
        total_concepts = 0
        total_rejected = 0

        for chunk_row in chunk_rows:
            chunk_text = chunk_row.text
            if not chunk_text or not chunk_text.strip():
                print(f"  Chunk {chunk_row.chunk_index}: EMPTY - skipped")
                continue

            print(f"  Chunk {chunk_row.chunk_index}: extracting concepts...", end=" ", flush=True)

            try:
                # concept extraction separately for counting
                concepts = service._extract_concepts(
                    chunk_text=chunk_text,
                    chunk_id=chunk_row.chunk_id,
                    model=settings.ollama_primary_model,
                )
                total_concepts += len(concepts)
                print(f"{len(concepts)} concepts, generating MCQs...", end=" ", flush=True)

                result = service.generate_questions_from_chunk(
                    chunk_text=chunk_text,
                    chunk_id=chunk_row.chunk_id,
                    model=settings.ollama_primary_model,
                )
                raw_mcqs = len(result.questions)
                print(f"{raw_mcqs} raw MCQs")

                if raw_mcqs == 0 and chunk_row.chunk_index == 0:
                    _resp = service.ollama.generate(
                        f"Generate 2 MCQs from the educational concepts below.\n\n--- TRANSCRIPT ---\n{chunk_text}\n--- END ---\n\n--- CONCEPTS ---\n{service._build_concepts_summary(concepts)}\n--- END ---\n\nReturn ONLY a JSON array of 2 question objects. No other text.",
                        model=settings.ollama_primary_model,
                        system=MCQ_SYSTEM_PROMPT,
                        temperature=0.7,
                    )
                    _cleaned = _resp.response.strip()
                    print(f"  RAW LLM (first 500 chars): {_cleaned[:500]}")
                    _cleaned2 = QuestionService._strip_thinking_tokens(_cleaned)
                    print(f"  Cleaned type: {type(QuestionService._robust_json_parse(_cleaned2)).__name__}")
            except Exception as exc:
                print(f"FAILED: {exc}")
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
                    )
                )

        # validation
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
            else:
                total_rejected += 1

        unique, duplicates_removed = deduplicate_questions(valid)
        final_rejected = total_rejected + duplicates_removed

        print()
        print("=" * 60)
        print("PREVIEW STATISTICS")
        print("=" * 60)
        print(f"  Chunks processed:    {len(chunk_rows)}")
        print(f"  Concepts extracted:   {total_concepts}")
        print(f"  Raw MCQs generated:  {len(all_questions)}")
        print(f"  MCQs rejected (validation): {total_rejected}")
        print(f"  Duplicates removed:  {duplicates_removed}")
        print(f"  Final preview MCQs:  {len(unique)}")
        print()

        print("=" * 60)
        print("PREVIEW MCQs")
        print("=" * 60)

        for i, q in enumerate(unique, 1):
            print(f"\n--- MCQ #{i} ---")
            print(f"  Question:         {q.question_text}")
            if q.options and len(q.options) >= 4:
                print(f"  Option A:         {q.options[0]}")
                print(f"  Option B:         {q.options[1]}")
                print(f"  Option C:         {q.options[2]}")
                print(f"  Option D:         {q.options[3]}")
            print(f"  Correct Answer:   {q.correct_answer}")
            print(f"  Question Style:   {q.question_style}")
            print(f"  Bloom Level:      {q.bloom_taxonomy}")
            print(f"  Difficulty:        {q.difficulty}")
            print(f"  Explanation:      {q.explanation}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
