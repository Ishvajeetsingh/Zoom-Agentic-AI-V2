import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    __table_args__ = (
        UniqueConstraint("transcript_id", "chunk_index", name="uq_transcript_chunks_index"),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    end_time: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    speakers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    segment_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    segment_range_start: Mapped[int | None] = mapped_column(Integer)
    segment_range_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transcript = relationship("Transcript", back_populates="chunks")
    questions = relationship("Question", back_populates="chunk", cascade="all, delete-orphan")
    learning_outputs = relationship("LearningOutput", back_populates="chunk", cascade="all, delete-orphan")
