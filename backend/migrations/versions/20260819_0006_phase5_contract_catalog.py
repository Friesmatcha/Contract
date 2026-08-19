"""Add Phase 5 contract catalog and viewer access.

Revision ID: 20260819_0006
Revises: 20260819_0005
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0006"
down_revision: str | None = "20260819_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE contract_display_no_seq START WITH 1 INCREMENT BY 1")
    op.create_table(
        "contracts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("display_no", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("declared_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("btrim(title) <> ''", name="title_not_blank"),
        sa.CheckConstraint(
            "declared_type IS NULL OR declared_type IN "
            "('purchase', 'sales', 'nda', 'outsourcing', 'employment', 'other')",
            name="declared_type_valid",
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_contracts_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_contracts_owner_membership_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contracts"),
        sa.UniqueConstraint("organization_id", "id", name="uq_contracts_organization_id_id"),
        sa.UniqueConstraint("display_no", name="uq_contracts_display_no"),
    )
    op.create_index(
        "ix_contracts_organization_created_at_id",
        "contracts",
        ["organization_id", "created_at", "id"],
    )
    op.create_index(
        "ix_contracts_organization_status_created_at_id",
        "contracts",
        ["organization_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_contracts_organization_owner_id",
        "contracts",
        ["organization_id", "owner_id"],
    )

    op.create_table(
        "contract_access_grants",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(length=16), server_default="read", nullable=False),
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
        sa.CheckConstraint("access_level IN ('read')", name="access_level_valid"),
        sa.ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_contract_access_grants_contract_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_contract_access_grants_user_membership_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_access_grants"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_contract_access_grants_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "contract_id",
            "user_id",
            name="uq_contract_access_grants_contract_user",
        ),
    )
    op.create_index(
        "ix_contract_access_grants_organization_contract_user",
        "contract_access_grants",
        ["organization_id", "contract_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contract_access_grants_organization_contract_user",
        table_name="contract_access_grants",
    )
    op.drop_table("contract_access_grants")
    op.drop_index("ix_contracts_organization_owner_id", table_name="contracts")
    op.drop_index(
        "ix_contracts_organization_status_created_at_id", table_name="contracts"
    )
    op.drop_index("ix_contracts_organization_created_at_id", table_name="contracts")
    op.drop_table("contracts")
    op.execute("DROP SEQUENCE contract_display_no_seq")
