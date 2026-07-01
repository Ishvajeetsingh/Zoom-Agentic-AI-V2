import sys
import json

sys.path.insert(0, "backend")

from app.core.config import settings
from app.services.question_service import QuestionService, MCQ_SYSTEM_PROMPT

service = QuestionService(config=settings)

chunk_text = None
chunk_id = None

from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models.transcript_chunk import TranscriptChunk
import uuid

TRANSCRIPT_ID = uuid.UUID("4b4e9600-5e4c-4c38-8ea7-ca6c36a85c0c")

db = SessionLocal()
chunk_row = db.scalars(
    select(TranscriptChunk)
    .where(TranscriptChunk.transcript_id == TRANSCRIPT_ID)
    .order_by(TranscriptChunk.chunk_index)
    .limit(1)
).first()
db.close()

chunk_text = chunk_row.text
chunk_id = chunk_row.chunk_id

print("=== CONCEPT EXTRACTION ===")
concepts = service._extract_concepts(chunk_text, chunk_id, model=settings.ollama_primary_model)
print(f"Concepts returned: {len(concepts)}")
for c in concepts:
    print(f"  {c}")
concepts_summary = service._build_concepts_summary(concepts)
print(f"Concepts summary: {concepts_summary[:300]}")

print("\n=== MCQ GENERATION (direct call) ===")
prompt = (
    f"Generate 2 MCQs from the educational concepts below.\n\n"
    f"--- TRANSCRIPT ---\n{chunk_text}\n--- END ---\n\n"
    f"--- CONCEPTS ---\n{concepts_summary}\n--- END ---\n\n"
    f"Return a JSON array of 2 question objects."
)

response = service.ollama.generate_json(
    prompt,
    model=settings.ollama_primary_model,
    system=MCQ_SYSTEM_PROMPT,
    temperature=0.7,
    max_tokens=settings.max_chunk_tokens,
)

raw = response.response.strip()
print(f"Raw response length: {len(raw)}")

cleaned = service._strip_thinking_tokens(raw)
print(f"Cleaned length: {len(cleaned)}")
print(f"Cleaned first 1000 chars:\n{cleaned[:1000]}")

parsed = service._robust_json_parse(cleaned)
print(f"\nParsed type: {type(parsed).__name__}")
if isinstance(parsed, dict):
    print(f"Dict keys: {list(parsed.keys())}")
    for k, v in parsed.items():
        print(f"  {k}: {type(v).__name__} = {str(v)[:200]}")
elif isinstance(parsed, list):
    print(f"List length: {len(parsed)}")
    for i, item in enumerate(parsed):
        print(f"  [{i}] type={type(item).__name__} val={str(item)[:200]}")
else:
    print(f"Other: {str(parsed)[:500]}")

# Now test the full pipeline
print("\n=== FULL PIPELINE ===")
result = service.generate_questions_from_chunk(
    chunk_text=chunk_text,
    chunk_id=chunk_id,
    model=settings.ollama_primary_model,
)
print(f"Questions generated: {len(result.questions)}")
for q in result.questions:
    print(f"  Q: {q.question_text[:100]}")
    print(f"  Style: {q.question_style}, Bloom: {q.bloom_level}, Diff: {q.difficulty}")
