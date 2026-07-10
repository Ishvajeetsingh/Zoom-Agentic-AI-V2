"""Embedding Service for Atlas Semantic Search."""
import hashlib
import uuid

import httpx

from app.core.config import Settings, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EMBED_MODEL = "nomic-embed-text"
# Ollama /api/embeddings returns a single vector per input using /api/embeddings
# endpoint, or we can use /api/embed (batch) – here we use /api/embeddings for
# a single chunk and /api/embed for batching.


# ---------------------------------------------------------------------------
# Embedding Service
# ---------------------------------------------------------------------------

class EmbeddingServiceError(Exception):
    pass


class EmbeddingService:
    """Generates vector embeddings via Ollama."""

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.model = config.ollama_embedding_model or DEFAULT_EMBED_MODEL
        self.dim = config.ollama_embedding_dim or 768
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.ollama_base_url,
                timeout=httpx.Timeout(
                    connect=self.config.ollama_connect_timeout_seconds,
                    read=120.0,
                    write=10.0,
                    pool=30.0,
                ),
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """Return a single embedding vector for the given text."""
        target = model or self.model
        payload = {
            "model": target,
            "prompt": text,
            "options": {},
        }
        logger.info("embedding.generate.started", extra={"model": target, "text_length": len(text)})
        try:
            response = self.client.post("/api/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise EmbeddingServiceError(f"Ollama returned error: {data['error']}")
            vector = data.get("embedding")
            if vector is None:
                raise EmbeddingServiceError("Ollama response missing 'embedding'")
            if not isinstance(vector, list):
                raise EmbeddingServiceError(f"Unexpected embedding format: {type(vector)}")
            return vector
        except httpx.ConnectError as exc:
            raise EmbeddingServiceError(f"Cannot connect to Ollama at {self.config.ollama_base_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingServiceError(f"Ollama embeddings request failed: {exc.response.status_code}") from exc

    def embed_batch(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Generate embeddings for multiple texts in one request (if Ollama supports batch).

        Fallback: one-at-a-time if batch fails.
        """
        target = model or self.model
        if not texts:
            return []

        try:
            payload = {
                "model": target,
                "input": texts,
            }
            response = self.client.post("/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if embeddings and isinstance(embeddings, list) and len(embeddings) == len(texts):
                logger.info("embedding.generate_batch.completed", extra={"model": target, "count": len(texts)})
                return embeddings
            # Fallback
        except Exception:
            logger.warning("embedding.generate_batch.fallback", extra={"model": target, "count": len(texts)})

        # Fallback to individual calls
        result = []
        for t in texts:
            result.append(self.embed(t, model=target))
        return result


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Chunk Embedding Utilities
# ---------------------------------------------------------------------------

from sqlalchemy.orm import Session

from app.db.models.chunk_embedding import ChunkEmbedding as ChunkEmbeddingModel


class ChunkEmbeddingStore:
    """Database CRUD for chunk embeddings."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_chunk_id(self, chunk_id: uuid.UUID) -> ChunkEmbeddingModel | None:
        from sqlalchemy import select
        return self.db.scalar(select(ChunkEmbeddingModel).where(ChunkEmbeddingModel.chunk_id == chunk_id))

    def get_for_meeting(self, meeting_id: uuid.UUID, model: str) -> list[ChunkEmbeddingModel]:
        from sqlalchemy import select
        return list(self.db.scalars(
            select(ChunkEmbeddingModel)
            .where(ChunkEmbeddingModel.meeting_id == meeting_id)
            .where(ChunkEmbeddingModel.model == model)
            .order_by(ChunkEmbeddingModel.chunk_id)
        ).all())

    def upsert(self, *, chunk_id: uuid.UUID, transcript_id: uuid.UUID, meeting_id: uuid.UUID,
               chunk_text: str, embedding: list, model: str) -> ChunkEmbeddingModel:
        import hashlib
        txt_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
        record = self.get_by_chunk_id(chunk_id)
        if record is not None:
            record.embedding = embedding
            record.chunk_text = chunk_text
            record.chunk_text_hash = txt_hash
            record.model = model
        else:
            record = ChunkEmbeddingModel(
                chunk_id=chunk_id,
                transcript_id=transcript_id,
                meeting_id=meeting_id,
                chunk_text=chunk_text,
                chunk_text_hash=txt_hash,
                embedding=embedding,
                model=model,
            )
            self.db.add(record)
        self.db.flush()
        return record

    def delete_for_chunk(self, chunk_id: uuid.UUID) -> None:
        from sqlalchemy import delete
        self.db.execute(delete(ChunkEmbeddingModel).where(ChunkEmbeddingModel.chunk_id == chunk_id))
        self.db.flush()
