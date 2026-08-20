"""Add Phase 9A review task and async orchestration facts.

Revision ID: 20260820_0011
Revises: 20260819_0010
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260820_0011"
down_revision: str | None = "20260819_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE review_display_no_seq")
    op.create_table(
        "review_tasks",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("contract_file_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("rule_bundle_version_id", sa.Uuid(), nullable=False),
        sa.Column("clause_template_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("display_no", sa.String(length=32), nullable=False),
        sa.Column("business_scenario", sa.String(length=128), nullable=False),
        sa.Column("prompt_bundle_version", sa.String(length=128), nullable=False),
        sa.Column(
            "model_config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "input_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_stage", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
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
            "status IN ("
            "'pending', 'parsing', 'reviewing', 'pending_review', "
            "'completed', 'failed', 'archived')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "current_stage IN ("
            "'queued', 'parsing', 'classification', 'extraction', "
            "'risk_analysis', 'clause_comparison', 'report')",
            name="current_stage_valid",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        sa.CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_review_tasks_contract_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contract_file_id"],
            ["contract_files.organization_id", "contract_files.id"],
            name="fk_review_tasks_contract_file_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_review_tasks_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rule_bundle_version_id"],
            ["risk_rule_bundle_versions.organization_id", "risk_rule_bundle_versions.id"],
            name="fk_review_tasks_rule_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "clause_template_version_id"],
            ["clause_template_versions.organization_id", "clause_template_versions.id"],
            name="fk_review_tasks_clause_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_review_tasks_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_tasks"),
        sa.UniqueConstraint("organization_id", "id", name="uq_review_tasks_organization_id_id"),
        sa.UniqueConstraint("display_no", name="uq_review_tasks_display_no"),
    )
    op.create_index(
        "uq_review_tasks_active_contract",
        "review_tasks",
        ["organization_id", "contract_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'parsing', 'reviewing', 'pending_review')"
        ),
    )
    op.create_index(
        "ix_review_tasks_organization_status_created",
        "review_tasks",
        ["organization_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_review_tasks_organization_contract_created",
        "review_tasks",
        ["organization_id", "contract_id", "created_at", "id"],
    )

    op.create_table(
        "review_stage_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("compensation_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
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
            "stage IN ("
            "'parsing', 'classification', 'extraction', 'risk_analysis', "
            "'clause_comparison', 'report')",
            name="stage_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'retryable')",
            name="status_valid",
        ),
        sa.CheckConstraint("attempt_no > 0", name="attempt_no_positive"),
        sa.CheckConstraint(
            "compensation_attempts >= 0", name="compensation_attempts_nonnegative"
        ),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_review_stage_runs_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_stage_runs"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_review_stage_runs_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "review_task_id", "stage", "attempt_no", name="uq_review_stage_runs_task_stage_attempt"
        ),
    )
    op.create_index(
        "ix_review_stage_runs_organization_lease",
        "review_stage_runs",
        ["organization_id", "status", "lease_expires_at"],
    )
    op.create_index(
        "ix_review_stage_runs_task_stage_attempt_desc",
        "review_stage_runs",
        ["organization_id", "review_task_id", "stage", "attempt_no"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_stage_runs_task_stage_attempt_desc", table_name="review_stage_runs")
    op.drop_index("ix_review_stage_runs_organization_lease", table_name="review_stage_runs")
    op.drop_table("review_stage_runs")
    op.drop_index("ix_review_tasks_organization_contract_created", table_name="review_tasks")
    op.drop_index("ix_review_tasks_organization_status_created", table_name="review_tasks")
    op.drop_index("uq_review_tasks_active_contract", table_name="review_tasks")
    op.drop_table("review_tasks")
    op.execute("DROP SEQUENCE review_display_no_seq")
