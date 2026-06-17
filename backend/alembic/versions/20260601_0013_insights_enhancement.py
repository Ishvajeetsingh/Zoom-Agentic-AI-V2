"""Add key_takeaways, learning_outcomes, topics, decisions, recommendations to meeting_insights

Revision ID: 20260601_0013
Revises: 20260601_0012
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0013"
down_revision: str | None = "20260601_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meeting_insights",
        sa.Column("key_takeaways", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_insights",
        sa.Column("learning_outcomes", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_insights",
        sa.Column("topics", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_insights",
        sa.Column("decisions", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "meeting_insights",
        sa.Column("recommendations", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("meeting_insights", "recommendations")
    op.drop_column("meeting_insights", "decisions")
    op.drop_column("meeting_insights", "topics")
    op.drop_column("meeting_insights", "learning_outcomes")
    op.drop_column("meeting_insights", "key_takeaways")
