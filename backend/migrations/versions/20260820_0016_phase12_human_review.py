"""Add Phase 12 human review, revisions and feedback facts.

Revision ID: 20260820_0016
Revises: 20260820_0015
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260820_0016"
down_revision: str | None = "20260820_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_tasks", sa.Column("completed_by", sa.Uuid(), nullable=True))
    op.add_column(
        "review_tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_review_tasks_completed_by_tenant",
        "review_tasks",
        "organization_memberships",
        ["organization_id", "completed_by"],
        ["organization_id", "user_id"],
        ondelete="RESTRICT",
    )

    for table in (
        "contract_classifications",
        "extracted_fields",
        "risk_findings",
        "clause_comparisons",
    ):
        op.add_column(table, sa.Column("edited_by", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_edited_by_tenant",
            table,
            "organization_memberships",
            ["organization_id", "edited_by"],
            ["organization_id", "user_id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "result_revisions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("before_json", postgresql.JSONB(none_as_null=False), nullable=False),
        sa.Column("after_json", postgresql.JSONB(none_as_null=False), nullable=False),
        sa.Column("version_before", sa.Integer(), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject_type IN ("
            "'classification', 'extracted_field', 'risk_finding', 'clause_comparison')",
            name="subject_type_valid",
        ),
        sa.CheckConstraint(
            "version_before > 0 AND version_after = version_before + 1",
            name="versions_valid",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_result_revisions_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_result_revisions_actor_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_result_revisions"),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
    )
    op.create_index(
        "ix_result_revisions_organization_task_created",
        "result_revisions",
        ["organization_id", "review_task_id", "created_at", "id"],
    )
    op.create_index(
        "ix_result_revisions_organization_subject_created",
        "result_revisions",
        ["organization_id", "subject_type", "subject_id", "created_at", "id"],
    )

    op.create_table(
        "feedback",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("corrected_value", postgresql.JSONB(none_as_null=False), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject_type IN ("
            "'classification', 'extracted_field', 'risk_finding', 'clause_comparison')",
            name="subject_type_valid",
        ),
        sa.CheckConstraint(
            "label IN ('correct', 'incorrect', 'modified', 'ignored')",
            name="label_valid",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_feedback_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_feedback_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
    )
    op.create_index(
        "ix_feedback_organization_created", "feedback", ["organization_id", "created_at", "id"]
    )
    op.create_index(
        "ix_feedback_organization_task",
        "feedback",
        ["organization_id", "review_task_id", "created_at", "id"],
    )
    op.create_index(
        "ix_feedback_organization_subject",
        "feedback",
        ["organization_id", "subject_type", "subject_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_organization_subject", table_name="feedback")
    op.drop_index("ix_feedback_organization_task", table_name="feedback")
    op.drop_index("ix_feedback_organization_created", table_name="feedback")
    op.drop_table("feedback")

    op.drop_index("ix_result_revisions_organization_subject_created", table_name="result_revisions")
    op.drop_index("ix_result_revisions_organization_task_created", table_name="result_revisions")
    op.drop_table("result_revisions")

    for table in (
        "clause_comparisons",
        "risk_findings",
        "extracted_fields",
        "contract_classifications",
    ):
        op.drop_constraint(f"fk_{table}_edited_by_tenant", table, type_="foreignkey")
        op.drop_column(table, "edited_at")
        op.drop_column(table, "edited_by")

    op.drop_constraint("fk_review_tasks_completed_by_tenant", "review_tasks", type_="foreignkey")
    op.drop_column("review_tasks", "completed_at")
    op.drop_column("review_tasks", "completed_by")
