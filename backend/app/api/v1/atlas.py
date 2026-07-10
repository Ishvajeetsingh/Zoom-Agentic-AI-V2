import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.repositories import atlas as atlas_repo
from app.db.session import SessionLocal
from app.integrations.ollama.client import OllamaApiClient, OllamaConnectionError, OllamaModelError, OllamaGenerateError
from app.services.atlas_context_service import build_meeting_context
from app.services.atlas_citation_service import (
    CitationRegistry,
    format_context_with_citations,
    finalize_response,
)
from app.services.atlas_intent_router import detect_intent, AtlasIntent
from app.services.atlas_memory_service import build_llm_prompt_with_budget
from app.services.atlas_educational_intelligence import (
    build_summary_response,
    build_concept_explanation_response,
    build_quiz_response,
    build_revision_guide_response,
    build_action_items_response,
    build_decisions_response,
    build_recommendations_response,
)
from app.services.atlas_prompt_builders import (
    build_summary_prompt,
    build_concept_explanation_prompt,
    build_quiz_prompt,
    build_revision_guide_prompt,
    build_action_items_prompt,
    build_decisions_prompt,
    build_recommendations_prompt,
)
from app.schemas.atlas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListOut,
    ConversationSummary,
    ConversationUpdate,
    MessageIn,
    MessageOut,
)

router = APIRouter()
logger = get_logger(__name__)


def _build_system_prompt(context_str: str) -> str:
    return (
        "You are Atlas, a Meeting Intelligence Assistant. You help users understand meetings, "
        "explore learning material, generate quizzes, explain concepts, and answer questions. "
        "You are currently discussing the following meeting. Base your answers ONLY on the provided meeting context, "
        "especially the 'Relevant Meeting Segments' below. Do NOT use outside knowledge. "
        "If the answer is not contained in the provided meeting segments, clearly state that the "
        "selected meeting does not contain that information.\n"
        "Citations: cite ONLY the numbered IDs declared in the 'Sources you may cite' block of the context. "
        "Place citations inline after supported statements. Do NOT write your own 'Sources' section; the "
        "backend assembles it from the IDs you actually used.\n\n"
        f"{context_str}"
    )


def _build_chat_prompt(messages: list[Message]) -> str:
    """Format conversation messages into a single prompt for the LLM."""
    lines: list[str] = []
    for msg in messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)


def _build_chat_inputs(
    db: Session,
    conversation: Conversation,
    messages: list[Message],
    payload: MessageIn,
) -> tuple[str, str | None, str | None, CitationRegistry | None]:
    """Build the LLM request parameters.
    Returns (system_prompt, llm_prompt, direct_response, citation_registry).
    * If direct_response is not None, return it directly (no LLM call).
    * If direct_response is None, call the LLM with (system_prompt, llm_prompt).
    * citation_registry is the backend-owned citation registry used to append
      the deterministic Sources section via finalize_response(). It is None
      only when there is no meeting context (the no-meeting fallback).
    """
    meeting_context = build_meeting_context(db, conversation, user_query=payload.content)
    meeting_context_str, registry = format_context_with_citations(meeting_context)

    if not meeting_context.has_context:
        no_meeting_text = (
            "# No meeting selected\n\n"
            "Please **choose a meeting** before asking questions.\n\n"
            "Once a meeting is selected, I can help you:\n\n"
            "- **Summarize** the meeting\n"
            "- **Explain concepts** discussed\n"
            "- **Generate quizzes** from the content\n"
            "- **Review action items**\n"
            "- **Review decisions**\n"
            "- **Explain learning outputs**\n"
            "- **Answer questions** grounded in the selected meeting\n\n"
            "Go ahead and pick a meeting — I'll get to work."
        )
        return "", None, no_meeting_text, None

    system_prompt = _build_system_prompt(meeting_context_str)
    intent = detect_intent(payload.content)
    logger.info("atlas.intent_detected", extra={"intent": intent.value, "conversation_id": str(conversation.id)})

    if intent == AtlasIntent.SUMMARY:
        response_obj = build_summary_response(meeting_context)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            return system_prompt, build_summary_prompt(meeting_context_str), None, registry

    elif intent == AtlasIntent.CONCEPT_EXPLANATION:
        response_obj = build_concept_explanation_response(meeting_context)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            return system_prompt, build_concept_explanation_prompt(meeting_context_str), None, registry

    elif intent == AtlasIntent.QUIZ_REQUEST:
        response_obj = build_quiz_response(db, meeting_context, user_message=payload.content)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            mcqs = response_obj.artifacts.get("mcqs", [])
            # Build the deterministic, verbatim quiz directly from stored MCQs.
            # The LLM is never asked to regenerate the questions. If any MCQ is
            # missing its explanation, route ONLY an explanation-generation
            # prompt (never a question-regeneration prompt).
            if response_obj.artifacts.get("needs_explanation_generation"):
                quiz_data_str = _format_quiz_for_prompt(mcqs)
                return (
                    system_prompt,
                    build_quiz_prompt(meeting_context_str, quiz_data_str),
                    None,
                    registry,
                )
            # Fully formed quiz: render it as the stored wording, with no LLM
            # involvement whatsoever.
            requested = response_obj.artifacts.get("returned_count", len(mcqs))
            quiz_text = _render_quiz_markdown(mcqs, requested)
            # Append the backend-owned Sources block if any citations are used
            # (none generally, but kept consistent with every other response).
            return system_prompt, None, finalize_response(quiz_text, registry), registry

    elif intent == AtlasIntent.REVISION_REQUEST:
        response_obj = build_revision_guide_response(meeting_context)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            revision_data_str = _format_revision_for_prompt(response_obj.artifacts)
            return system_prompt, build_revision_guide_prompt(meeting_context_str, revision_data_str), None, registry

    elif intent == AtlasIntent.ACTION_ITEMS:
        response_obj = build_action_items_response(meeting_context)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            action_items = response_obj.artifacts.get("action_items", [])
            action_items_str = _format_items_for_prompt(action_items, "item_text")
            return system_prompt, build_action_items_prompt(meeting_context_str, action_items_str), None, registry

    elif intent == AtlasIntent.DECISIONS:
        response_obj = build_decisions_response(meeting_context)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            decisions = response_obj.artifacts.get("decisions", [])
            decisions_str = _format_items_for_prompt(decisions, "decision")
            return system_prompt, build_decisions_prompt(meeting_context_str, decisions_str), None, registry

    elif intent == AtlasIntent.RECOMMENDATIONS:
        response_obj = build_recommendations_response(meeting_context)
        if not response_obj.artifacts:
            return system_prompt, None, response_obj.content, registry
        else:
            recommendations = response_obj.artifacts.get("recommendations", [])
            recommendations_str = _format_items_for_prompt(recommendations, "text")
            if not recommendations_str:
                recommendations_str = response_obj.artifacts.get("summary", "")
            return system_prompt, build_recommendations_prompt(meeting_context_str, recommendations_str), None, registry

    else:
        _, prompt = build_llm_prompt_with_budget(
            system_prompt,
            messages,
            max_total_tokens=settings.atlas_max_total_context_tokens,
            max_turns=settings.atlas_max_history_turns,
        )
        return system_prompt, prompt, None, registry


def _persist_streamed_message(conversation_id, content):
    """Persist a completed assistant message in a fresh DB session."""
    db2 = SessionLocal()
    try:
        if content:
            atlas_repo.create_message(
                db2,
                conversation_id=conversation_id,
                role="assistant",
                content=content,
            )
            conv = atlas_repo.get_conversation(db2, conversation_id)
            if conv:
                conv.updated_at = func.now()
                db2.flush()
            db2.commit()
    except Exception:
        db2.rollback()
        raise
    finally:
        db2.close()


@router.post("/conversations", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    session_id = payload.session_id if payload.session_id else uuid.uuid4().hex
    conversation = atlas_repo.create_conversation(
        db,
        meeting_id=payload.meeting_id,
        session_id=session_id,
        title=payload.title,
    )
    return ConversationDetail(
        id=conversation.id,
        session_id=conversation.session_id,
        meeting_id=conversation.meeting_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
        messages=[],
    )


@router.get("/conversations", response_model=ConversationListOut)
def list_conversations(
    meeting_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ConversationListOut:
    rows, total = atlas_repo.list_conversations(
        db,
        meeting_id=meeting_id,
        offset=offset,
        limit=limit,
        order_desc=True,
    )

    # Calculate message count for each conversation
    items: list[ConversationSummary] = []
    for conv in rows:
        message_count = db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
        ) or 0
        items.append(
            ConversationSummary(
                id=conv.id,
                session_id=conv.session_id,
                meeting_id=conv.meeting_id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=message_count,
            )
        )

    return ConversationListOut(items=items, total=total, offset=offset, limit=limit)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    conversation = atlas_repo.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = atlas_repo.get_messages_for_conversation(db, conversation_id)

    return ConversationDetail(
        id=conversation.id,
        session_id=conversation.session_id,
        meeting_id=conversation.meeting_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(messages),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationDetail)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="No fields to update")

    conversation = atlas_repo.update_conversation(db, conversation_id, **update_data)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = atlas_repo.get_messages_for_conversation(db, conversation_id)
    return ConversationDetail(
        id=conversation.id,
        session_id=conversation.session_id,
        meeting_id=conversation.meeting_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(messages),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    success = atlas_repo.delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return None


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    db: Session = Depends(get_db),
) -> MessageOut:
    conversation = atlas_repo.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    message = atlas_repo.create_message(
        db,
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    return MessageOut.model_validate(message)


def _call_ollama(prompt: str, system: str) -> str:
    """Call Ollama and return the response text, or a fallback message on error."""
    ollama = OllamaApiClient()
    try:
        response = ollama.generate(
            prompt=prompt,
            system=system,
            model=settings.ollama_primary_model,
        )
        return response.response
    except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
        logger.error("atlas.llm_generation_failed", extra={"error": str(exc)})
        return "I'm sorry, I'm having trouble connecting to my brain right now. Please try again later."
    finally:
        ollama.close()


@router.post("/conversations/{conversation_id}/chat", response_model=MessageOut)
def chat_with_llm(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    db: Session = Depends(get_db),
) -> MessageOut:
    """Store user message, get LLM response, store assistant message, return it."""
    conversation = atlas_repo.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # 1. Store user message
    user_msg = atlas_repo.create_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )

    # 2. Get conversation history
    messages = atlas_repo.get_messages_for_conversation(db, conversation_id)

    # 3. Build LLM inputs
    system_prompt, prompt, direct_response, registry = _build_chat_inputs(
        db, conversation, messages, payload
    )

    # 4. Early return for missing meeting or direct response
    if direct_response is not None:
        assistant_content = finalize_response(direct_response, registry)
    else:
        raw = _call_ollama(prompt, system_prompt)
        assistant_content = finalize_response(raw, registry)

    # 5. Store assistant message
    assistant_msg = atlas_repo.create_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
    )

    # Ensure updated_at reflects latest activity
    conversation.updated_at = func.now()
    db.flush()

    return MessageOut.model_validate(assistant_msg)


@router.post("/conversations/{conversation_id}/chat/stream")
def chat_with_llm_stream(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    db: Session = Depends(get_db),
):
    """Stream the LLM response as Server-Sent Events."""
    conversation = atlas_repo.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # 1. Store user message
    atlas_repo.create_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )

    # 2. Get conversation history
    messages = atlas_repo.get_messages_for_conversation(db, conversation_id)

    # 3. Build LLM inputs
    system_prompt, prompt, direct_response, registry = _build_chat_inputs(
        db, conversation, messages, payload
    )

    # 4. Prepare the generator
    accumulated_text = [""]

    def _event_generator():
        """Yield SSE events from the LLM stream."""
        if direct_response is not None:
            finalized = finalize_response(direct_response, registry)
            accumulated_text[0] = finalized
            yield f"data: {json.dumps({'text': finalized})}\n\n"
            return

        ollama = OllamaApiClient()
        try:
            for chunk in ollama.generate_stream(
                prompt,
                system=system_prompt,
                model=settings.ollama_primary_model,
            ):
                accumulated_text[0] += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        finally:
            ollama.close()

    def _generator_with_persistence():
        """Wrap the generator to persist after successful completion."""
        completed = False
        try:
            yield from _event_generator()
            completed = True
        finally:
            if completed:
                # Persist the finalized response: strip any inline Sources
                # block the model produced and append the backend-owned one
                # computed from the citation registry.
                finalized = finalize_response(accumulated_text[0], registry)
                _persist_streamed_message(conversation_id, finalized)

    return StreamingResponse(
        _generator_with_persistence(),
        media_type="text/event-stream",
    )


def _format_quiz_for_prompt(mcqs: list[dict]) -> str:
    """Format MCQs into a string for the prompt builder.

    Used ONLY when some MCQs are missing an explanation and we ask the LLM to
    produce explanations (never to regenerate questions). Question text and
    options are passed verbatim; citation markers the model might place there
    are stripped before display by _strip_citations_from_mcqs().
    """
    if not mcqs:
        return ""
    lines = []
    for i, q in enumerate(mcqs, 1):
        lines.append(f"{i}. {q.get('question', '')}")
        for opt in q.get("options", []):
            letter = opt.get("letter", "") if isinstance(opt, dict) else ""
            text = opt.get("text", "") if isinstance(opt, dict) else str(opt)
            lines.append(f"   {letter}. {text}")
        answer = q.get("answer", "")
        if answer:
            lines.append(f"   Answer: {answer}")
        explanation = q.get("explanation", "")
        if not explanation:
            lines.append("   Explanation: <generate a brief, meeting-grounded explanation>")
        else:
            lines.append(f"   Explanation: {explanation}")
        lines.append("")
    return "\n".join(lines)


def _strip_inline_citations(text: str) -> str:
    """Remove inline citation markers ([1], [2], ...) from question text and options."""
    if not text:
        return text
    out = __import__("re").sub(r"\s*\[\d{1,3}\]\s*", " ", text)
    out = __import__("re").sub(r"\s+", " ", out).strip()
    return out


def _render_quiz_markdown(mcqs: list[dict], requested_count: int | None = None) -> str:
    """Render the stored, professor-ranked quiz as final markdown.

    The wording is the EXACT stored wording (only stray citation markers are
    stripped from the question text and the options — citations may live only
    in the explanation). The LLM is NOT involved; questions are never
    regenerated. Format mirrors professional ChatGPT-style quiz output:

      # Quiz (N Questions)
      ---
      ## Question 1
      <text>
      **A.** option A
      ...
      **Answer**
      B
      **Explanation**
      ...
      ---

    Option labels are normalized: any stored format (A:, A., A), A-) is
    rendered uniformly as **A.** <body>. Every option occupies exactly one
    markdown line.
    """
    if not mcqs:
        return "No quizzes are available for this meeting yet."

    import re as _re

    def _normalise_label(letter: str | None, idx: int) -> str:
        """Always return a single uppercase A-D letter for the option label."""
        if letter:
            ltr = letter.strip().upper()
            if len(ltr) == 1 and "A" <= ltr <= "D":
                return ltr
        return chr(ord("A") + idx) if 0 <= idx < 4 else str(idx + 1)

    # Matches a leading option label, case-insensitive, with optional
    # surrounding parentheses and one trailing separator ( : . - ) ).
    #   (c): Option   C. Option   (A) Option   C: Option   C- Option
    # Iterating strips nested/composite labels one fragment at a time
    # while only ever matching at the very start of the remaining text.
    _LABEL_RE = _re.compile(r"^\s*\(?\s*([A-Da-d])\s*\)?\s*[:.\-)]?\s*")

    def _strip_label_prefix(text: str) -> str:
        """Remove any leading option-label fragments (optionally nested) from body.

        Handles 'A:', 'A.', 'A)', 'A-', '(a):', '(C)', etc. Iterates so a
        composite body like '(c): It confirms ...' is fully stripped down to
        'It confirms ...'. Never affects characters later in the sentence.
        """
        body = text or ""
        while True:
            m = _LABEL_RE.match(body)
            if not m:
                break
            stripped = body[m.end():]
            if stripped == body:
                break
            body = stripped
        return body.strip()

    def _opt_item(opt, idx: int) -> tuple[str, str]:
        """Return (normalised_letter, body) for an option regardless of shape.

        Stored shapes supported:
          - {"letter": "A", "text": "Option A"}
          - {"letter": "A.", "text": "A. Option A"}
          - "A. Option A", "A: Option A", "A) Option A", "A- Option A"
          - "Option A" (no label)
        The returned letter is ALWAYS uppercase A-D; the body ALWAYS has its
        leading label stripped so we never emit 'A. (c): Option' or any
        duplicated/embedded label.
        """
        if isinstance(opt, dict):
            raw_letter = opt.get("letter")
            raw_body = opt.get("text") or opt.get("body") or ""
            if not raw_body:
                raw_body = str(opt)
            letter = _normalise_label(raw_letter if isinstance(raw_letter, str) else None, idx)
            body = _strip_label_prefix(str(raw_body))
            return letter, body
        s = str(opt).strip()
        m = _LABEL_RE.match(s)
        if m:
            letter = m.group(1).upper()
            body = s[m.end():].strip()
        else:
            letter = _normalise_label(None, idx)
            body = s
        return letter, body

    out: list[str] = []

    # Optional shortfall note (kept short and outside the numbered structure).
    if requested_count is not None and len(mcqs) < requested_count:
        out.append(
            f"Here are {len(mcqs)} of the {requested_count} questions you asked for. "
            "The meeting doesn't contain more ranked questions yet."
        )
        out.append("")  # blank line before the quiz heading

    out.append(f"# Quiz ({len(mcqs)} Questions)")
    out.append("")
    out.append("---")

    for i, q in enumerate(mcqs, 1):
        question_text = _strip_inline_citations(q.get("question", ""))

        out.append("")
        out.append(f"## Question {i}")
        out.append("")  # blank line between the heading and the question text
        out.append(question_text)
        out.append("")  # blank line before the options

        # Render each option as a markdown unordered-list item so
        # ReactMarkdown + remark-gfm renders each option as its own block
        # instead of merging consecutive **A.** ... lines into one paragraph.
        # Positional order is authoritative: every stored option is emitted,
        # no option is silently dropped. The label is always normalized to
        # A-D from the option's position, so the rendered output is uniform
        # even if the stored letters are missing, duplicated, or malformed.
        options = q.get("options", []) or []
        for idx, opt in enumerate(options[:4]):
            letter, body = _opt_item(opt, idx)
            # Always use the positional label (A, B, C, D) so the rendered
            # quiz is uniform even if stored letters are wrong/duplicated.
            letter = chr(ord("A") + idx) if 0 <= idx < 4 else letter
            body = _strip_inline_citations(body).strip()
            if not body:
                # Keep the slot visible so the quiz never silently loses
                # an option (e.g. option C disappearing).
                body = "—"
            out.append(f"- **{letter}.** {body}")
        out.append("")  # blank line after the full option list

        answer = (q.get("answer") or "").strip()
        if answer:
            # Normalise the answer label too (e.g. "A." -> "A") for display.
            ans_match = _LABEL_RE.match(answer)
            if ans_match:
                answer = ans_match.group(1).upper()
            else:
                answer = answer.strip()
            out.append("")  # blank line before the Answer label
            out.append("**Answer**")
            out.append("")  # blank line between label and value
            out.append(answer)

        explanation = (q.get("explanation") or "").strip()
        out.append("")  # blank line before the Explanation label
        out.append("**Explanation**")
        out.append("")  # blank line between label and value
        if explanation:
            # Citations stay inside the explanation.
            out.append(explanation)
        else:
            out.append("_No explanation was generated for this question._")

        out.append("")
        out.append("---")

    # Join with single newlines; the explicit blank lines ("") provide the
    # required visual spacing and produce clean paragraph breaks in markdown.
    return "\n".join(out).rstrip()


def _format_revision_for_prompt(artifacts: dict) -> str:
    """Format revision artifacts into a string for the prompt builder."""
    lines = []
    summary = artifacts.get("summary", "")
    if summary:
        lines.append(f"Summary:\n{summary}\n")
    key_concepts = artifacts.get("key_concepts", [])
    if key_concepts:
        lines.append("Key Concepts:\n" + "\n".join(f"• {c}" for c in key_concepts) + "\n")
    key_takeaways = artifacts.get("key_takeaways", [])
    if key_takeaways:
        lines.append("Key Takeaways:\n" + "\n".join(f"• {t}" for t in key_takeaways) + "\n")
    return "\n".join(lines)


def _format_items_for_prompt(items: list[dict], key: str) -> str:
    """Format a list of dict items into a bullet string for the prompt builder."""
    if not items:
        return ""
    lines = []
    for item in items:
        if isinstance(item, dict):
            text = item.get(key, "")
        else:
            text = str(item)
        if text:
            lines.append(f"• {text}")
    return "\n".join(lines)
