#!/usr/bin/env python3
"""Validate the Atlas conversation flow end-to-end."""

import requests
import sys

def test_atlas_flow():
    base_url = "http://127.0.0.1:8000/api/v1"

    # Step 1: Create a conversation
    print("Step 1: POST /atlas/conversations")
    r = requests.post(
        f"{base_url}/atlas/conversations",
        json={"title": "Test Chat"},
        timeout=5,
    )
    print(f"  Status: {r.status_code}")
    if r.status_code != 201:
        print(f"  FAILED: {r.text}")
        return False
    conv_id = r.json()["id"]
    print(f"  Conversation ID: {conv_id}")

    # Step 2: List conversations (should find the new one)
    # (Small delay to ensure visibility)
    import time
    time.sleep(0.1)

    print("\nStep 2: GET /atlas/conversations")
    r = requests.get(f"{base_url}/atlas/conversations", timeout=5)
    print(f"  Status: {r.status_code}")
    data = r.json()
    print(f"  Total conversations: {data['total']}")
    found = any(item["id"] == conv_id for item in data.get("items", []))
    print(f"  Found our conversation: {found}")
    if not found:
        print("  FAILED: Conversation not visible after creation")
        return False

    # Step 3: Get the specific conversation
    print("\nStep 3: GET /atlas/conversations/{id}")
    r = requests.get(f"{base_url}/atlas/conversations/{conv_id}", timeout=5)
    print(f"  Status: {r.status_code}")
    if r.status_code != 200:
        print(f"  FAILED: {r.text}")
        return False
    print(f"  Conversation retrieved successfully")

    # Step 4: Send a chat message (no meeting = local response)
    print("\nStep 4: POST /atlas/conversations/{id}/chat")
    r = requests.post(
        f"{base_url}/atlas/conversations/{conv_id}/chat",
        json={"role": "user", "content": "Summarize this meeting."},
        timeout=10,
    )
    print(f"  Status: {r.status_code}")
    if r.status_code != 200:
        print(f"  FAILED: {r.text}")
        return False
    msg = r.json()
    print(f"  Response content: {msg['content'][:80]}")

    # Step 5: Verify messages were stored
    print("\nStep 5: GET /atlas/conversations/{id} (verify messages)")
    r = requests.get(f"{base_url}/atlas/conversations/{conv_id}", timeout=5)
    data = r.json()
    print(f"  Status: {r.status_code}")
    print(f"  Message count: {data['message_count']}")
    print(f"  Messages: {[m['role'] for m in data['messages']]}")
    if data["message_count"] == 0:
        print("  FAILED: Messages not persisted")
        return False

    print("\n✅ All tests passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_atlas_flow()
    except requests.ConnectionError:
        print(f"\n❌ Connection failed. Ensure the backend server is running at http://127.0.0.1:8000",
            file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if success else 1)
