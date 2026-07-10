"""Conversation Memory Management for Atlas."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.message import Message

logger = get_logger(__name__)

# Token estimation (characters per token)
# Average English: ~4 chars per token; using conservative 3.5 for safety
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Roughly estimate token count from character count."""
    return int(len(text) / CHARS_PER_TOKEN)


@dataclass
class MemoryMessage:
    """A message in the conversation memory."""
    role: str  # "user" or "assistant"
    content: str


def _deduplicate_messages(messages: list[MemoryMessage]) -> list[MemoryMessage]:
    """Remove exact-duplicate messages based on role and content."""
    seen: set[tuple[str, str]] = set()
    unique: list[MemoryMessage] = []
    for msg in messages:
        key = (msg.role, msg.content)
        if key not in seen:
            seen.add(key)
            unique.append(msg)
    return unique


def build_conversation_memory(
    raw_messages: list[Message],
    max_turns: int | None = None,
) -> list[MemoryMessage]:
    """Build a deduplicated, filtered list of messages for the prompt.
    Keeps the current user message and the previous N conversation turns
    (pairs of user+assistant) in chronological order.
    """
    max_turns = max_turns or settings.atlas_max_history_turns

    # Filter out empty and malformed messages
    filtered: list[MemoryMessage] = []
    for msg in raw_messages:
        if not msg or not msg.role or not msg.content or not msg.content.strip():
            continue
        if msg.role not in ("user", "assistant"):
            continue
        content = msg.content.strip()
        # Prevent exact duplicates within the memory window
        if any(m.role == msg.role and m.content == content for m in filtered):
            continue
        filtered.append(MemoryMessage(role=msg.role, content=content))

    # Deduplicate (safety net)
    filtered = _deduplicate_messages(filtered)

    if not filtered:
        return []

    # A "turn" is a user+assistant pair.
    # We want to keep the current user message and up to max_turns previous pairs.
    # current_msg is the last message (most recent), which should be the current user message.
    current_msg: MemoryMessage | None = None
    if filtered[-1].role == "user":
        current_msg = filtered.pop()
        history = filtered
    else:
        history = filtered

    # Collect pairs from the end (most recent) of history.
    pairs: list[tuple[MemoryMessage, MemoryMessage]] = []
    i = len(history) - 1
    while i > 0:
        if history[i].role == "assistant" and history[i - 1].role == "user":
            pairs.append((history[i - 1], history[i]))
            i -= 2
        else:
            i -= 1

    # Trim to most recent max_turns, then reassemble chronologically.
    selected_pairs = pairs[:max_turns]
    final_history: list[MemoryMessage] = []
    for user_msg, assistant_msg in reversed(selected_pairs):
        final_history.append(user_msg)
        final_history.append(assistant_msg)

    if current_msg:
        final_history.append(current_msg)
    return final_history


def format_conversation_memory(messages: list[MemoryMessage]) -> str:
    """Format a list of memory messages into a single prompt string."""
    lines: list[str] = []
    for msg in messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)


def build_llm_prompt_with_budget(
    system_prompt_text: str,
    conversation_messages: list[Message],
    max_total_tokens: int | None = None,
    max_turns: int | None = None,
) -> tuple[str, str]:
    """Build the LLM prompt, managing the total context budget.

    Priority (high to low):
    1. System Prompt (always included fully)
    2. Current User Message (always included fully)
    3. Recent Conversation History (trimmed first if over budget)

    Never trims retrieved semantic chunks before conversation history.
    """
    max_total_tokens = max_total_tokens or settings.atlas_max_total_context_tokens

    # Build memory with max_turns limit
    memory = build_conversation_memory(conversation_messages, max_turns=max_turns)

    # Separate current message from history
    if not memory:
        # No valid memory, return system with empty prompt
        return system_prompt_text, ""

    current_msg: MemoryMessage | None = None
    if memory[-1].role == "user":
        current_msg = memory[-1]
        history = memory[:-1]
    else:
        history = memory
        current_msg = None

    # Format current message (always present)
    current_text = f"User: {current_msg.content}" if current_msg else ""

    # Calculate token budgets
    system_tokens = estimate_tokens(system_prompt_text)
    current_tokens = estimate_tokens(current_text)

    # Reserve space for system and current message
    available_history = max(0, max_total_tokens - system_tokens - current_tokens)

    # Build history text
    history_text = format_conversation_memory(history)

    # Trim oldest history messages first if over budget
    if estimate_tokens(history_text) > available_history:
        history_list = list(history)
        while history_list and estimate_tokens(format_conversation_memory(history_list)) > available_history:
            history_list.pop(0)
        history_text = format_conversation_memory(history_list)

    # Assemble final prompt
    if history_text:
        prompt_text = f"{history_text}\n{current_text}"
    else:
        prompt_text = current_text

    return system_prompt_text, prompt_text