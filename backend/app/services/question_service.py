"""Question generation orchestration service.

Consumes transcript chunks and calls the Ollama LLM to generate
assessment questions. This module wires the OllamaApiClient to the
chunking output but does NOT own the LangGraph workflow — that will
be added later as a separate orchestration layer.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.integrations.ollama.client import (
    GenerationResponse,
    OllamaApiClient,
    OllamaConnectionError,
    OllamaGenerateError,
    OllamaModelError,
)

logger = get_logger(__name__)

_THINK_OPEN = "\u003Cthink\u003E"
_THINK_CLOSE = "\u003C/think\u003E"
_THINKING_RE = re.compile(rf"^{re.escape(_THINK_OPEN)}.*?{re.escape(_THINK_CLOSE)}", re.DOTALL)


class QuestionGenerationError(AppError):
    """Raised when question generation cannot be completed."""


@dataclass(frozen=True)
class GeneratedQuestion:
    question_text: str
    question_type: str
    options: list[str]
    correct_answer: str
    explanation: str
    difficulty: str
    chunk_id: uuid.UUID | None = None


@dataclass(frozen=True)
class QuestionGenerationResult:
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID
    questions: list[GeneratedQuestion]
    total_questions: int
    model_used: str
    total_prompt_tokens: int | None = None
    total_completion_tokens: int | None = None
    total_duration_seconds: float | None = None


MCQ_SYSTEM_PROMPT = """You are an expert assessment author. Given a transcript chunk from a meeting, generate multiple-choice questions that test comprehension and application of the discussed material.

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


class QuestionService:
    def __init__(
        self,
        ollama_client: OllamaApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.config = config
        self.ollama = ollama_client or OllamaApiClient(config=config)

    _MIN_QUESTIONS_PER_CHUNK = 2
    _MAX_QUESTIONS_PER_CHUNK = 5

    @classmethod
    def _compute_question_count(cls, word_count: int) -> int:
        if word_count < 100:
            return 2
        if word_count < 250:
            return 3
        if word_count < 500:
            return 4
        return 5

    def generate_questions_from_chunk(
        self,
        chunk_text: str,
        chunk_id: uuid.UUID | None = None,
        *,
        num_questions: int | None = None,
        model: str | None = None,
    ) -> QuestionGenerationResult:
        if not chunk_text or not chunk_text.strip():
            logger.warning(
                "question_generation.empty_chunk",
                extra={"chunk_id": str(chunk_id) if chunk_id else None},
            )
            return QuestionGenerationResult(
                transcript_id=uuid.uuid4(),
                meeting_id=uuid.uuid4(),
                questions=[],
                total_questions=0,
                model_used=model or self.config.ollama_primary_model,
            )

        word_count = len(chunk_text.split())

        if num_questions is not None:
            target_count = num_questions
        else:
            target_count = self._compute_question_count(word_count)

        target_count = max(self._MIN_QUESTIONS_PER_CHUNK, min(target_count, self._MAX_QUESTIONS_PER_CHUNK))

        final_questions: list[GeneratedQuestion] = []
        final_response: GenerationResponse | None = None

        for attempt_target in [target_count, max(target_count - 1, 2), 2]:
            prompt = (
                f"Generate {attempt_target} multiple-choice questions from the following meeting transcript chunk.\n\n"
                f"--- TRANSCRIPT CHUNK ---\n{chunk_text}\n--- END CHUNK ---\n\n"
                f"Return a JSON array of {attempt_target} question objects."
            )

            logger.info(
                "question_generation.started",
                extra={
                    "chunk_id": str(chunk_id) if chunk_id else None,
                    "word_count": word_count,
                    "target_question_count": attempt_target,
                    "chunk_length": len(chunk_text),
                    "prompt_length": len(prompt),
                },
            )

            try:
                response = self.ollama.generate_json(
                    prompt,
                    model=model or self.config.ollama_primary_model,
                    system=MCQ_SYSTEM_PROMPT,
                    temperature=0.7,
                    max_tokens=self.config.max_chunk_tokens,
                )
            except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
                logger.exception(
                    "question_generation.llm_failed",
                    extra={
                        "chunk_id": str(chunk_id) if chunk_id else None,
                        "error": str(exc),
                    },
                )
                raise QuestionGenerationError(f"LLM generation failed: {exc}") from exc

            questions = self._parse_questions(response, chunk_id)

            if questions:
                final_questions = questions
                final_response = response
                break

            raw = response.response.strip()
            is_llm_error = False
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "error" in parsed:
                    is_llm_error = True
                    logger.warning(
                        "question_generation.llm_returned_error_retrying",
                        extra={
                            "chunk_id": str(chunk_id) if chunk_id else None,
                            "error_msg": str(parsed["error"])[:200],
                            "retrying_with_target": max(attempt_target - 1, 2) if attempt_target > 2 else None,
                        },
                    )
            except json.JSONDecodeError:
                pass

            final_response = response

            if not is_llm_error:
                break

        logger.info(
            "question_generation.completed",
            extra={
                "chunk_id": str(chunk_id) if chunk_id else None,
                "questions_generated": len(final_questions),
                "model_used": final_response.model if final_response else None,
                "prompt_tokens": final_response.prompt_tokens if final_response else None,
                "completion_tokens": final_response.completion_tokens if final_response else None,
                "duration_seconds": final_response.total_duration_seconds if final_response else None,
            },
        )

        return QuestionGenerationResult(
            transcript_id=uuid.uuid4(),
            meeting_id=uuid.uuid4(),
            questions=final_questions,
            total_questions=len(final_questions),
            model_used=final_response.model if final_response else (model or self.config.ollama_primary_model),
            total_prompt_tokens=final_response.prompt_tokens if final_response else None,
            total_completion_tokens=final_response.completion_tokens if final_response else None,
            total_duration_seconds=final_response.total_duration_seconds if final_response else None,
        )

    def _parse_questions(
        self,
        response: GenerationResponse,
        chunk_id: uuid.UUID | None = None,
    ) -> list[GeneratedQuestion]:
        raw = response.response.strip()
        if not raw:
            logger.warning("question_generation.empty_response")
            return []

        cleaned = self._strip_thinking_tokens(raw)

        items = self._robust_json_parse(cleaned)
        if items is None:
            logger.warning(
                "question_generation.json_parse_failed_all_methods",
                extra={"response_preview": cleaned[:500]},
            )
            return []

        if isinstance(items, dict):
            unwrapped = self._unwrap_dict_response(items, cleaned)
            if unwrapped is None:
                return []
            items = unwrapped

        if not isinstance(items, list):
            logger.warning(
                "question_generation.unexpected_response_format",
                extra={
                    "response_preview": cleaned[:500],
                    "parsed_type": type(items).__name__,
                },
            )
            return []

        questions: list[GeneratedQuestion] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                questions.append(
                    GeneratedQuestion(
                        question_text=str(item.get("question_text", "")),
                        question_type=str(item.get("question_type", "mcq")),
                        options=list(item.get("options", [])),
                        correct_answer=str(item.get("correct_answer", "")),
                        explanation=str(item.get("explanation", "")),
                        difficulty=str(item.get("difficulty", "medium")),
                        chunk_id=chunk_id,
                    )
                )
            except Exception:
                logger.warning(
                    "question_generation.question_parse_skipped",
                    extra={"item": str(item)[:100]},
                )
                continue

        return questions

    @staticmethod
    def _strip_thinking_tokens(text: str) -> str:
        stripped = _THINKING_RE.sub("", text).strip()
        if stripped != text.strip():
            logger.debug(
                "question_generation.thinking_tokens_stripped",
                extra={"original_len": len(text), "cleaned_len": len(stripped)},
            )
        return stripped

    @staticmethod
    def _robust_json_parse(text: str) -> list | dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        return QuestionService._extract_balanced_json(text)

    @staticmethod
    def _extract_balanced_json(text: str) -> list | dict | None:
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            pos = 0
            while True:
                idx = text.find(start_char, pos)
                if idx == -1:
                    break
                depth = 0
                in_string = False
                escape_next = False
                end_idx = -1
                for i in range(idx, len(text)):
                    ch = text[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if ch == "\\" and in_string:
                        escape_next = True
                        continue
                    if ch == '"':
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if ch == start_char:
                        depth += 1
                    elif ch == end_char:
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
                if end_idx != -1:
                    candidate = text[idx:end_idx]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                pos = idx + 1
        return None

    _KNOWN_WRAPPER_KEYS = ("questions", "mcq_questions", "result", "results", "data")

    def _unwrap_dict_response(self, data: dict, raw: str) -> list | None:
        for key in self._KNOWN_WRAPPER_KEYS:
            if key in data and isinstance(data[key], list):
                logger.info(
                    "question_generation.dict_unwrapped",
                    extra={"wrapper_key": key, "item_count": len(data[key])},
                )
                return data[key]

        list_keys = [k for k, v in data.items() if isinstance(v, list)]
        if len(list_keys) == 1:
            logger.info(
                "question_generation.dict_auto_unwrapped",
                extra={"wrapper_key": list_keys[0], "item_count": len(data[list_keys[0]])},
            )
            return data[list_keys[0]]

        if "error" in data:
            logger.warning(
                "question_generation.llm_returned_error",
                extra={"error": str(data["error"])[:200]},
            )
            return None

        logger.warning(
            "question_generation.unexpected_response_format",
            extra={
                "response_preview": raw[:500],
                "dict_keys": list(data.keys()),
                "list_valued_keys": list_keys,
            },
        )
        return None
