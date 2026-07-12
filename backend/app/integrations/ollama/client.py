from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from app.core.config import Settings, settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaConnectionError(ExternalServiceError):
    """Raised when Ollama server cannot be reached."""


class OllamaModelError(ExternalServiceError):
    """Raised when requested model is not available."""


class OllamaGenerateError(ExternalServiceError):
    """Raised when generation request fails."""


@dataclass(frozen=True)
class OllamaModelInfo:
    name: str
    size: int | None = None
    quantization: str | None = None
    family: str | None = None
    parameter_size: str | None = None


@dataclass(frozen=True)
class GenerationResponse:
    model: str
    response: str
    done: bool
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None

    @property
    def total_duration_seconds(self) -> float | None:
        if self.total_duration_ns is None:
            return None
        return self.total_duration_ns / 1_000_000_000

    @property
    def prompt_tokens(self) -> int | None:
        return self.prompt_eval_count

    @property
    def completion_tokens(self) -> int | None:
        return self.eval_count


@dataclass
class OllamaHealthStatus:
    available: bool
    models: list[str] = field(default_factory=list)
    primary_model_loaded: bool = False
    fallback_model_loaded: bool = False
    error: str | None = None
    response_latency_seconds: float | None = None


class OllamaApiClient:
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
            self._client = httpx.Client(
                base_url=self.config.ollama_base_url,
                timeout=httpx.Timeout(
                    connect=self.config.ollama_connect_timeout_seconds,
                    read=self.config.ollama_read_timeout_seconds,
                    write=self.config.ollama_connect_timeout_seconds,
                    pool=self.config.ollama_connect_timeout_seconds,
                ),
            )
            self._owned_client = True
        return self._client

    def close(self) -> None:
        if self._owned_client and self._client is not None:
            self._client.close()
            self._client = None
            self._owned_client = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def is_available(self) -> OllamaHealthStatus:
        start = time.monotonic()
        try:
            response = self.client.get("/")
            latency = time.monotonic() - start
            response.raise_for_status()

            models = self.list_model_names()
            primary_loaded = self.config.ollama_primary_model in models
            fallback_loaded = self.config.ollama_fallback_model in models

            return OllamaHealthStatus(
                available=True,
                models=models,
                primary_model_loaded=primary_loaded,
                fallback_model_loaded=fallback_loaded,
                response_latency_seconds=round(latency, 3),
            )
        except httpx.ConnectError as exc:
            latency = time.monotonic() - start
            logger.warning(
                "ollama.connection_failed",
                extra={"base_url": self.config.ollama_base_url, "error": str(exc)},
            )
            return OllamaHealthStatus(
                available=False,
                error=f"Connection refused: {self.config.ollama_base_url}",
                response_latency_seconds=round(latency, 3),
            )
        except httpx.HTTPError as exc:
            latency = time.monotonic() - start
            logger.warning(
                "ollama.health_check_failed",
                extra={"error": str(exc)},
            )
            return OllamaHealthStatus(
                available=False,
                error=str(exc),
                response_latency_seconds=round(latency, 3),
            )

    def list_models(self) -> list[OllamaModelInfo]:
        try:
            response = self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.config.ollama_base_url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaConnectionError(f"Ollama list models request failed: {exc}") from exc

        models = []
        for model_data in data.get("models", []):
            details = model_data.get("details") or {}
            models.append(
                OllamaModelInfo(
                    name=model_data.get("name", ""),
                    size=model_data.get("size"),
                    quantization=details.get("quantization_level"),
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                )
            )
        return models

    def list_model_names(self) -> list[str]:
        return [m.name for m in self.list_models()]

    def ensure_model_available(self, model: str | None = None) -> str:
        target = model or self.config.ollama_primary_model
        try:
            available = self.list_model_names()
        except OllamaConnectionError:
            raise
        except Exception as exc:
            raise OllamaModelError(f"Failed to check model availability: {exc}") from exc

        if target in available:
            return target

        fallback = self.config.ollama_fallback_model
        if fallback and fallback != target and fallback in available:
            logger.warning(
                "ollama.model_fallback",
                extra={"requested_model": target, "fallback_model": fallback},
            )
            return fallback

        raise OllamaModelError(
            f"Model '{target}' not found. Available models: {available}"
        )

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
        target_model = self.ensure_model_available(model)
        attempts = retry_attempts or self.config.ollama_retry_attempts
        backoff = self.config.ollama_retry_backoff_seconds

        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._do_generate(
                    target_model, prompt, system, temperature, max_tokens
                )
            except (OllamaGenerateError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "ollama.generate_retry",
                    extra={
                        "model": target_model,
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                )
                if attempt < attempts:
                    time.sleep(backoff * attempt)

        raise OllamaGenerateError(
            f"Generation failed after {attempts} attempts for model '{target_model}': {last_error}"
        ) from last_error

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
        target_model = self.ensure_model_available(model)
        attempts = retry_attempts or self.config.ollama_retry_attempts
        backoff = self.config.ollama_retry_backoff_seconds

        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._do_generate_json(
                    target_model, prompt, system, temperature, max_tokens
                )
            except (OllamaGenerateError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "ollama.generate_json_retry",
                    extra={
                        "model": target_model,
                        "attempt": attempt,
                        "attempts": attempts,
                        "error": str(exc),
                    },
                )
                if attempt < attempts:
                    time.sleep(backoff * attempt)

        raise OllamaGenerateError(
            f"JSON generation failed after {attempts} attempts for model '{target_model}': {last_error}"
        ) from last_error

    def _do_generate(
        self,
        model: str,
        prompt: str,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> GenerationResponse:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["options"] = {"temperature": temperature}
        if max_tokens is not None:
            payload.setdefault("options", {})["num_predict"] = max_tokens

        logger.info(
            "ollama.generate.started",
            extra={
                "model": model,
                "prompt_length": len(prompt),
                "has_system": system is not None,
            },
        )

        try:
            response = self.client.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.config.ollama_base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaGenerateError(
                f"Ollama generation timed out for model '{model}'"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 404:
                raise OllamaModelError(f"Model '{model}' not found on Ollama server") from exc
            raise OllamaGenerateError(
                f"Ollama generation failed with status {status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaGenerateError(f"Ollama generation request failed: {exc}") from exc

        if data.get("error"):
            raise OllamaGenerateError(f"Ollama returned error: {data['error']}")

        result = GenerationResponse(
            model=data.get("model", model),
            response=data.get("response", ""),
            done=data.get("done", True),
            total_duration_ns=data.get("total_duration"),
            load_duration_ns=data.get("load_duration"),
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
        )

        logger.info(
            "ollama.generate.completed",
            extra={
                "model": result.model,
                "response_length": len(result.response),
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "duration_seconds": result.total_duration_seconds,
            },
        )

        return result

    def _do_generate_json(
        self,
        model: str,
        prompt: str,
        system: str | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> GenerationResponse:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["options"] = {"temperature": temperature}
        if max_tokens is not None:
            payload.setdefault("options", {})["num_predict"] = max_tokens

        logger.info(
            "ollama.generate_json.started",
            extra={
                "model": model,
                "prompt_length": len(prompt),
                "has_system": system is not None,
            },
        )

        try:
            response = self.client.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.config.ollama_base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaGenerateError(
                f"Ollama JSON generation timed out for model '{model}'"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 404:
                raise OllamaModelError(f"Model '{model}' not found on Ollama server") from exc
            raise OllamaGenerateError(
                f"Ollama JSON generation failed with status {status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaGenerateError(f"Ollama JSON generation request failed: {exc}") from exc

        if data.get("error"):
            raise OllamaGenerateError(f"Ollama returned error: {data['error']}")

        result = GenerationResponse(
            model=data.get("model", model),
            response=data.get("response", ""),
            done=data.get("done", True),
            total_duration_ns=data.get("total_duration"),
            load_duration_ns=data.get("load_duration"),
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
        )

        logger.info(
            "ollama.generate_json.completed",
            extra={
                "model": result.model,
                "response_length": len(result.response),
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "duration_seconds": result.total_duration_seconds,
            },
        )

        return result

    def generate_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Stream a generation request from Ollama /api/generate.

        Yields partial response tokens as they arrive.
        Raises OllamaConnectionError, OllamaModelError, OllamaGenerateError.
        """
        target_model = self.ensure_model_available(model)

        payload: dict = {
            "model": target_model,
            "prompt": prompt,
            "stream": True,
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["options"] = {"temperature": temperature}
        if max_tokens is not None:
            payload.setdefault("options", {})["num_predict"] = max_tokens

        try:
            with self.client.stream("POST", "/api/generate", json=payload) as response:
                response.raise_for_status()
                try:
                    for raw_line in response.iter_lines():
                        if not raw_line:
                            continue
                        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                        if not line.strip():
                            continue
                        try:
                            import json
                            data = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise OllamaGenerateError(f"Invalid JSON from Ollama stream: {line}") from exc

                        if data.get("error"):
                            raise OllamaGenerateError(f"Ollama returned error: {data['error']}")

                        chunk = data.get("response", "")
                        done = data.get("done", False)
                        yield chunk

                        if done:
                            break
                finally:
                    response.close()  # type: ignore[union-attr]
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.config.ollama_base_url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaGenerateError(f"Ollama streaming request failed: {exc}") from exc



