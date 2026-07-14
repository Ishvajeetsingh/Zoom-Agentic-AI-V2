"""Minimal structured logging for the standalone Atlas backend.

Mirrors the part of Zoom Agentic AI's logging ergonomic we actually need
without any coupling to its implementation. Produces JSON-ish key=value
lines and swallows extra context gracefully if no handlers are attached.
"""
from __future__ import annotations

import logging
import sys

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_configured = False


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once."""
    global _configured
    if _configured:
        return

    env_level = (level or "info").lower()
    logging.basicConfig(
        level=_LEVELS.get(env_level, logging.INFO),
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
