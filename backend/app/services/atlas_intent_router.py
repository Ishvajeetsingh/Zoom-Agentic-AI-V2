"""Intent Router for Atlas Educational Intelligence."""
from dataclasses import dataclass
from enum import Enum
import re


class AtlasIntent(Enum):
    SUMMARY = "summary"
    CONCEPT_EXPLANATION = "concept_explanation"
    QUIZ_REQUEST = "quiz_request"
    REVISION_REQUEST = "revision_request"
    ACTION_ITEMS = "action_items"
    DECISIONS = "decisions"
    RECOMMENDATIONS = "recommendations"
    GENERAL_QUESTION = "general_question"


class Scope(Enum):
    """Result of request understanding: how narrow is the user's ask?

    MEETING_WIDE — the user wants the entire meeting view (e.g.
    "summarize the meeting", "explain the concepts discussed",
    "give me all action items", "quiz").
    TOPIC_ONLY   — the user named a specific concept/entity and Atlas
    should restrict every retrieval/builder/prompt to that topic only
    (e.g. "explain phishing detection", "summarize federated learning",
    "action items for deployment", "generate 7 questions on phishing
    detection").
    """
    MEETING_WIDE = "meeting_wide"
    TOPIC_ONLY = "topic_only"


@dataclass
class ParsedRequest:
    """Lightweight outcome of request understanding.

    Fields:
      - intent: detected AtlasIntent
      - topic: the focused concept / entity / section the user asked about,
               stripped of intent-bearing verbs and filler. None when the user
               made a meeting-wide request with no specific focus
               (e.g. "summarize the meeting", "explain the concepts discussed").
               Empty string ("") means an explicit-but-empty focus was given.
      - scope: MEETING_WIDE when no topic was extracted, TOPIC_ONLY otherwise.
               Downstream builders/inspect the meeting use this to decide
               whether to filter artifacts by topic or surface the whole meeting.
      - quantity: requested count when applicable (quizzes, action items,
                  decisions, recommendations, concepts, flashcards), else None.
    """
    intent: AtlasIntent
    topic: str | None = None
    scope: Scope = Scope.MEETING_WIDE
    quantity: int | None = None


# Simple keyword-based intent detection
_INTENT_KEYWORDS: dict[AtlasIntent, list[str]] = {
    AtlasIntent.SUMMARY: [
        "summarize", "summary", "overview", "brief", "recap", "what happened",
        "key points", "main points", "highlights",
    ],
    AtlasIntent.CONCEPT_EXPLANATION: [
        "explain", "what is", "what are", "how does", "why is", "definition",
        "clarify", "describe", "meaning of", "concept",
    ],
    AtlasIntent.QUIZ_REQUEST: [
        "quiz", "test me", "question me", "assess", "practice", "exercise",
        "generate quiz", "quiz me", "test my knowledge",
    ],
    AtlasIntent.REVISION_REQUEST: [
        "revise", "review", "study", "flashcard", "revision", "study guide",
        "help me study", "prepare for exam", "revision guide",
    ],
    AtlasIntent.ACTION_ITEMS: [
        "action item", "action items", "todo", "to-do", "tasks", "next steps",
        "what needs to be done", "who should", "responsibilities",
    ],
    AtlasIntent.DECISIONS: [
        "decision", "decisions", "decided", "concluded", "agreed", "consensus",
        "what was decided", "outcome",
    ],
    AtlasIntent.RECOMMENDATIONS: [
        "recommendation", "recommendations", "suggest", "advice", "proposed",
        "what should we do", "next recommendation",
    ],
}


# Per-intent patterns that strip the intent-bearing head (and any trailing
# connective) off the user message, isolating the requested topic. Each
# pattern is anchored at the start and consumes the full natural-language
# trigger phrase including common connectives ("about", "regarding",
# "were made about", "the discussion about", ...). The trailing capture
# group holds the residual topic. When nothing concrete remains the caller
# falls back to the existing meeting-wide behaviour.
#
# Patterns are tried in order; the first match wins.
_TOPIC_PATTERNS: dict[AtlasIntent, list[str]] = {
    AtlasIntent.SUMMARY: [
        # "Summarize the discussion about X" / "Summary of the discussion on X"
        r"^\s*(?:please\s+)?(?:can\s+you\s+)?(?:summar(?:ise|ize)|recap|brief|overview|highlight|review)\s+(?:the\s+)?(?:discussion|meeting|session|lecture|talk|content|transcript)?\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:please\s+)?give\s+me\s+(?:a\s+)?(?:summary|overview|recap|brief)\s+(?:of|on|about|regarding)?\s*(?:the\s+)?(?:discussion|meeting|session)?\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:what\s+(?:happened|was\s+discussed|were\s+(?:the\s+)?(?:key|main)\s+points?))\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
    ],
    AtlasIntent.CONCEPT_EXPLANATION: [
        # Natural question / imperative forms first so the captured residual
        # is the generic noun phrase (caught by _GENERIC_TOPIC_RE) rather than
        # leaking question text. Each allows an optional quantifier /
        # adjective ("all the", "key", "important", ...) so "What were the key
        # concepts discussed?" → residual "the key concepts discussed" → None.
        r"^\s*(?:please\s+)?(?:what\s+(?:concepts?|topics?|key\s+concepts?|important\s+concepts?|main\s+concepts?|were\s+(?:the\s+)?(?:key\s+|important\s+|main\s+)?concepts?)|tell\s+me\s+(?:about\s+)?(?:the\s+)?(?:key\s+|important\s+|main\s+|all\s+(?:the\s+)?)?concepts?(?:\s+discussed)?)\s*(.*)?\??\s*$",
        r"^\s*(?:please\s+)?what\s+did\s+we\s+learn(?:\s+(?:in|from|about)\s+(?:the\s+)?(?:meeting|session|this\s+meeting|session))?\s*(.*)?\??\s*$",
        r"^\s*(?:please\s+)?(?:can\s+you\s+)?(?:explain|describe|clarify|tell\s+me\s+about|describe)\s+(?:the\s+)?(?:concept\s+(?:of|about|on)\s*)?(.+?)\??\s*$",
        r"^\s*(?:please\s+)?(?:what\s+(?:is|are)|define|definition\s+of|meaning\s+of)\s*(?:the\s+)?(?:concept\s+(?:of|about|on)\s*)?(.+?)\??\s*$",
        r"^\s*(?:please\s+)?(?:how\s+does|why\s+is|elaborate\s+on)\s+(.+?)\??\s*$",
    ],
    AtlasIntent.ACTION_ITEMS: [
        r"^\s*(?:please\s+)?(?:give|list|show)\s+(?:me\s+)?(?:the\s+)?(?:action\s+items?|to-?dos?|tasks|next\s+steps|responsibilities)\s*(?:about|on|regarding|for|related\s+to|concerning|on\s+the\s+topic\s+of)?\s*(.+?)\??\s*$",
        r"^\s*(?:what\s+(?:are|were)\s+(?:the\s+)?(?:action\s+items?|to-?dos?|tasks|next\s+steps|responsibilities))\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:action\s+items?|to-?dos?|tasks|next\s+steps|responsibilities)\s*(?:about|on|regarding|for|related\s+to|concerning|who\s+should)?\s*(.+?)\??\s*$",
    ],
    AtlasIntent.DECISIONS: [
        r"^\s*(?:please\s+)?(?:give|list|show)\s+(?:me\s+)?(?:the\s+)?(?:decisions?|outcomes?|conclusions?)\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:what\s+decisions\s+were\s+made|what\s+was\s+decided|what\s+(?:were|are)\s+(?:the\s+)?decisions?|decisions\s+made)\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:decisions?|outcomes?|conclusions?)\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
    ],
    AtlasIntent.RECOMMENDATIONS: [
        r"^\s*(?:please\s+)?(?:give|list|show)\s+(?:me\s+)?(?:the\s+)?(?:recommendations?|suggestions?|advice)\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:what\s+(?:are|were)\s+(?:the\s+)?(?:recommendations?|suggestions?))\s*(?:about|on|regarding|for|related\s+to|concerning|made\s+for)?\s*(.+?)\??\s*$",
        r"^\s*(?:what\s+recommendations?\s+were\s+made|recommendations?\s+made)\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
        r"^\s*(?:recommendations?|suggestions?)\s*(?:about|on|regarding|for|related\s+to|concerning)?\s*(.+?)\??\s*$",
    ],
    AtlasIntent.REVISION_REQUEST: [
        r"^\s*(?:please\s+)?(?:create|generate|give|make)\s+(?:me\s+)?(?:revision(?:\s+notes?)?|study\s+(?:guide|notes?)|flashcards?|summary\s+notes?)\s*(?:for|on|about|regarding|related\s+to|covering)?\s*(.+?)\??\s*$",
        r"^\s*(?:please\s+)?(?:revision\s+notes?|study\s+guide|flashcards?)\s*(?:for|on|about|regarding|related\s+to|covering)?\s*(.+?)\??\s*$",
    ],
    AtlasIntent.QUIZ_REQUEST: [
        r"^\s*(?:please\s+)?(?:create|generate|give|make)\s+(?:me\s+)?(?:a\s+)?(?:quiz|test|questions?)\s*(?:on|about|regarding|for|related\s+to|covering|of)?\s*(.+?)\??\s*$",
        r"^\s*(?:please\s+)?(?:quiz|test)\s+me\s+(?:on|about|regarding|for|related\s+to|covering)?\s*(.+?)\??\s*$",
        r"^\s*(?:quiz|questions?)\s*(?:on|about|regarding|for|related\s+to|covering|of)?\s*(.+?)\??\s*$",
    ],
}

# Residual tail that means "no specific topic" → meeting-wide request.
# Recognises generic placeholders so the topic falls back to None
# ("summarize the discussion", "explain the concepts discussed",
#  "generate quiz", "give me action items", ...).
# The concept-noun branch is permissive: it accepts an optional leading
# quantifier ("all", "all the", "every", "any", "the"), an optional
# adjective ("key", "important", "main", "major", "core"), the noun
# itself ("concepts", "concept", "topics", "ideas", ...), and a trailing
# suffix covering all natural ways of referring to the meeting
# ("discussed", "covered in the meeting", "from the meeting",
#  "mentioned in the meeting", ...). None of these are topics.
_GENERIC_TOPIC_RE = re.compile(
    r"^\s*(?:"
    # (All the | every | any | the)? (key | important | main | major | core)?
    # (concepts? | topics? | ideas? | points? | themes? | takeaways? | outcomes?)
    # (discussed | covered [in the meeting] | mentioned [in the meeting]
    #  | in the meeting | from the meeting | of the meeting | taught | learned)?
    r"(?:all\s+(?:the\s+)?|every\s+|any\s+|the\s+)?"
    r"(?:key\s+|important\s+|main\s+|major\s+|core\s+)?"
    r"(?:concepts?|topics?|ideas?|points?|themes?|takeaways?|outcomes?)"
    # Trailing suffix. Wrapped in a repeatable non-capturing group so a
    # noun phrase like "concepts discussed in the meeting" can chain
    # "discussed" + "in the meeting" (two separate tokens) — both get
    # consumed and the whole residual collapses to a meeting-wide
    # placeholder rather than leaking as a literal topic.
    r"(?:\s+(?:discussed|covered|covered\s+in\s+the\s+meeting"
    r"|mentioned|mentioned\s+in\s+the\s+meeting|in\s+the\s+meeting"
    r"|in\s+this\s+meeting|from\s+the\s+meeting|of\s+the\s+meeting"
    r"|taught|learned))*"
    r"\s*"
    # Standalone meeting placeholders.
    r"|(?:the\s+)?(?:meeting|session|discussion|lecture|class|call|transcript|content|talk|presentation|topic|material)s?"
    r"(?:\s+(?:discussed|covered|mentioned|in\s+the\s+meeting))?\s*"
    # Bare quantifiers / pronouns.
    r"|(?:all|every|any)\s*(?:of\s+(?:it|them|the\s+above))?\s*"
    r"|(?:everything|anything|whatever|nothing|none)\s*"
    # Standalone residue of question forms: "What concepts were discussed?"
    # matched "what concepts" and left "were discussed" — accept it.
    r"|(?:were\s+)?(?:discussed|covered|covered\s+in\s+the\s+meeting"
    r"|mentioned|mentioned\s+in\s+the\s+meeting|taught|learned)\s*"
    # "what did we learn" / "what we learned" style residues.
    r"|(?:did\s+we\s+learn|we\s+learned)\s*"
    r"|me(?:\s+please)?\s*"
    r"|(?:this|that|these|those)\s*"
    r"|(?:please)\s*"
    r")\??\s*$",
    re.IGNORECASE,
)


def detect_intent(user_message: str) -> AtlasIntent:
    """Detect the user's intent from their message."""
    lower = user_message.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return intent
    return AtlasIntent.GENERAL_QUESTION


def _extract_quantity(user_message: str, intent: AtlasIntent) -> int | None:
    """Extract requested count for any intent that supports a count.

    Applies to quiz, action items, decisions, recommendations, concept
    explanation, and revision/flashcards. Returns None when no count is
    named (e.g. "summarize the meeting", "give me action items").
    """
    if intent == AtlasIntent.GENERAL_QUESTION:
        return None
    msg = user_message.lower()
    m = re.search(r"\b(\d{1,3})\b", msg)
    if m:
        try:
            n = int(m.group(1))
            if n > 0:
                return n
        except ValueError:
            pass
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
        "twenty": 20, "thirty": 30, "fifty": 50,
    }
    for w in (
        "fifty", "thirty", "twenty", "fifteen", "ten", "nine", "eight",
        "seven", "six", "five", "four", "three", "two", "one",
    ):
        if re.search(r"\b" + re.escape(w) + r"\b", msg):
            try:
                return words[w]
            except KeyError:
                pass
    return None


def _strip_punct_tail(topic: str) -> str:
    """Strip a trailing question mark / punctuation (kept out of the topic)."""
    return re.sub(r"[\?\.\!\,]+\s*$", "", topic).strip()


def _extract_topic(user_message: str, intent: AtlasIntent) -> str | None:
    """Isolate the focused topic from a user message.

    Strips the intent-bearing head phrase plus any trailing connective
    ("explain", "summarize the discussion about",
    "what decisions were made regarding", ...) and returns the residual
    topic. Falls back to None when nothing concrete remains, meaning the
    user made a meeting-wide request — the caller should then keep the
    existing behaviour (return all concepts / full summary / etc.).
    """
    if intent == AtlasIntent.GENERAL_QUESTION:
        # general Q&A: semantic retrieval already keys on the full query
        return None
    text = (user_message or "").strip()
    if not text:
        return None

    topic: str | None = None
    for pat in _TOPIC_PATTERNS.get(intent, []):
        m = re.match(pat, text, re.IGNORECASE)  # anchored at start
        if m:
            grp = m.group(1) if m.groups() else ""
            topic = _strip_punct_tail(grp)
            if topic:
                break

    if not topic:
        return None
    # Reject 1-char noise left-overs (e.g. the trailing "s" of "items") and
    # connective-only tails ("about", "on", "for") which carry no content.
    if len(topic) < 2:
        return None
    if re.fullmatch(r"(?:about|on|for|regarding|concerning|related\s+to|of)", topic, re.IGNORECASE):
        return None
    # Meeting-wide / generic placeholder → None (preserve existing behaviour).
    if _GENERIC_TOPIC_RE.match(topic):
        return None
    # Normalise whitespace, protect the topic from over-long tails.
    topic = re.sub(r"\s+", " ", topic).strip()
    if len(topic) > 200:
        topic = topic[:200].rsplit(" ", 1)[0]
    return topic or None


def parse_request(user_message: str) -> ParsedRequest:
    """Understand a user message: intent + requested topic + quantity.

    Slot this in right after intent detection, before retrieval. The returned
    ``topic`` (when not None) is a clean concept/entity/section name that
    should be passed as the retrieval query for semantic search; it lets
    Atlas respond about *phishing detection* instead of the whole meeting
    when the user says "Explain phishing detection".

    Behaviour:
      - "Explain phishing detection"     → CONCEPT_EXPLANATION, "phishing detection"
      - "Explain the concepts discussed" → CONCEPT_EXPLANATION, None
      - "Summarize the meeting"          → SUMMARY, None
      - "Decisions about AI ethics?"     → DECISIONS, "AI ethics"
    """
    intent = detect_intent(user_message)
    topic = _extract_topic(user_message, intent)
    quantity = _extract_quantity(user_message, intent)
    scope = Scope.TOPIC_ONLY if topic else Scope.MEETING_WIDE
    return ParsedRequest(intent=intent, topic=topic, scope=scope, quantity=quantity)
