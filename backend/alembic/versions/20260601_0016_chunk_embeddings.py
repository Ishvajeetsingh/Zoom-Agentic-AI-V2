"""Alembic migration: Add chunk_embeddings table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0016_chunk_embeddings"
down_revision: str | None = "20260601_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["transcript_chunks.chunk_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id"),
    )
    # Create two composite indexes for the common Atlas query patterns
    op.create_index(
        op.f("ix_chunk_embeddings_meeting_id"), "chunk_embeddings", ["meeting_id"], unique=False
    )
    op.create_index(
        op.f("ix_chunk_embeddings_meeting_id_model"), "chunk_embeddings", ["meeting_id", "model"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chunk_embeddings_meeting_id_model"), table_name="chunk_embeddings")
    op.drop_index(op.f("ix_chunk_embeddings_meeting_id"), table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
