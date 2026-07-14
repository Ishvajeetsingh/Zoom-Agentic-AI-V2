"""Runtime configuration for the standalone Atlas backend.

All values are sourced from environment variables. Nothing here reads the
Zoom Agentic AI source tree - this module only describes *where* to reach
the baseline REST API and *how* the local HTTP client should behave.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split_csv(value: str) -> list[int]:
    out: list[int] = []
    for part in (value or "").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return out


@dataclass
class Settings:
    """Application settings. Construct via :func:`get_settings` so values
    are read lazily from the environment (test-friendly).
    """

    # Zoom Agentic AI REST API base URL (every client prefixes this).
    atlas_api_base_url: str

    # Outbound HTTP timeout (seconds).
    atlas_api_timeout: int

    # Optional API key forwarded as ``Authorization: Bearer <key>``.
    atlas_api_key: str

    # Retry policy for the shared HTTP client.
    atlas_api_max_retries: int
    atlas_api_retry_backoff_seconds: float

    # HTTP status codes that should trigger a retry.
    atlas_api_retry_status_codes: list[int] = field(default_factory=list)

    # Local server config.
    atlas_host: str = "0.0.0.0"
    atlas_port: int = 8090
    atlas_log_level: str = "info"


def _load_settings() -> Settings:
    return Settings(
        atlas_api_base_url=os.getenv(
            "ATLAS_API_BASE_URL", "http://localhost:8000/api/v1"
        ).rstrip("/"),
        atlas_api_timeout=int(os.getenv("ATLAS_API_TIMEOUT", "30")),
        atlas_api_key=os.getenv("ATLAS_API_KEY", ""),
        atlas_api_max_retries=int(os.getenv("ATLAS_API_MAX_RETRIES", "3")),
        atlas_api_retry_backoff_seconds=float(
            os.getenv("ATLAS_API_RETRY_BACKOFF_SECONDS", "0.5")
        ),
        atlas_api_retry_status_codes=_split_csv(
            os.getenv("ATLAS_API_RETRY_STATUS_CODES", "429,500,502,503,504")
        ),
        atlas_host=os.getenv("ATLAS_HOST", "0.0.0.0"),
        atlas_port=int(os.getenv("ATLAS_PORT", "8090")),
        atlas_log_level=os.getenv("ATLAS_LOG_LEVEL", "info"),
    )


# Cache one Settings instance per process. Tests can call ``get_settings.cache_clear``
# after changing the environment, but in normal use this is a singleton.
_cached_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, loaded on first use."""
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = _load_settings()
    return _cached_settings


def reset_settings() -> None:
    """Drop the cached settings. Primarily for tests that change env vars."""
    global _cached_settings
    _cached_settings = None
