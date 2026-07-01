"""Add classification metadata columns to questions and learning_outputs

Revision ID: 20260601_0014
Revises: 20260601_0013
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0014"
down_revision: str | None = "20260601_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("category", sa.String(50), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("bloom_taxonomy", sa.String(30), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("educational_score", sa.Float, nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("relevance_score", sa.Float, nullable=True),
    )

    op.add_column(
        "learning_outputs",
        sa.Column("category", sa.String(50), nullable=True),
    )
    op.add_column(
        "learning_outputs",
        sa.Column("bloom_taxonomy", sa.String(30), nullable=True),
    )
    op.add_column(
        "learning_outputs",
        sa.Column("educational_score", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("questions", "relevance_score")
    op.drop_column("questions", "educational_score")
    op.drop_column("questions", "bloom_taxonomy")
    op.drop_column("questions", "category")

    op.drop_column("learning_outputs", "educational_score")
    op.drop_column("learning_outputs", "bloom_taxonomy")
    op.drop_column("learning_outputs", "category")
