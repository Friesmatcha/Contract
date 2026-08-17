"""Add Phase 1 shared persistence invariants.

Revision ID: 20260817_0001
Revises:
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column(
            "settings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("retention_days", sa.Integer(), server_default="180", nullable=False),
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
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        sa.CheckConstraint(
            "retention_days >= 0", name="retention_days_nonnegative"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name="status_valid"
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
    )
    op.create_index(
        "ix_organizations_created_at_id", "organizations", ["created_at", "id"], unique=False
    )

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column(
            "is_platform_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
        sa.CheckConstraint(
            "normalized_email = lower(btrim(email))",
            name="normalized_email_canonical",
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
    )
    op.create_index("ix_users_created_at_id", "users", ["created_at", "id"], unique=False)

    op.create_table(
        "organization_memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending_invitation",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "normalized_email = lower(btrim(email))",
            name="normalized_email_canonical",
        ),
        sa.CheckConstraint(
            "role IN ('org_admin', 'reviewer', 'viewer')",
            name="role_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending_invitation', 'active', 'disabled')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "version > 0", name="version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_memberships_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_memberships"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_memberships_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            "user_id",
            name="uq_memberships_organization_id_id_user_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "normalized_email",
            name="uq_memberships_organization_id_normalized_email",
        ),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_memberships_organization_id_user_id"
        ),
    )
    op.create_index(
        "ix_memberships_organization_created_at_id",
        "organization_memberships",
        ["organization_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("operation_key", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(response_status IS NULL AND completed_at IS NULL) OR "
            "(response_status BETWEEN 200 AND 299 AND completed_at IS NOT NULL)",
            name="completion_valid",
        ),
        sa.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="fingerprint_valid",
        ),
        sa.CheckConstraint(
            "scope ~ '^(organization|platform):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            "[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="scope_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
        sa.UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_membership_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("before_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(action) <> ''", name="action_not_blank"),
        sa.CheckConstraint(
            "actor_membership_id IS NULL OR "
            "(organization_id IS NOT NULL AND actor_id IS NOT NULL)",
            name="membership_requires_actor_tenant",
        ),
        sa.CheckConstraint(
            "btrim(resource_type) <> ''", name="resource_type_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_audit_logs_actor_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_membership_id", "actor_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.id",
                "organization_memberships.user_id",
            ],
            name="fk_audit_logs_actor_membership_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_logs_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index(
        "ix_audit_logs_organization_created_at_id",
        "audit_logs",
        ["organization_id", "created_at", "id"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION prevent_audit_logs_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs are append-only' USING ERRCODE = '55000';
        END;
        $$;

        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_logs_mutation();

        CREATE TRIGGER audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_logs_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_logs_mutation()")
    op.drop_index("ix_audit_logs_organization_created_at_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index(
        "ix_memberships_organization_created_at_id", table_name="organization_memberships"
    )
    op.drop_table("organization_memberships")
    op.drop_index("ix_users_created_at_id", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_organizations_created_at_id", table_name="organizations")
    op.drop_table("organizations")
