"""Phase 5: Multi-account support + auto sync

Revision ID: 20260601_0012
Revises: 20260601_0011
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0012"
down_revision: str | None = "20260601_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zoom_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("zoom_account_id", sa.String(255), nullable=False, unique=True),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("client_secret", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("token_url", sa.String(512), nullable=False, server_default="https://zoom.us/oauth/token"),
        sa.Column("api_base_url", sa.String(512), nullable=False, server_default="https://api.zoom.us/v2"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_zoom_accounts_zoom_account_id", "zoom_accounts", ["zoom_account_id"], unique=True)
    op.create_index("ix_zoom_accounts_enabled", "zoom_accounts", ["enabled"])
    op.create_index("ix_zoom_accounts_is_default", "zoom_accounts", ["is_default"])

    op.create_table(
        "sync_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("zoom_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auto_sync_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("sync_interval_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("lookback_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("auto_process", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(50), nullable=True),
        sa.Column("last_sync_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_configs_zoom_account_id", "sync_configs", ["zoom_account_id"])

    op.create_table(
        "sync_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("zoom_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("meetings_discovered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("transcripts_discovered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("transcripts_queued", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
    )
    op.create_index("ix_sync_history_zoom_account_id", "sync_history", ["zoom_account_id"])
    op.create_index("ix_sync_history_sync_type", "sync_history", ["sync_type"])
    op.create_index("ix_sync_history_status", "sync_history", ["status"])

    op.add_column("meetings", sa.Column("zoom_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_meetings_zoom_account_id", "meetings", ["zoom_account_id"])


def downgrade() -> None:
    op.drop_index("ix_meetings_zoom_account_id", table_name="meetings")
    op.drop_column("meetings", "zoom_account_id")

    op.drop_index("ix_sync_history_status", table_name="sync_history")
    op.drop_index("ix_sync_history_sync_type", table_name="sync_history")
    op.drop_index("ix_sync_history_zoom_account_id", table_name="sync_history")
    op.drop_table("sync_history")

    op.drop_index("ix_sync_configs_zoom_account_id", table_name="sync_configs")
    op.drop_table("sync_configs")

    op.drop_index("ix_zoom_accounts_is_default", table_name="zoom_accounts")
    op.drop_index("ix_zoom_accounts_enabled", table_name="zoom_accounts")
    op.drop_index("ix_zoom_accounts_zoom_account_id", table_name="zoom_accounts")
    op.drop_table("zoom_accounts")
