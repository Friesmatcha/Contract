"""Add Phase 10 risk and clause comparison result facts.

Revision ID: 20260820_0014
Revises: 20260820_0013
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0014"
down_revision: str | None = "20260820_0013"
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


def _result_constraints(*, result_fingerprint: bool = True) -> list[sa.Constraint]:
    constraints: list[sa.Constraint] = [
        sa.CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"
        ),
        sa.CheckConstraint(
            "model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"
        ),
    ]
    if result_fingerprint:
        constraints.append(
            sa.CheckConstraint(
                "result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"
            )
        )
    return constraints


def upgrade() -> None:
    created_at, updated_at = _timestamps()
    op.create_table(
        "risk_findings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_span_id", sa.Uuid(), nullable=True),
        sa.Column("rule_key", sa.String(length=128), nullable=True),
        sa.Column("risk_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("basis", sa.String(length=2000), nullable=False),
        sa.Column("suggestion", sa.String(length=2000), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending_review", nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("model_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint("source IN ('rule', 'model')", name="source_valid"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'confirmed', 'false_positive', 'processed')",
            name="status_valid",
        ),
        *_result_constraints(),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_risk_findings_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_risk_findings_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rule_id"],
            ["risk_rules.organization_id", "risk_rules.id"],
            name="fk_risk_findings_rule_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "model_call_id"],
            ["model_calls.organization_id", "model_calls.id"],
            name="fk_risk_findings_model_call_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_risk_findings_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_risk_findings_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_risk_findings_organization_id_id"),
        sa.UniqueConstraint(
            "organization_id", "review_task_id", "result_fingerprint",
            name="uq_risk_findings_task_fingerprint",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_findings"),
    )
    op.create_index(
        "ix_risk_findings_organization_task_filter",
        "risk_findings",
        ["organization_id", "review_task_id", "severity", "status"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "risk_finding_evidence",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_span_id", sa.Uuid(), nullable=False),
        sa.Column("position_no", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint("position_no >= 0", name="position_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["risk_findings.organization_id", "risk_findings.id"],
            name="fk_risk_finding_evidence_finding_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_risk_finding_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_risk_finding_evidence_span_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_risk_finding_evidence_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "finding_id", "source_span_id",
            name="uq_risk_finding_evidence_span",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_finding_evidence"),
    )
    op.create_index(
        "ix_risk_finding_evidence_finding_order",
        "risk_finding_evidence",
        ["organization_id", "finding_id", "position_no"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "clause_comparisons",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("standard_clause_id", sa.Uuid(), nullable=False),
        sa.Column("model_call_id", sa.Uuid(), nullable=True),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_span_id", sa.Uuid(), nullable=True),
        sa.Column("clause_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("contract_text", sa.String(length=10000), nullable=True),
        sa.Column("difference_summary", sa.String(length=2000), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("suggestion", sa.String(length=2000), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("model_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint(
            "status IN ('matched', 'deviated', 'missing', 'uncertain')",
            name="status_valid",
        ),
        *_result_constraints(),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_clause_comparisons_review_task_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_clause_comparisons_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "standard_clause_id"],
            ["standard_clauses.organization_id", "standard_clauses.id"],
            name="fk_clause_comparisons_standard_clause_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "model_call_id"],
            ["model_calls.organization_id", "model_calls.id"],
            name="fk_clause_comparisons_model_call_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_clause_comparisons_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_clause_comparisons_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_clause_comparisons_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "review_task_id", "clause_key",
            name="uq_clause_comparisons_task_clause",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clause_comparisons"),
    )
    op.create_index(
        "ix_clause_comparisons_organization_task_status",
        "clause_comparisons",
        ["organization_id", "review_task_id", "status"],
    )

    created_at, updated_at = _timestamps()
    op.create_table(
        "clause_comparison_evidence",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_span_id", sa.Uuid(), nullable=False),
        sa.Column("position_no", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        created_at,
        updated_at,
        sa.CheckConstraint("position_no >= 0", name="position_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "comparison_id"],
            ["clause_comparisons.organization_id", "clause_comparisons.id"],
            name="fk_clause_comparison_evidence_comparison_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_clause_comparison_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_clause_comparison_evidence_span_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_clause_comparison_evidence_organization_id_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "comparison_id", "source_span_id",
            name="uq_clause_comparison_evidence_span",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clause_comparison_evidence"),
    )
    op.create_index(
        "ix_clause_comparison_evidence_comparison_order",
        "clause_comparison_evidence",
        ["organization_id", "comparison_id", "position_no"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clause_comparison_evidence_comparison_order",
        table_name="clause_comparison_evidence",
    )
    op.drop_table("clause_comparison_evidence")
    op.drop_index(
        "ix_clause_comparisons_organization_task_status", table_name="clause_comparisons"
    )
    op.drop_table("clause_comparisons")
    op.drop_index(
        "ix_risk_finding_evidence_finding_order", table_name="risk_finding_evidence"
    )
    op.drop_table("risk_finding_evidence")
    op.drop_index("ix_risk_findings_organization_task_filter", table_name="risk_findings")
    op.drop_table("risk_findings")
