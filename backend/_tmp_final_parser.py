"""Final Task-1 validation: intent router parser behavior."""
from app.services.atlas_intent_router import parse_request

meeting_wide = [
    "Generate a quiz based on the meeting content.",
    "Generate quiz from this meeting.",
    "Generate quiz from the meeting.",
    "Generate quiz from this transcript.",
    "Generate quiz from transcript.",
    "Create quiz based on this meeting.",
    "Give me a quiz from the meeting.",
    "Quiz on the meeting.",
    "Quiz from today's meeting.",
    "Generate questions from this meeting.",
    "Generate practice questions from the meeting.",
]
concrete = [
    "Generate quiz on federated learning",
    "Generate quiz on phishing detection",
    "Generate quiz on edge analytics",
    "Generate quiz on AI ethics",
]
regression_meeting_wide = [
    ("Summarize the meeting.", "summary", None),
    ("Summarize the discussion.", "summary", None),
    ("Summarize based on this meeting.", "summary", None),
    ("Explain the concepts discussed.", "concept_explanation", None),
    ("Explain the concepts discussed in the meeting.", "concept_explanation", None),
    # Task-1 follow-up: remaining Quick Action cards.
    ("Summarize the key points from this meeting.", "summary", None),
    ("Summarize this meeting.", "summary", None),
    ("Summarize the meeting.", "summary", None),
    ("Give me a meeting summary.", "summary", None),
    ("Summarize the meeting content.", "summary", None),
    ("What are the action items from this meeting?", "action_items", None),
    ("Show action items from the meeting.", "action_items", None),
    ("List action items from this meeting.", "action_items", None),
    ("Give me the action items.", "action_items", None),
    ("Action items from this meeting.", "action_items", None),
]
regression_concrete = [
    ("Explain phishing detection", "concept_explanation", "phishing detection"),
    ("Summarize the discussion about phishing detection", "summary", "phishing detection"),
    ("Summarize phishing detection.", "summary", "phishing detection"),
    ("Summarize edge analytics.", "summary", "edge analytics"),
    ("Decisions about AI ethics?", "decisions", "AI ethics"),
    ("Action items about deployment", "action_items", "deployment"),
    ("Action items for API migration", "action_items", "API migration"),
    ("Generate quiz on phishing detection", "quiz_request", "phishing detection"),
]

fails = 0

print("=== Required: meeting-wide quick-action phrases ===")
for p in meeting_wide:
    r = parse_request(p)
    ok = r.intent.value == "quiz_request" and r.topic is None
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] {p!r:55} intent={r.intent.value:14} topic={r.topic!r}")

print("\n=== Required: concrete-topic quizzes still extract topic ===")
for p in concrete:
    r = parse_request(p)
    ok = r.intent.value == "quiz_request" and r.topic is not None
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] {p!r:55} intent={r.intent.value:14} topic={r.topic!r}")

print("\n=== Regression: meeting-wide for other intents ===")
for p, ei, et in regression_meeting_wide:
    r = parse_request(p)
    ok = r.intent.value == ei and r.topic is None
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] {p!r:60} intent={r.intent.value:18} topic={r.topic!r}")

print("\n=== Regression: concrete topics for other intents ===")
for p, ei, et in regression_concrete:
    r = parse_request(p)
    ok = r.intent.value == ei and r.topic == et
    fails += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] {p!r:60} intent={r.intent.value:18} topic={r.topic!r}")

print(f"\n{'ALL_OK' if fails == 0 else str(fails)+' FAILURES'}")
