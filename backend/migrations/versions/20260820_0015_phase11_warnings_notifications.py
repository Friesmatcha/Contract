"""Phase 11 warnings and in-app notifications.

Revision ID: 20260820_0015
Revises: 20260820_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260820_0015"
down_revision: str | None = "20260820_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
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
    )


def upgrade() -> None:
    created_at, updated_at = _timestamps()
    op.create_table(
        "warnings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("risk_finding_id", sa.Uuid(), nullable=True),
        sa.Column("clause_comparison_id", sa.Uuid(), nullable=True),
        sa.Column("extracted_field_id", sa.Uuid(), nullable=True),
        sa.Column("classification_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="pending_confirmation", nullable=False
        ),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("revision_id", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint(
            "risk_finding_id IS NOT NULL OR clause_comparison_id IS NOT NULL "
            "OR extracted_field_id IS NOT NULL OR classification_id IS NOT NULL",
            name="warning_subject_required",
        ),
        sa.CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        sa.CheckConstraint("priority IN ('high', 'medium', 'low')", name="priority_valid"),
        sa.CheckConstraint(
            "status IN ('pending_confirmation', 'in_progress', 'ignored', 'resolved', 'closed')",
            name="status_valid",
        ),
        sa.CheckConstraint("btrim(trigger_type) <> ''", name="trigger_type_not_blank"),
        sa.CheckConstraint("btrim(dedupe_key) <> ''", name="dedupe_key_not_blank"),
        sa.CheckConstraint(
            "resolution IS NULL OR btrim(resolution) <> ''", name="resolution_not_blank"
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_warnings_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_warnings_contract_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "risk_finding_id"],
            ["risk_findings.organization_id", "risk_findings.id"],
            name="fk_warnings_risk_finding_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "clause_comparison_id"],
            ["clause_comparisons.organization_id", "clause_comparisons.id"],
            name="fk_warnings_clause_comparison_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "extracted_field_id"],
            ["extracted_fields.organization_id", "extracted_fields.id"],
            name="fk_warnings_extracted_field_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "classification_id"],
            ["contract_classifications.organization_id", "contract_classifications.id"],
            name="fk_warnings_classification_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "assignee_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_warnings_assignee_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_warnings_organization_id_id"),
        sa.PrimaryKeyConstraint("id", name="pk_warnings"),
    )
    op.create_index(
        "uq_warnings_active_dedupe",
        "warnings",
        ["organization_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_confirmation', 'in_progress', 'resolved')"),
    )
    op.create_index(
        "ix_warnings_organization_status_triggered",
        "warnings",
        ["organization_id", "status", "triggered_at", "id"],
    )
    op.create_index(
        "ix_warnings_organization_assignee_due",
        "warnings",
        ["organization_id", "assignee_id", "due_at"],
    )

    op.create_table(
        "warning_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("warning_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'confirm', 'false_positive', 'ignore', 'assign', 'note', "
            "'resolve', 'close', 'reopen')",
            name="event_type_valid",
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN ('pending_confirmation', 'in_progress', "
            "'ignored', 'resolved', 'closed')",
            name="from_status_valid",
        ),
        sa.CheckConstraint(
            "to_status IS NULL OR to_status IN ('pending_confirmation', 'in_progress', "
            "'ignored', 'resolved', 'closed')",
            name="to_status_valid",
        ),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="note_not_blank"),
        sa.ForeignKeyConstraint(
            ["organization_id", "warning_id"],
            ["warnings.organization_id", "warnings.id"],
            name="fk_warning_events_warning_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_warning_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_warning_events"),
    )
    op.create_index(
        "ix_warning_events_organization_warning_created",
        "warning_events",
        ["organization_id", "warning_id", "created_at", "id"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "notifications",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("warning_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), server_default="in_app", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("delivery_status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint("channel IN ('in_app')", name="channel_valid"),
        sa.CheckConstraint(
            "delivery_status IN ('queued', 'delivered', 'failed')", name="delivery_status_valid"
        ),
        sa.CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        sa.CheckConstraint(
            "error_code IS NULL OR btrim(error_code) <> ''", name="error_code_not_blank"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_notifications_user_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "warning_id"],
            ["warnings.organization_id", "warnings.id"],
            name="fk_notifications_warning_tenant",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_notifications_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "warning_id",
            "channel",
            name="uq_notifications_recipient_warning_channel",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    op.create_index(
        "ix_notifications_organization_user_created",
        "notifications",
        ["organization_id", "user_id", "created_at", "id"],
    )
    op.create_index(
        "ix_notifications_organization_user_read",
        "notifications",
        ["organization_id", "user_id", "read_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_organization_user_read", table_name="notifications")
    op.drop_index("ix_notifications_organization_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_warning_events_organization_warning_created", table_name="warning_events")
    op.drop_table("warning_events")
    op.drop_index("ix_warnings_organization_assignee_due", table_name="warnings")
    op.drop_index("ix_warnings_organization_status_triggered", table_name="warnings")
    op.drop_index("uq_warnings_active_dedupe", table_name="warnings")
    op.drop_table("warnings")
