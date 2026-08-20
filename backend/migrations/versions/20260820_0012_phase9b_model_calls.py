"""Add Phase 9B model gateway call telemetry facts.

Revision ID: 20260820_0012
Revises: 20260820_0011
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0012"
down_revision: str | None = "20260820_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_review_stage_runs_task_id",
        "review_stage_runs",
        ["organization_id", "review_task_id", "id"],
    )
    op.create_table(
        "model_calls",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("model_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("response_schema_version", sa.String(length=128), nullable=False),
        sa.Column("sanitization_policy_version", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "repair_attempt", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
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
        sa.CheckConstraint(
            "capability IN ('classification', 'extraction', 'risk_analysis', 'clause_comparison')",
            name="capability_valid",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'retryable', 'failed')", name="status_valid"
        ),
        sa.CheckConstraint("attempt_no > 0", name="attempt_no_positive"),
        sa.CheckConstraint(
            "token_input IS NULL OR token_input >= 0", name="token_input_nonnegative"
        ),
        sa.CheckConstraint(
            "token_output IS NULL OR token_output >= 0", name="token_output_nonnegative"
        ),
        sa.CheckConstraint("cost IS NULL OR cost >= 0", name="cost_nonnegative"),
        sa.CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'", name="request_fingerprint_hex"
        ),
        sa.CheckConstraint(
            "model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_model_calls_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_model_calls_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_calls"),
        sa.UniqueConstraint("organization_id", "id", name="uq_model_calls_organization_id_id"),
    )
    op.create_index(
        "ix_model_calls_organization_created",
        "model_calls",
        ["organization_id", "created_at", "id"],
    )
    op.create_index(
        "ix_model_calls_task_stage_created",
        "model_calls",
        ["organization_id", "review_task_id", "stage_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_calls_task_stage_created", table_name="model_calls")
    op.drop_index("ix_model_calls_organization_created", table_name="model_calls")
    op.drop_table("model_calls")
    op.drop_constraint(
        "uq_review_stage_runs_task_id", "review_stage_runs", type_="unique"
    )
