"""Add Phase 3 organization and platform model configuration.

Revision ID: 20260818_0004
Revises: 20260818_0003
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0004"
down_revision: str | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
    )
    op.execute("UPDATE organizations SET normalized_name = lower(btrim(name))")
    op.alter_column("organizations", "normalized_name", nullable=False)
    op.create_unique_constraint(
        "uq_organizations_normalized_name",
        "organizations",
        ["normalized_name"],
    )
    op.create_check_constraint(
        "normalized_name_canonical",
        "organizations",
        "normalized_name = lower(btrim(name))",
    )

    op.create_table(
        "platform_model_configurations",
        sa.Column("singleton_key", sa.Integer(), server_default="1", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "usage_tracking_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
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
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("max_retries >= 0", name="max_retries_nonnegative"),
        sa.CheckConstraint("singleton_key = 1", name="singleton_key_valid"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        sa.CheckConstraint("timeout_seconds > 0", name="timeout_seconds_positive"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_platform_model_configurations"),
        sa.UniqueConstraint("singleton_key", name="uq_platform_model_configurations_singleton"),
    )
    op.execute(
        """
        INSERT INTO platform_model_configurations (
            id, singleton_key, timeout_seconds, max_retries,
            usage_tracking_enabled, status, version
        ) VALUES (
            '00000000-0000-0000-0000-000000000004', 1, 60, 3, true, 'active', 1
        )
        """
    )


def downgrade() -> None:
    op.drop_table("platform_model_configurations")
    op.drop_constraint("normalized_name_canonical", "organizations", type_="check")
    op.drop_constraint("uq_organizations_normalized_name", "organizations", type_="unique")
    op.drop_column("organizations", "normalized_name")
