from __future__ import annotations

import time

import httpx

from app.core.config import Settings, settings
from app.core.logging import get_logger
from app.integrations.ollama.client import (
    GenerationResponse,
    OllamaConnectionError,
    OllamaGenerateError,
    OllamaModelError,
)


logger = get_logger(__name__)


class GroqApiClient:
    """
    Groq adapter implementing the same generation interface
    used by OllamaApiClient.

    This allows the existing question-generation,
    learning-output, and meeting-insights services to
    work with Groq without changing their prompt or
    response-processing logic.
    """

    def __init__(
        self,
        config: Settings = settings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._client = http_client
        self._owned_client = False

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            if not self.config.groq_api_key:
                raise OllamaConnectionError(
                    "GROQ_API_KEY is not configured"
                )

            self._client = httpx.Client(
                base_url=self.config.groq_base_url,
                headers={
                    "Authorization": (
                        f"Bearer {self.config.groq_api_key}"
                    ),
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(
                    self.config.groq_timeout_seconds
                ),
            )

            self._owned_client = True

        return self._client

    def close(self) -> None:
        if (
            self._owned_client
            and self._client is not None
        ):
            self._client.close()
            self._client = None
            self._owned_client = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        retry_attempts: int | None = None,
    ) -> GenerationResponse:
        return self._generate(
            prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            retry_attempts=retry_attempts,
            json_mode=False,
        )

    def generate_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        retry_attempts: int | None = None,
    ) -> GenerationResponse:
        return self._generate(
            prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            retry_attempts=retry_attempts,
            json_mode=True,
        )

    def _generate(
        self,
        prompt: str,
        *,
        model: str | None,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
        retry_attempts: int | None,
        json_mode: bool,
    ) -> GenerationResponse:

        # Existing services may still pass the configured
        # Ollama model explicitly. In Groq mode translate
        # those model names to the configured Groq model.
        target_model = (
            self.config.groq_model
            if (
                not model
                or model == self.config.ollama_primary_model
                or model == self.config.ollama_fallback_model
            )
            else model
        )

        attempts = (
            retry_attempts
            or self.config.groq_retry_attempts
        )

        messages: list[dict[str, str]] = []

        if system:
            messages.append(
                {
                    "role": "system",
                    "content": system,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        payload: dict = {
            "model": target_model,
            "messages": messages,
        }

        if temperature is not None:
            payload["temperature"] = temperature

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if json_mode:
            payload["response_format"] = {
                "type": "json_object"
            }

        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            start = time.monotonic()

            try:
                response = self.client.post(
                    "/chat/completions",
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                choices = data.get("choices") or []

                if not choices:
                    raise OllamaGenerateError(
                        "Groq returned no choices"
                    )

                content = (
                    choices[0]
                    .get("message", {})
                    .get("content", "")
                )

                usage = data.get("usage") or {}

                duration_seconds = (
                    time.monotonic() - start
                )

                result = GenerationResponse(
                    model=data.get(
                        "model",
                        target_model,
                    ),
                    response=content or "",
                    done=True,
                    total_duration_ns=int(
                        duration_seconds
                        * 1_000_000_000
                    ),
                    prompt_eval_count=usage.get(
                        "prompt_tokens"
                    ),
                    eval_count=usage.get(
                        "completion_tokens"
                    ),
                )

                logger.info(
                    "groq.generate.completed",
                    extra={
                        "model": result.model,
                        "response_length": len(
                            result.response
                        ),
                        "prompt_tokens": (
                            result.prompt_tokens
                        ),
                        "completion_tokens": (
                            result.completion_tokens
                        ),
                        "duration_seconds": (
                            result.total_duration_seconds
                        ),
                        "json_mode": json_mode,
                    },
                )

                return result

            except httpx.ConnectError as exc:
                last_error = exc

                logger.warning(
                    "groq.connection_failed",
                    extra={
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                )

            except httpx.TimeoutException as exc:
                last_error = exc

                logger.warning(
                    "groq.timeout",
                    extra={
                        "model": target_model,
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                )

            except httpx.HTTPStatusError as exc:
                last_error = exc

                status_code = (
                    exc.response.status_code
                )

                if status_code == 404:
                    raise OllamaModelError(
                        f"Groq model "
                        f"'{target_model}' "
                        f"was not found"
                    ) from exc

                if status_code in {
                    400,
                    401,
                    403,
                }:
                    raise OllamaGenerateError(
                        "Groq request rejected "
                        f"with status {status_code}: "
                        f"{exc.response.text[:300]}"
                    ) from exc

                logger.warning(
                    "groq.http_error_retry",
                    extra={
                        "model": target_model,
                        "status_code": status_code,
                        "attempt": attempt,
                        "attempts": attempts,
                    },
                )

            except httpx.HTTPError as exc:
                last_error = exc

                logger.warning(
                    "groq.http_error",
                    extra={
                        "model": target_model,
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                )

            except OllamaGenerateError:
                raise

            if attempt < attempts:
                time.sleep(attempt)

        if isinstance(
            last_error,
            (
                httpx.ConnectError,
                httpx.TimeoutException,
            ),
        ):
            raise OllamaConnectionError(
                "Unable to reach Groq after "
                f"{attempts} attempts: "
                f"{last_error}"
            ) from last_error

        raise OllamaGenerateError(
            "Groq generation failed after "
            f"{attempts} attempts: "
            f"{last_error}"
        )