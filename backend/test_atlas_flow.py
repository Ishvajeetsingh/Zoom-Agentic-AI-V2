import requests
import time

BASE = 'http://127.0.0.1:8000/api/v1'

# Wait for server
time.sleep(1)

try:
    # 1. List conversations (should be empty)
    r = requests.get(f'{BASE}/atlas/conversations', timeout=5)
    print(f'GET /conversations: {r.status_code} -> items={len(r.json()[\"items\"])}')

    # 2. Create conversation
    r = requests.post(f'{BASE}/atlas/conversations', json={'title': 'Test Chat'}, timeout=5)
    data = r.json()
    print(f'POST /conversations: {r.status_code} -> id={data[\"id\"][:8]}...')
    conv_id = data['id']

    # 3. Get conversation
    r = requests.get(f'{BASE}/atlas/conversations/{conv_id}', timeout=5)
    print(f'GET /conversations/{{id}}: {r.status_code} -> messages={len(r.json()[\"messages\"])}')

    # 4. Chat with LLM (no meeting, should return local message)
    r = requests.post(f'{BASE}/atlas/conversations/{conv_id}/chat', json={'role':'user','content':'Summarize this meeting.'}, timeout=10)
    print(f'POST /chat: {r.status_code} -> {r.json()[\"content\"][:60]}...')

except Exception as e:
    print(f'ERROR: {e}')
