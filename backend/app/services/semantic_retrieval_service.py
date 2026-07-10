"""Semantic Retrieval for Atlas."""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from app.core.logging import get_logger
from app.db.models.chunk_embedding import ChunkEmbedding

logger = get_logger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class RetrievedChunk:
    """A retrieved chunk with metadata from the original transcript segment."""

    chunk_text: str
    similarity: float
    start_time: str | None = None
    end_time: str | None = None
    speaker: str | None = None


class SemanticRetrievalService:
    """Retrieve top-k relevant chunks given a query embedding vector."""

    def __init__(
        self,
        *,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> None:
        self.top_k = top_k
        self.min_similarity = min_similarity

    def search(
        self,
        query_embedding: list[float],
        *,
        candidates: list[ChunkEmbedding],
    ) -> list[ChunkEmbedding]:
        """Rank candidates by cosine similarity and return top-k."""
        if not candidates:
            return []

        scored = []
        for c in candidates:
            sim = cosine_similarity(query_embedding, c.embedding)
            if sim >= self.min_similarity:
                scored.append((sim, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [c for _, c in scored[: self.top_k]]
        logger.info("semantic.retrieval.completed", extra={"top_k": len(results)})
        return results
