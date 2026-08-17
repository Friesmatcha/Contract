"""Add Phase 2 authentication and session security.

Revision ID: 20260817_0002
Revises: 20260817_0001
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0002"
down_revision: str | None = "20260817_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("attempts > 0", name="attempts_positive"),
        sa.PrimaryKeyConstraint("action", "key_hash", "window_started_at"),
    )
    op.create_index(
        "ix_auth_rate_limits_window_started_at",
        "auth_rate_limits",
        ["window_started_at"],
        unique=False,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(csrf_hash) = 64", name="csrf_hash_valid"),
        sa.CheckConstraint("char_length(token_hash) = 64", name="token_hash_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["idle_expires_at", "absolute_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_user_active",
        "auth_sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )

    op.create_table(
        "auth_one_time_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("membership_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("purpose IN ('password_reset', 'invitation')", name="purpose_valid"),
        sa.CheckConstraint("char_length(token_hash) = 64", name="token_hash_valid"),
        sa.CheckConstraint(
            "(purpose = 'password_reset' AND user_id IS NOT NULL AND membership_id IS NULL) OR "
            "(purpose = 'invitation' AND user_id IS NULL AND membership_id IS NOT NULL)",
            name="subject_matches_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["organization_memberships.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_auth_one_time_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_auth_one_time_tokens_token_hash"),
    )
    op.create_index(
        "ix_auth_one_time_tokens_expires_at",
        "auth_one_time_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_one_time_tokens_membership_active",
        "auth_one_time_tokens",
        ["membership_id", "used_at"],
        unique=False,
    )
    op.create_index(
        "uq_auth_one_time_tokens_active_password_reset",
        "auth_one_time_tokens",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("purpose = 'password_reset' AND used_at IS NULL"),
    )
    op.create_index(
        "uq_auth_one_time_tokens_active_invitation",
        "auth_one_time_tokens",
        ["membership_id"],
        unique=True,
        postgresql_where=sa.text("purpose = 'invitation' AND used_at IS NULL"),
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_auth_one_time_tokens_active_invitation")
    op.execute("DROP INDEX IF EXISTS uq_auth_one_time_tokens_active_password_reset")
    op.drop_index("ix_auth_one_time_tokens_membership_active", table_name="auth_one_time_tokens")
    op.drop_index("ix_auth_one_time_tokens_expires_at", table_name="auth_one_time_tokens")
    op.drop_table("auth_one_time_tokens")
    op.drop_index("ix_auth_sessions_user_active", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_auth_rate_limits_window_started_at", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
