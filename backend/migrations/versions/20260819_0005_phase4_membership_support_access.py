"""Add Phase 4 membership delivery and support access state.

Revision ID: 20260819_0005
Revises: 20260818_0004
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0005"
down_revision: str | None = "20260818_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_memberships",
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organization_memberships",
        sa.Column("email_delivery_status", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "email_delivery_status_valid",
        "organization_memberships",
        "email_delivery_status IS NULL OR email_delivery_status IN ('queued', 'sent', 'failed')",
    )

    op.create_table(
        "support_access_grants",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("platform_admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("btrim(reason) <> ''", name="reason_not_blank"),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked')", name="status_valid"),
        sa.CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_support_access_grants_organization"
        ),
        sa.ForeignKeyConstraint(
            ["platform_admin_user_id"],
            ["users.id"],
            name="fk_support_access_grants_platform_admin_user",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="fk_support_access_grants_granted_by"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["users.id"], name="fk_support_access_grants_revoked_by"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_support_access_grants"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_support_access_grants_organization_id_id"
        ),
    )
    op.create_index(
        "uq_support_access_grants_active_target",
        "support_access_grants",
        ["organization_id", "platform_admin_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_support_access_grants_organization_created_at_id",
        "support_access_grants",
        ["organization_id", "created_at", "id"],
    )
    op.create_index(
        "ix_support_access_grants_organization_expires_at",
        "support_access_grants",
        ["organization_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_access_grants_organization_expires_at",
        table_name="support_access_grants",
    )
    op.drop_index(
        "ix_support_access_grants_organization_created_at_id",
        table_name="support_access_grants",
    )
    op.drop_index("uq_support_access_grants_active_target", table_name="support_access_grants")
    op.drop_table("support_access_grants")
    op.drop_constraint(
        "email_delivery_status_valid", "organization_memberships", type_="check"
    )
    op.drop_column("organization_memberships", "email_delivery_status")
    op.drop_column("organization_memberships", "invited_at")
