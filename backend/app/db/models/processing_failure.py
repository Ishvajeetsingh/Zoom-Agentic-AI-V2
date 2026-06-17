import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProcessingFailure(Base):
    __tablename__ = "processing_failures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[Text] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text)
    retry_eligible: Mapped[bool] = mapped_column(default=True, nullable=False)
    retry_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    run = relationship("ProcessingRun", back_populates="failures")
