"""Phase 2: queue columns on processing_runs + processing_failures table

Revision ID: 20260601_0009
Revises: 20260601_0008
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0009"
down_revision: str | None = "20260601_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processing_runs", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("processing_runs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("processing_runs", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("processing_runs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_runs", sa.Column("locked_by", sa.String(100), nullable=True))
    op.add_column("processing_runs", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_runs", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_runs", sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_runs", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_processing_runs_priority", "processing_runs", ["priority"])
    op.create_index("ix_processing_runs_next_retry_at", "processing_runs", ["next_retry_at"])
    op.create_index("ix_processing_runs_locked_by", "processing_runs", ["locked_by"])

    op.create_table(
        "processing_failures",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("retry_eligible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("retry_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["processing_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_processing_failures_run_id", "processing_failures", ["run_id"])
    op.create_index("ix_processing_failures_step", "processing_failures", ["step"])


def downgrade() -> None:
    op.drop_index("ix_processing_failures_step", table_name="processing_failures")
    op.drop_index("ix_processing_failures_run_id", table_name="processing_failures")
    op.drop_table("processing_failures")

    op.drop_index("ix_processing_runs_locked_by", table_name="processing_runs")
    op.drop_index("ix_processing_runs_next_retry_at", table_name="processing_runs")
    op.drop_index("ix_processing_runs_priority", table_name="processing_runs")

    op.drop_column("processing_runs", "cancelled_at")
    op.drop_column("processing_runs", "picked_at")
    op.drop_column("processing_runs", "queued_at")
    op.drop_column("processing_runs", "locked_at")
    op.drop_column("processing_runs", "locked_by")
    op.drop_column("processing_runs", "next_retry_at")
    op.drop_column("processing_runs", "max_retries")
    op.drop_column("processing_runs", "retry_count")
    op.drop_column("processing_runs", "priority")
