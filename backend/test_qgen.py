import httpx
import json

system_prompt = """You are an expert assessment author. Given a transcript chunk from a meeting, generate multiple-choice questions that test comprehension and application of the discussed material.

Rules:
- Each question must have exactly 4 options labeled A through D.
- Exactly one option must be correct.
- Include a brief explanation for why the correct answer is right.
- Assign difficulty: easy, medium, or hard.
- Questions should focus on key concepts, decisions, and action items.
- Do NOT invent information not present in the transcript.
- Return a JSON array of question objects.

Each question object must have this schema:
{
    "question_text": "string",
    "question_type": "mcq",
    "options": ["A: ...", "B: ...", "C: ...", "D: ..."],
    "correct_answer": "A",
    "explanation": "string",
    "difficulty": "easy|medium|hard"
}"""

prompt_3 = "Generate 3 multiple-choice questions from the following meeting transcript chunk.\n\n--- TRANSCRIPT CHUNK ---\nWe discussed the project timeline and agreed to push the deadline to March 15th. The marketing team will handle the campaign launch, and the engineering team needs to deliver the API by end of February. Sarah volunteered to lead the QA effort.\n--- END CHUNK ---\n\nReturn a JSON array of 3 question objects."

prompt_2 = "Generate 2 multiple-choice questions from the following meeting transcript chunk.\n\n--- TRANSCRIPT CHUNK ---\nWe discussed the project timeline and agreed to push the deadline to March 15th. The marketing team will handle the campaign launch, and the engineering team needs to deliver the API by end of February. Sarah volunteered to lead the QA effort.\n--- END CHUNK ---\n\nReturn a JSON array of 2 question objects."

payload = {
    "model": "qwen3:8b",
    "prompt": prompt_3,
    "system": system_prompt,
    "stream": False,
    "format": "json",
    "options": {"temperature": 0.0, "num_predict": 4096},
}

print("=== Test: target=3 questions, temp=0.0 ===")
r = httpx.post("http://localhost:11434/api/generate", json=payload, timeout=300)
data = r.json()
resp = data.get("response", "")
print(f"resp_len: {len(resp)}, done: {data.get('done')}")
try:
    parsed = json.loads(resp)
    print(f"keys: {list(parsed.keys())}")
    if isinstance(parsed, dict) and "questions" in parsed:
        print(f"questions: {len(parsed['questions'])}")
        for q in parsed["questions"]:
            print(f"  - {q.get('question_text', '')[:80]}")
    elif isinstance(parsed, list):
        print(f"list_len: {len(parsed)}")
        for q in parsed:
            print(f"  - {q.get('question_text', '')[:80]}")
    elif "error" in parsed:
        print(f"ERROR: {parsed['error']}")
except Exception as e:
    print(f"INVALID_JSON: {e}")

print()
print("=== Test: target=2 questions, temp=0.0 ===")
payload["prompt"] = prompt_2
r = httpx.post("http://localhost:11434/api/generate", json=payload, timeout=300)
data = r.json()
resp = data.get("response", "")
print(f"resp_len: {len(resp)}, done: {data.get('done')}")
try:
    parsed = json.loads(resp)
    print(f"keys: {list(parsed.keys())}")
    if isinstance(parsed, dict) and "questions" in parsed:
        print(f"questions: {len(parsed['questions'])}")
    elif isinstance(parsed, list):
        print(f"list_len: {len(parsed)}")
    elif "error" in parsed:
        print(f"ERROR: {parsed['error']}")
except Exception as e:
    print(f"INVALID_JSON: {e}")
