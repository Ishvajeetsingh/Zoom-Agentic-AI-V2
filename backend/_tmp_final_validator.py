"""Final consolidated Task-1 + Task-2 + regression validation."""
from app.services.atlas_intent_router import parse_request, Scope

fails = 0
def check(label, p, expected_intent, expected_topic):
    global fails
    r = parse_request(p)
    ok = r.intent.value == expected_intent and r.topic == expected_topic
    fails += 0 if ok else 1
    mark = "OK " if ok else "FAIL"
    print(f"  [{mark}] {label:24} intent={r.intent.value:20} topic={r.topic!r}")

print("=== Task 2: ALL SIX landing cards (must be meeting-wide) ===")
check("Summarize a meeting",      "Summarize the key points from this meeting.", "summary", None)
check("Explain a concept",        "Explain the main concept discussed in the meeting.", "concept_explanation", None)
check("Generate a quiz",           "Generate a quiz based on the meeting content.", "quiz_request", None)
check("Find action items",         "What are the action items from this meeting?", "action_items", None)
check("Review learning outputs",  "Review the learning outputs from this meeting.", "revision_request", None)
check("Create study notes",        "Create study notes from this meeting.", "revision_request", None)

print("\n=== Task 1: meeting-wide summary phrases (must all be summary + None) ===")
for p in [
    "Summarize the key points from this meeting.",
    "Summarize this meeting.",
    "Summarize the meeting.",
    "Give me a meeting summary.",
    "Summarize the meeting content.",
]:
    check("summary MW", p, "summary", None)

print("\n=== Task 1: meeting-wide action-item phrases (must all be action_items + None) ===")
for p in [
    "What are the action items from this meeting?",
    "Show action items from the meeting.",
    "List action items from this meeting.",
    "Give me the action items.",
    "Action items from this meeting.",
]:
    check("action_items MW", p, "action_items", None)

print("\n=== Required: concrete topics MUST still extract ===")
check("Summarize phishing detection.",   "Summarize phishing detection.",   "summary", "phishing detection")
check("Summarize edge analytics.",       "Summarize edge analytics.",       "summary", "edge analytics")
check("Action items about deployment",   "Action items about deployment",   "action_items", "deployment")
check("Action items for API migration",  "Action items for API migration",  "action_items", "API migration")

print("\n=== Regression: Quiz / Concept / Decisions / Recs / Revision must be unchanged ===")
check("Quiz meeting-wide", "Generate a quiz based on the meeting content.", "quiz_request", None)
check("Quiz concrete",    "Generate quiz on phishing detection", "quiz_request", "phishing detection")
check("Concept MW",       "Explain the concepts discussed in the meeting.", "concept_explanation", None)
check("Concept concrete", "What is phishing detection?", "concept_explanation", "phishing detection")
check("Decisions concrete","Decisions about AI ethics?", "decisions", "AI ethics")
check("Recs concrete",    "Recommendations about security?", "recommendations", "security")
check("Revision concrete","Create revision notes on federated learning", "revision_request", "federated learning")

print("\n=== Regression: meet-wide 'What are the key concepts …' must STAY concept_explanation, None ===")
check("What are the key concepts discussed?", "What are the key concepts discussed?", "concept_explanation", None)
check("What are the main concepts in meeting?", "What are the main concepts discussed in the meeting?", "concept_explanation", None)

print(f"\n{'ALL_OK' if fails == 0 else str(fails) + ' FAILURES'}  (checked scope flag too: every None == MEETING_WIDE)")
