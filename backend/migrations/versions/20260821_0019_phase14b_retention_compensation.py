"""Add durable file cleanup journals and retention states."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0019"
down_revision: str | None = "20260821_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("storage_status_valid", "file_objects", type_="check")
    op.create_check_constraint(
        "storage_status_valid",
        "file_objects",
        "storage_status IN ('quarantine', 'stored', 'deleting', 'deleted', 'failed')",
    )
    op.create_table(
        "file_cleanup_operations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("file_object_id", sa.Uuid(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "operation_type IN ('write', 'cleanup')", name="operation_type_valid"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'file_deleted', 'finalized', 'retryable', "
            "'skipped', 'final_failed')",
            name="status_valid",
        ),
        sa.CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        sa.CheckConstraint(
            "error_code IS NULL OR btrim(error_code) <> ''",
            name="error_code_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_file_cleanup_operations_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "file_object_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_file_cleanup_operations_file_object_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_file_cleanup_operations"),
        sa.UniqueConstraint(
            "operation_type", "storage_key", name="uq_file_cleanup_operations_type_key"
        ),
    )
    op.create_index(
        "ix_file_cleanup_operations_claim",
        "file_cleanup_operations",
        ["operation_type", "status", "next_attempt_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_file_cleanup_operations_organization_created",
        "file_cleanup_operations",
        ["organization_id", "created_at", "id"],
    )
    op.execute(
        "UPDATE notifications SET next_attempt_at = created_at + interval '1 minute' "
        "WHERE delivery_status = 'failed' AND attempts = 1 AND next_attempt_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_file_cleanup_operations_organization_created",
        table_name="file_cleanup_operations",
    )
    op.drop_index("ix_file_cleanup_operations_claim", table_name="file_cleanup_operations")
    op.drop_table("file_cleanup_operations")
    op.drop_constraint("storage_status_valid", "file_objects", type_="check")
    op.create_check_constraint(
        "storage_status_valid",
        "file_objects",
        "storage_status IN ('quarantine', 'stored', 'failed')",
    )
