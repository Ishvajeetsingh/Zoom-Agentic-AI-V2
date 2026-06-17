import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_format: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="metadata_received", index=True)
    transcript_filename: Mapped[str | None] = mapped_column(String(255))
    raw_file_path: Mapped[str | None] = mapped_column(Text)
    processed_file_path: Mapped[str | None] = mapped_column(Text)
    zoom_file_id: Mapped[str | None] = mapped_column(String(255), index=True)
    zoom_recording_type: Mapped[str | None] = mapped_column(String(100), index=True)
    file_type: Mapped[str | None] = mapped_column(String(50))
    file_extension: Mapped[str | None] = mapped_column(String(50))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    recording_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    play_url: Mapped[str | None] = mapped_column(Text)
    download_url: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(20))
    segment_count: Mapped[int | None] = mapped_column(BigInteger)
    word_count: Mapped[int | None] = mapped_column(BigInteger)
    parse_error: Mapped[str | None] = mapped_column(Text)
    cleaned_segment_count: Mapped[int | None] = mapped_column(BigInteger)
    cleaned_word_count: Mapped[int | None] = mapped_column(BigInteger)
    cleaning_error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int | None] = mapped_column(BigInteger)
    chunking_error: Mapped[str | None] = mapped_column(Text)
    question_count: Mapped[int | None] = mapped_column(BigInteger)
    generation_model: Mapped[str | None] = mapped_column(String(100))
    generation_error: Mapped[str | None] = mapped_column(Text)
    download_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    download_error: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    meeting = relationship("Meeting", back_populates="transcripts")
    segments = relationship(
        "TranscriptSegment",
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.sequence_number",
    )
    chunks = relationship(
        "TranscriptChunk",
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptChunk.chunk_index",
    )
    questions = relationship(
        "Question",
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="Question.created_at",
    )
    meeting_insights = relationship(
        "MeetingInsights",
        back_populates="transcript",
        cascade="all, delete-orphan",
        uselist=False,
    )
    learning_outputs = relationship(
        "LearningOutput",
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="LearningOutput.created_at",
    )
