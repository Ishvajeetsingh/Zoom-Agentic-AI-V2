"""processing_runs table

Revision ID: 20260601_0008
Revises: 20260601_0007
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0008"
down_revision: str | None = "20260601_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transcript_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meeting_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("current_step", sa.String(50), nullable=True),
        sa.Column("steps_completed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_steps", sa.BigInteger(), nullable=False, server_default="5"),
        sa.Column("step_results", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_duration_seconds", sa.Float(), nullable=True),
        sa.Column("questions_generated", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_processing_runs_transcript_id", "processing_runs", ["transcript_id"])
    op.create_index("ix_processing_runs_meeting_id", "processing_runs", ["meeting_id"])
    op.create_index("ix_processing_runs_status", "processing_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_processing_runs_status", table_name="processing_runs")
    op.drop_index("ix_processing_runs_meeting_id", table_name="processing_runs")
    op.drop_index("ix_processing_runs_transcript_id", table_name="processing_runs")
    op.drop_table("processing_runs")
