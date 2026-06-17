"""Phase 3: webhook automation - link processing_runs to webhook_events

Revision ID: 20260601_0010
Revises: 20260601_0009
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0010"
down_revision: str | None = "20260601_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_runs",
        sa.Column(
            "webhook_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_processing_runs_webhook_event_id",
        "processing_runs",
        "webhook_events",
        ["webhook_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_processing_runs_webhook_event_id",
        "processing_runs",
        ["webhook_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_runs_webhook_event_id", table_name="processing_runs")
    op.drop_constraint(
        "fk_processing_runs_webhook_event_id",
        "processing_runs",
        type_="foreignkey",
    )
    op.drop_column("processing_runs", "webhook_event_id")
