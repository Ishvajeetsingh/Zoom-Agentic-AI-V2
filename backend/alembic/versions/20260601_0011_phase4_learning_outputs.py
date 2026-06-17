"""Phase 4: meeting_insights + learning_outputs tables

Revision ID: 20260601_0011
Revises: 20260601_0010
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0011"
down_revision: str | None = "20260601_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "transcript_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_text", sa.Text, nullable=False),
        sa.Column("key_concepts", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("action_items", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_duration_seconds", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_meeting_insights_transcript_id", "meeting_insights", ["transcript_id"], unique=True)
    op.create_index("ix_meeting_insights_meeting_id", "meeting_insights", ["meeting_id"])

    op.create_table(
        "learning_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "transcript_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transcript_chunks.chunk_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("output_type", sa.String(30), nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("difficulty", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_learning_outputs_transcript_id", "learning_outputs", ["transcript_id"])
    op.create_index("ix_learning_outputs_meeting_id", "learning_outputs", ["meeting_id"])
    op.create_index("ix_learning_outputs_chunk_id", "learning_outputs", ["chunk_id"])
    op.create_index("ix_learning_outputs_output_type", "learning_outputs", ["output_type"])
    op.create_index(
        "ix_learning_outputs_transcript_output_type",
        "learning_outputs",
        ["transcript_id", "output_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_outputs_transcript_output_type", table_name="learning_outputs")
    op.drop_index("ix_learning_outputs_output_type", table_name="learning_outputs")
    op.drop_index("ix_learning_outputs_chunk_id", table_name="learning_outputs")
    op.drop_index("ix_learning_outputs_meeting_id", table_name="learning_outputs")
    op.drop_index("ix_learning_outputs_transcript_id", table_name="learning_outputs")
    op.drop_table("learning_outputs")

    op.drop_index("ix_meeting_insights_meeting_id", table_name="meeting_insights")
    op.drop_index("ix_meeting_insights_transcript_id", table_name="meeting_insights")
    op.drop_table("meeting_insights")
