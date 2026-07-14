"""Shared HTTP client used by every Zoom Agentic AI REST client.

This module *only* knows how to make JSON HTTP calls against a remote
baseline (Zoom Agentic AI). It deliberately:

- Has **no** dependency on Zoom Agentic AI's codebase.
- Applies a single retry / timeout / auth policy via :class:`Settings`.
- Returns parsed JSON; typed clients (in this package) shape the output.

Retry policy: exponential backoff with the configured base, retrying only
the HTTP status codes set via ``ATLAS_API_RETRY_STATUS_CODES``. Network
errors (connect/read timeouts) are retried up to ``atlas_api_max_retries``
times; other exceptions propagate immediately.
"""
from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping

import requests

from app.core.config.settings import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AtlasAPIError(RuntimeError):
    """Raised when a call to the Zoom Agentic AI REST API fails."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class _RetryPolicy:
    max_retries: int
    backoff_seconds: float
    retry_status_codes: frozenset[int]


class BaseHTTPClient:
    """Thin JSON-over-HTTP client for the Zoom Agentic AI baseline.

    All typed clients in this package should subclass this and add typed
    methods. ``BaseHTTPClient`` only handles transport concerns (base URL,
    auth, timeout, retries, error mapping).
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
        api_key: str | None = None,
        *,
        session: requests.Session | None = None,
        settings: Settings | None = None,
    ) -> None:
        s = settings or get_settings()
        self.base_url = (base_url or s.atlas_api_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else s.atlas_api_timeout
        self.api_key = api_key if api_key is not None else s.atlas_api_key
        self._session = session or requests.Session()
        self._policy = _RetryPolicy(
            max_retries=max(0, s.atlas_api_max_retries),
            backoff_seconds=max(0.0, s.atlas_api_retry_backoff_seconds),
            retry_status_codes=frozenset(s.atlas_api_retry_status_codes or []),
        )

    # ------------------------------------------------------------------
    # Public verbs
    # ------------------------------------------------------------------
    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=dict(params) if params else None)

    def post(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return self._request(
            "POST", path, params=dict(params) if params else None, json_body=json_body
        )

    def put(
        self,
        path: str,
        *,
        json_body: Any | None = None,
    ) -> Any:
        return self._request("PUT", path, json_body=json_body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        url = f"{self.base_url}/{path}" if path else self.base_url
        # Validate it parses; raises on malformed input.
        urllib.parse.urlparse(url)
        return url

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any | None = None,
    ) -> Any:
        url = self._url(path)
        attempts = 0
        max_attempts = self._policy.max_retries + 1
        last_exc: Exception | None = None
        last_status: int | None = None
        while attempts < max_attempts:
            attempts += 1
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body if json_body is not None else None,
                    timeout=self.timeout,
                    headers=self._headers(),
                )
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                last_exc = exc
                logger.warning(
                    "atlas_http.transport_error",
                    extra={
                        "method": method,
                        "url": url,
                        "attempt": attempts,
                        "error": str(exc),
                    },
                )
                continue

            last_status = response.status_code
            if (
                response.status_code in self._policy.retry_status_codes
                and attempts < max_attempts
            ):
                self._sleep_backoff(attempts)
                continue

            if 200 <= response.status_code < 300:
                if response.status_code == 204 or not response.content:
                    return None
                try:
                    return response.json()
                except ValueError as exc:
                    raise AtlasAPIError(
                        f"Invalid JSON from {url}: {exc}",
                        status_code=response.status_code,
                        body=response.text,
                    ) from exc

            # Non-retry status -> raise immediately.
            body: Any = None
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise AtlasAPIError(
                f"{method} {path} -> {response.status_code}",
                status_code=response.status_code,
                body=body,
            )

        # Exhausted retries on transport errors.
        if last_exc is not None:
            raise AtlasAPIError(
                f"{method} {path} failed after {attempts} attempts: {last_exc}"
            ) from last_exc
        raise AtlasAPIError(
            f"{method} {path} -> {last_status} after {attempts} attempts",
            status_code=last_status,
        )

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self._policy.backoff_seconds * (2 ** (attempt - 1))
        if delay > 0:
            time.sleep(delay)
