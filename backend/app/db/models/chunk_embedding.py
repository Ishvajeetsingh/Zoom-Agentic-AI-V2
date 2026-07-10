"""Transcript chunk embedding table."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcript_chunks.chunk_id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    # Keep denormalized FKs for fast queries
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Store sparse vectors as JSONB for cross-database support
    # Clients that need high performance can switch to pgvector
    embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
