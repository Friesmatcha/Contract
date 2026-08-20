"""Add Phase 9C classification and extraction result facts.

Revision ID: 20260820_0013
Revises: 20260820_0012
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260820_0013"
down_revision: str | None = "20260820_0012"
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
        "contract_classifications",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_span_id", sa.Uuid(), nullable=False),
        sa.Column("model_value", sa.String(length=32), nullable=False),
        sa.Column("current_value", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("model_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint(
            "model_value IN ('purchase', 'sales', 'nda', 'outsourcing', 'employment', 'other')",
            name="model_value_valid",
        ),
        sa.CheckConstraint(
            "current_value IN ('purchase', 'sales', 'nda', 'outsourcing', 'employment', 'other')",
            name="current_value_valid",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint(
            "status IN ('detected', 'not_found', 'needs_confirmation', 'confirmed', 'corrected')",
            name="status_valid",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        sa.CheckConstraint("model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"),
        sa.CheckConstraint("result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_contract_classifications_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_contract_classifications_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_contract_classifications_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_contract_classifications_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_contract_classifications_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "review_task_id", name="uq_contract_classifications_task"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_classifications"),
    )
    op.create_index(
        "ix_contract_classifications_organization_task",
        "contract_classifications",
        ["organization_id", "review_task_id"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "contract_classification_evidence",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("classification_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_span_id", sa.Uuid(), nullable=False),
        sa.Column("position_no", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint("position_no >= 0", name="position_nonnegative"),
        sa.CheckConstraint("is_primary IN (true, false)", name="primary_boolean"),
        sa.ForeignKeyConstraint(
            ["organization_id", "classification_id"],
            ["contract_classifications.organization_id", "contract_classifications.id"],
            name="fk_contract_classification_evidence_classification_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_contract_classification_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_contract_classification_evidence_span_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_contract_classification_evidence_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "classification_id",
            "source_span_id",
            name="uq_contract_classification_evidence_span",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_classification_evidence"),
    )
    op.create_index(
        "ix_contract_classification_evidence_classification_order",
        "contract_classification_evidence",
        ["organization_id", "classification_id", "position_no"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "extracted_fields",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_span_id", sa.Uuid(), nullable=True),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column(
            "model_value_json",
            postgresql.JSONB(none_as_null=False),
            nullable=False,
        ),
        sa.Column(
            "current_value_json",
            postgresql.JSONB(none_as_null=False),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("model_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint(
            "field_key IN ('parties', 'signing_date', 'contract_amount', 'performance_period', "
            "'dispute_resolution', 'payment_terms', 'auto_renewal')",
            name="field_key_valid",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint(
            "status IN ('detected', 'not_found', 'needs_confirmation', 'confirmed', 'corrected')",
            name="status_valid",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        sa.CheckConstraint("model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"),
        sa.CheckConstraint("result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_extracted_fields_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_extracted_fields_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_extracted_fields_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_extracted_fields_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_extracted_fields_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id", "review_task_id", "field_key", name="uq_extracted_fields_task_field"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extracted_fields"),
    )
    op.create_index(
        "ix_extracted_fields_organization_task_status",
        "extracted_fields",
        ["organization_id", "review_task_id", "status"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "extracted_field_evidence",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("extracted_field_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_span_id", sa.Uuid(), nullable=False),
        sa.Column("position_no", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint("position_no >= 0", name="position_nonnegative"),
        sa.CheckConstraint("is_primary IN (true, false)", name="primary_boolean"),
        sa.ForeignKeyConstraint(
            ["organization_id", "extracted_field_id"],
            ["extracted_fields.organization_id", "extracted_fields.id"],
            name="fk_extracted_field_evidence_field_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_extracted_field_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_extracted_field_evidence_span_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_extracted_field_evidence_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "extracted_field_id",
            "source_span_id",
            name="uq_extracted_field_evidence_span",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extracted_field_evidence"),
    )
    op.create_index(
        "ix_extracted_field_evidence_field_order",
        "extracted_field_evidence",
        ["organization_id", "extracted_field_id", "position_no"],
    )


def downgrade() -> None:
    op.drop_index("ix_extracted_field_evidence_field_order", table_name="extracted_field_evidence")
    op.drop_table("extracted_field_evidence")
    op.drop_index("ix_extracted_fields_organization_task_status", table_name="extracted_fields")
    op.drop_table("extracted_fields")
    op.drop_index(
        "ix_contract_classification_evidence_classification_order",
        table_name="contract_classification_evidence",
    )
    op.drop_table("contract_classification_evidence")
    op.drop_index(
        "ix_contract_classifications_organization_task", table_name="contract_classifications"
    )
    op.drop_table("contract_classifications")
