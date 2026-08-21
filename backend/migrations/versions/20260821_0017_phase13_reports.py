"""Add immutable report snapshots and report files.

Revision ID: 20260821_0017
Revises: 20260820_0016
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_0017"
down_revision: str | None = "20260820_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE report_display_no_seq START WITH 1 INCREMENT BY 1")
    op.create_table(
        "reports",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("display_no", sa.String(length=32), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="generating", nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("template_version", sa.String(length=128), nullable=False),
        sa.Column("file_object_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
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
        sa.CheckConstraint("format IN ('html', 'pdf')", name="format_valid"),
        sa.CheckConstraint(
            "status IN ('generating', 'ready', 'failed', 'expired')", name="status_valid"
        ),
        sa.CheckConstraint("btrim(display_no) <> ''", name="display_no_not_blank"),
        sa.CheckConstraint("btrim(template_version) <> ''", name="template_version_not_blank"),
        sa.CheckConstraint(
            "(status = 'generating' AND file_object_id IS NULL AND generated_at IS NULL "
            "AND expires_at IS NULL) OR "
            "(status = 'failed' AND file_object_id IS NULL AND generated_at IS NULL "
            "AND expires_at IS NULL) OR "
            "(status IN ('ready', 'expired') AND file_object_id IS NOT NULL "
            "AND generated_at IS NOT NULL AND expires_at IS NOT NULL)",
            name="lifecycle_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_reports_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "file_object_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_reports_file_object_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.UniqueConstraint("display_no", name="uq_reports_display_no"),
    )
    op.create_index(
        "uq_reports_generating_task_format",
        "reports",
        ["organization_id", "review_task_id", "format"],
        unique=True,
        postgresql_where=sa.text("status = 'generating'"),
    )
    op.create_index(
        "ix_reports_organization_task_created",
        "reports",
        ["organization_id", "review_task_id", "created_at", "id"],
    )
    op.create_index(
        "ix_reports_organization_status_created",
        "reports",
        ["organization_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_reports_organization_lease",
        "reports",
        ["organization_id", "status", "lease_expires_at"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_report_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                OR NEW.review_task_id IS DISTINCT FROM OLD.review_task_id
                OR NEW.display_no IS DISTINCT FROM OLD.display_no
                OR NEW.format IS DISTINCT FROM OLD.format
                OR NEW.snapshot_json IS DISTINCT FROM OLD.snapshot_json
                OR NEW.template_version IS DISTINCT FROM OLD.template_version
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION 'report snapshot identity is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER reports_snapshot_immutable
        BEFORE UPDATE ON reports
        FOR EACH ROW EXECUTE FUNCTION prevent_report_snapshot_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS reports_snapshot_immutable ON reports")
    op.execute("DROP FUNCTION IF EXISTS prevent_report_snapshot_mutation()")
    op.drop_index("ix_reports_organization_lease", table_name="reports")
    op.drop_index("ix_reports_organization_status_created", table_name="reports")
    op.drop_index("ix_reports_organization_task_created", table_name="reports")
    op.drop_index("uq_reports_generating_task_format", table_name="reports")
    op.drop_table("reports")
    op.execute("DROP SEQUENCE report_display_no_seq")
