import httpx
import json

system_prompt = (
    'You are an expert assessment author. Given a transcript chunk from a meeting, '
    'generate multiple-choice questions that test comprehension and application of the discussed material.\n\n'
    'Rules:\n'
    '- Each question must have exactly 4 options labeled A through D.\n'
    '- Exactly one option must be correct.\n'
    '- Include a brief explanation for why the correct answer is right.\n'
    '- Assign difficulty: easy, medium, or hard.\n'
    '- Questions should focus on key concepts, decisions, and action items.\n'
    '- Do NOT invent information not present in the transcript.\n'
    '- Return a JSON array of question objects.\n\n'
    'Each question object must have this schema:\n'
    '{\n'
    '    "question_text": "string",\n'
    '    "question_type": "mcq",\n'
    '    "options": ["A: ...", "B: ...", "C: ...", "D: ..."],\n'
    '    "correct_answer": "A",\n'
    '    "explanation": "string",\n'
    '    "difficulty": "easy or medium or hard"\n'
    '}'
)

prompt = (
    'Generate 4 multiple-choice questions from the following meeting transcript chunk.\n\n'
    '--- TRANSCRIPT CHUNK ---\n'
    'We discussed the project timeline and agreed to push the deadline to March 15th. '
    'The marketing team will handle the campaign launch, and the engineering team needs '
    'to deliver the API by end of February. Sarah volunteered to lead the QA effort.\n'
    '--- END CHUNK ---\n\n'
    'Return a JSON array of 4 question objects.'
)

payload = {
    'model': 'qwen3:8b',
    'prompt': prompt,
    'system': system_prompt,
    'stream': False,
    'format': 'json',
    'options': {'temperature': 0.0, 'num_predict': 4096},
}

r = httpx.post('http://localhost:11434/api/generate', json=payload, timeout=300)
data = r.json()
resp = data.get('response', '')
parsed = json.loads(resp)
questions = parsed.get('questions', parsed) if isinstance(parsed, dict) else parsed
print(f'Total questions: {len(questions)}')
for i, q in enumerate(questions):
    opts = q.get('options', [])
    ca = q.get('correct_answer', '')
    qt = q.get('question_type', '')
    diff = q.get('difficulty', '')
    expl_len = len(q.get('explanation', ''))
    errors = []
    if len(q.get('question_text', '')) < 10:
        errors.append('question_text short')
    if len(opts) != 4:
        errors.append(f'options count {len(opts)} != 4')
    if ca and ca.strip()[0].upper() not in 'ABCD':
        errors.append(f'correct_answer {ca} not ABCD')
    if not q.get('explanation') or len(q.get('explanation', '').strip()) < 5:
        errors.append('explanation short')
    if diff not in ('easy', 'medium', 'hard'):
        errors.append(f'invalid difficulty: {diff}')
    if qt != 'mcq':
        errors.append(f'wrong type: {qt}')
    print(f'  Q{i}: errors={errors}, type={qt}, opts={len(opts)}, ca={ca}, diff={diff}', flush=True)

print()
print('FULL RESPONSE (first 3000 chars):')
print(resp[:3000])
