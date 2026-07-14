"""Service-level helpers shared by Atlas services.

Contains only pure pass-through utilities (small data shaping for response
composition) — never business logic. Nothing here imports Zoom Agentic AI
internals.
"""
from __future__ import annotations

from typing import Any, Mapping


def coerce_mapping(value: Any) -> Mapping[str, Any]:
    """Return ``value`` if it is a mapping, otherwise an empty mapping.

    Lets services read fields off REST responses defensively without
    crashing when a remote route returns ``null`` (JSON null) for a list
    / detail endpoint.
    """
    if isinstance(value, Mapping):
        return value
    return {}


def coerce_list(value: Any) -> list[Any]:
    """Return ``value`` if it is a list, otherwise an empty list."""
    if isinstance(value, list):
        return value
    return []
