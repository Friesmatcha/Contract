"""Add Phase 6 secure file lifecycle tables.

Revision ID: 20260819_0007
Revises: 20260819_0006
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0007"
down_revision: str | None = "20260819_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_objects",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("scan_status", sa.String(length=32), nullable=False),
        sa.Column("storage_status", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'failed')",
            name="scan_status_valid",
        ),
        sa.CheckConstraint(
            "storage_status IN ('quarantine', 'stored', 'failed')",
            name="storage_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_file_objects_organization",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_file_objects"),
        sa.UniqueConstraint("organization_id", "id", name="uq_file_objects_organization_id_id"),
        sa.UniqueConstraint("storage_key", name="uq_file_objects_storage_key"),
    )
    op.create_index(
        "ix_file_objects_organization_sha256",
        "file_objects",
        ["organization_id", "sha256"],
    )

    op.create_table(
        "contract_files",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("file_object_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "external_model_notice_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("external_model_notice_acknowledged_by", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("version_no > 0", name="version_no_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_contract_files_contract_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "file_object_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_contract_files_file_object_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "external_model_notice_acknowledged_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_contract_files_notice_actor_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_files"),
        sa.UniqueConstraint("organization_id", "id", name="uq_contract_files_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id",
            "contract_id",
            "version_no",
            name="uq_contract_files_contract_version",
        ),
    )
    op.create_index(
        "uq_contract_files_current",
        "contract_files",
        ["organization_id", "contract_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_contract_files_organization_contract_version",
        "contract_files",
        ["organization_id", "contract_id", "version_no"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contract_files_organization_contract_version",
        table_name="contract_files",
    )
    op.drop_index("uq_contract_files_current", table_name="contract_files")
    op.drop_table("contract_files")
    op.drop_index("ix_file_objects_organization_sha256", table_name="file_objects")
    op.drop_table("file_objects")
