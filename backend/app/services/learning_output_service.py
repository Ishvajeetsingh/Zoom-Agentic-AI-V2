"""Learning output generation service.

Generates flashcards and short questions per transcript chunk
using a single LLM call per chunk (separate from MCQ generation).
"""

from __future__ import annotations
from app.llm.provider import create_llm_client, get_generation_model

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

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINKING_RE = re.compile(rf"^{re.escape(_THINK_OPEN)}.*?{re.escape(_THINK_CLOSE)}", re.DOTALL)


class LearningOutputGenerationError(AppError):
    pass


@dataclass(frozen=True)
class FlashcardData:
    front: str
    back: str
    category: str | None = None


@dataclass(frozen=True)
class ShortQuestionData:
    question_text: str
    sample_answer: str
    difficulty: str


@dataclass(frozen=True)
class ChunkLearningResult:
    chunk_id: uuid.UUID | None
    flashcards: list[FlashcardData]
    short_questions: list[ShortQuestionData]
    model_used: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_duration_seconds: float | None = None


LEARNING_OUTPUT_SYSTEM_PROMPT = """You are an expert educational content creator. Given a transcript chunk from a meeting, generate flashcards and short-answer questions that help learners review the material.

Rules:
- Flashcards must have a clear "front" (question/prompt) and "back" (answer/explanation).
- Short-answer questions must have a concise question and a sample answer.
- Assign difficulty to short questions: easy, medium, or hard.
- Optionally assign a category to flashcards (e.g., "definition", "process", "decision").
- Do NOT invent information not present in the transcript.
- Return a JSON object with two keys.

JSON schema:
{
  "flashcards": [
    {"front": "string", "back": "string", "category": "string or null"}
  ],
  "short_questions": [
    {"question_text": "string", "sample_answer": "string", "difficulty": "easy|medium|hard"}
  ]
}"""


class LearningOutputService:
    def __init__(
        self,
        ollama_client: OllamaApiClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.config = config
        self.ollama = ollama_client or create_llm_client(config)

    def generate_from_chunk(
        self,
        chunk_text: str,
        chunk_id: uuid.UUID | None = None,
        *,
        num_flashcards: int | None = None,
        num_short_questions: int | None = None,
        model: str | None = None,
    ) -> ChunkLearningResult:
        if not chunk_text or not chunk_text.strip():
            logger.warning(
                "learning_output.empty_chunk",
                extra={"chunk_id": str(chunk_id) if chunk_id else None},
            )
            return ChunkLearningResult(
                chunk_id=chunk_id,
                flashcards=[],
                short_questions=[],
                model_used=model or self.config.ollama_primary_model,
            )

        fc_count = num_flashcards or self.config.output_flashcards_per_chunk
        sq_count = num_short_questions or self.config.output_short_questions_per_chunk

        prompt = (
            f"Generate {fc_count} flashcards and {sq_count} short-answer questions "
            f"from the following meeting transcript chunk.\n\n"
            f"--- TRANSCRIPT CHUNK ---\n{chunk_text}\n--- END CHUNK ---\n\n"
            f"Return a JSON object with 'flashcards' and 'short_questions' arrays."
        )

        logger.info(
            "learning_output.generation_started",
            extra={
                "chunk_id": str(chunk_id) if chunk_id else None,
                "flashcards_requested": fc_count,
                "short_questions_requested": sq_count,
            },
        )

        try:
            response = self.ollama.generate_json(
                prompt,
                model=model or self.config.ollama_primary_model,
                system=LEARNING_OUTPUT_SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=self.config.max_chunk_tokens,
            )
        except (OllamaConnectionError, OllamaModelError, OllamaGenerateError) as exc:
            logger.exception(
                "learning_output.llm_failed",
                extra={
                    "chunk_id": str(chunk_id) if chunk_id else None,
                    "error": str(exc),
                },
            )
            raise LearningOutputGenerationError(f"LLM generation failed: {exc}") from exc

        flashcards, short_questions = self._parse_response(response)

        logger.info(
            "learning_output.generation_completed",
            extra={
                "chunk_id": str(chunk_id) if chunk_id else None,
                "flashcards_generated": len(flashcards),
                "short_questions_generated": len(short_questions),
                "model_used": response.model,
            },
        )

        return ChunkLearningResult(
            chunk_id=chunk_id,
            flashcards=flashcards,
            short_questions=short_questions,
            model_used=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_duration_seconds=response.total_duration_seconds,
        )

    def _parse_response(
        self, response: GenerationResponse
    ) -> tuple[list[FlashcardData], list[ShortQuestionData]]:
        raw = response.response.strip()
        if not raw:
            logger.warning("learning_output.empty_response")
            return [], []

        cleaned = _THINKING_RE.sub("", raw).strip()

        data = self._robust_json_parse(cleaned)
        if data is None:
            logger.warning(
                "learning_output.json_parse_failed",
                extra={"response_preview": cleaned[:500]},
            )
            return [], []

        if not isinstance(data, dict):
            logger.warning(
                "learning_output.unexpected_format",
                extra={"parsed_type": type(data).__name__},
            )
            return [], []

        flashcards = self._parse_flashcards(data.get("flashcards", []))
        short_questions = self._parse_short_questions(data.get("short_questions", []))

        return flashcards, short_questions

    @staticmethod
    def _parse_flashcards(items: list) -> list[FlashcardData]:
        result: list[FlashcardData] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            front = str(item.get("front", "")).strip()
            back = str(item.get("back", "")).strip()
            if not front or not back:
                continue
            category = item.get("category")
            if category is not None:
                category = str(category).strip() or None
            result.append(FlashcardData(front=front, back=back, category=category))
        return result

    @staticmethod
    def _parse_short_questions(items: list) -> list[ShortQuestionData]:
        result: list[ShortQuestionData] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            question_text = str(item.get("question_text", "")).strip()
            sample_answer = str(item.get("sample_answer", "")).strip()
            difficulty = str(item.get("difficulty", "medium")).strip().lower()
            if not question_text or not sample_answer:
                continue
            if difficulty not in ("easy", "medium", "hard"):
                difficulty = "medium"
            result.append(
                ShortQuestionData(
                    question_text=question_text,
                    sample_answer=sample_answer,
                    difficulty=difficulty,
                )
            )
        return result

    @staticmethod
    def _robust_json_parse(text: str) -> dict | list | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        return LearningOutputService._extract_balanced_json(text)

    @staticmethod
    def _extract_balanced_json(text: str) -> dict | list | None:
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
