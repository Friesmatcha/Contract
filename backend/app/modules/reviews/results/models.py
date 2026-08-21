from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin, VersionMixin

RESULT_STATUSES = ("detected", "not_found", "needs_confirmation", "confirmed", "corrected")
RISK_FINDING_STATUSES = ("pending_review", "confirmed", "false_positive", "processed")
RISK_SOURCES = ("rule", "model")
CLAUSE_COMPARISON_STATUSES = ("matched", "deviated", "missing", "uncertain")
CONTRACT_CATEGORIES = ("purchase", "sales", "nda", "outsourcing", "employment", "other")
CORE_EXTRACTED_FIELD_KEYS = (
    "parties",
    "signing_date",
    "contract_amount",
    "performance_period",
    "dispute_resolution",
    "payment_terms",
    "auto_renewal",
)


class ContractClassification(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "contract_classifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_contract_classifications_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id", "review_task_id", name="uq_contract_classifications_task"
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_contract_classifications_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "edited_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_contract_classifications_edited_by_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_contract_classifications_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_contract_classifications_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_contract_classifications_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "model_value IN ('purchase', 'sales', 'nda', 'outsourcing', 'employment', 'other')",
            name="model_value_valid",
        ),
        CheckConstraint(
            "current_value IN ('purchase', 'sales', 'nda', 'outsourcing', 'employment', 'other')",
            name="current_value_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "status IN ('detected', 'not_found', 'needs_confirmation', 'confirmed', 'corrected')",
            name="status_valid",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        CheckConstraint("model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"),
        CheckConstraint("result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"),
        Index(
            "ix_contract_classifications_organization_task",
            "organization_id",
            "review_task_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_span_id: Mapped[UUID] = mapped_column(nullable=False)
    model_value: Mapped[str] = mapped_column(String(32), nullable=False)
    current_value: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    edited_by: Mapped[UUID | None] = mapped_column()
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ContractClassificationEvidence(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_classification_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_contract_classification_evidence_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id",
            "classification_id",
            "source_span_id",
            name="uq_contract_classification_evidence_span",
        ),
        ForeignKeyConstraint(
            ["organization_id", "classification_id"],
            ["contract_classifications.organization_id", "contract_classifications.id"],
            name="fk_contract_classification_evidence_classification_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_contract_classification_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_contract_classification_evidence_span_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position_no >= 0", name="position_nonnegative"),
        CheckConstraint("is_primary IN (true, false)", name="primary_boolean"),
        Index(
            "ix_contract_classification_evidence_classification_order",
            "organization_id",
            "classification_id",
            "position_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    classification_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    source_span_id: Mapped[UUID] = mapped_column(nullable=False)
    position_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")


class ExtractedField(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_extracted_fields_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "review_task_id",
            "field_key",
            name="uq_extracted_fields_task_field",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_extracted_fields_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "edited_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_extracted_fields_edited_by_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_extracted_fields_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_extracted_fields_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_extracted_fields_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "field_key IN ('parties', 'signing_date', 'contract_amount', 'performance_period', "
            "'dispute_resolution', 'payment_terms', 'auto_renewal')",
            name="field_key_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "status IN ('detected', 'not_found', 'needs_confirmation', 'confirmed', 'corrected')",
            name="status_valid",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        CheckConstraint("model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"),
        CheckConstraint("result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"),
        Index(
            "ix_extracted_fields_organization_task_status",
            "organization_id",
            "review_task_id",
            "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_span_id: Mapped[UUID | None] = mapped_column()
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_value_json: Mapped[Any] = mapped_column(JSONB(none_as_null=False), nullable=False)
    current_value_json: Mapped[Any] = mapped_column(JSONB(none_as_null=False), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    edited_by: Mapped[UUID | None] = mapped_column()
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ExtractedFieldEvidence(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extracted_field_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_extracted_field_evidence_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id",
            "extracted_field_id",
            "source_span_id",
            name="uq_extracted_field_evidence_span",
        ),
        ForeignKeyConstraint(
            ["organization_id", "extracted_field_id"],
            ["extracted_fields.organization_id", "extracted_fields.id"],
            name="fk_extracted_field_evidence_field_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_extracted_field_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_extracted_field_evidence_span_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position_no >= 0", name="position_nonnegative"),
        CheckConstraint("is_primary IN (true, false)", name="primary_boolean"),
        Index(
            "ix_extracted_field_evidence_field_order",
            "organization_id",
            "extracted_field_id",
            "position_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    extracted_field_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    source_span_id: Mapped[UUID] = mapped_column(nullable=False)
    position_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")


class RiskFinding(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "risk_findings"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_risk_findings_organization_id_id"),
        UniqueConstraint(
            "organization_id", "review_task_id", "result_fingerprint",
            name="uq_risk_findings_task_fingerprint",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_risk_findings_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "edited_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_risk_findings_edited_by_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_risk_findings_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_id"],
            ["risk_rules.organization_id", "risk_rules.id"],
            name="fk_risk_findings_rule_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "model_call_id"],
            ["model_calls.organization_id", "model_calls.id"],
            name="fk_risk_findings_model_call_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_risk_findings_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_risk_findings_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        CheckConstraint("source IN ('rule', 'model')", name="source_valid"),
        CheckConstraint(
            "status IN ('pending_review', 'confirmed', 'false_positive', 'processed')",
            name="status_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        CheckConstraint("model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"),
        CheckConstraint("result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"),
        Index(
            "ix_risk_findings_organization_task_filter",
            "organization_id", "review_task_id", "severity", "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(nullable=False)
    rule_id: Mapped[UUID | None] = mapped_column()
    model_call_id: Mapped[UUID | None] = mapped_column()
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_span_id: Mapped[UUID | None] = mapped_column()
    rule_key: Mapped[str | None] = mapped_column(String(128))
    risk_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    basis: Mapped[str] = mapped_column(String(2000), nullable=False)
    suggestion: Mapped[str] = mapped_column(String(2000), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    edited_by: Mapped[UUID | None] = mapped_column()
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class RiskFindingEvidence(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risk_finding_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_risk_finding_evidence_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id", "finding_id", "source_span_id",
            name="uq_risk_finding_evidence_span",
        ),
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["risk_findings.organization_id", "risk_findings.id"],
            name="fk_risk_finding_evidence_finding_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_risk_finding_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_risk_finding_evidence_span_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position_no >= 0", name="position_nonnegative"),
        Index(
            "ix_risk_finding_evidence_finding_order",
            "organization_id", "finding_id", "position_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    finding_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    source_span_id: Mapped[UUID] = mapped_column(nullable=False)
    position_no: Mapped[int] = mapped_column(Integer, nullable=False)


class ClauseComparison(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "clause_comparisons"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_clause_comparisons_organization_id_id"),
        UniqueConstraint(
            "organization_id", "review_task_id", "clause_key",
            name="uq_clause_comparisons_task_clause",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_clause_comparisons_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "edited_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_clause_comparisons_edited_by_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_clause_comparisons_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "standard_clause_id"],
            ["standard_clauses.organization_id", "standard_clauses.id"],
            name="fk_clause_comparisons_standard_clause_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "model_call_id"],
            ["model_calls.organization_id", "model_calls.id"],
            name="fk_clause_comparisons_model_call_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_clause_comparisons_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evidence_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_clause_comparisons_primary_evidence_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('matched', 'deviated', 'missing', 'uncertain')",
            name="status_valid",
        ),
        CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        CheckConstraint("model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"),
        CheckConstraint("result_fingerprint ~ '^[0-9a-f]{64}$'", name="result_fingerprint_hex"),
        Index(
            "ix_clause_comparisons_organization_task_status",
            "organization_id", "review_task_id", "status",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(nullable=False)
    standard_clause_id: Mapped[UUID] = mapped_column(nullable=False)
    model_call_id: Mapped[UUID | None] = mapped_column()
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    evidence_span_id: Mapped[UUID | None] = mapped_column()
    clause_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_text: Mapped[str | None] = mapped_column(String(10000))
    difference_summary: Mapped[str | None] = mapped_column(String(2000))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    suggestion: Mapped[str] = mapped_column(String(2000), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    edited_by: Mapped[UUID | None] = mapped_column()
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class ClauseComparisonEvidence(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clause_comparison_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_clause_comparison_evidence_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id", "comparison_id", "source_span_id",
            name="uq_clause_comparison_evidence_span",
        ),
        ForeignKeyConstraint(
            ["organization_id", "comparison_id"],
            ["clause_comparisons.organization_id", "clause_comparisons.id"],
            name="fk_clause_comparison_evidence_comparison_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_clause_comparison_evidence_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_span_id"],
            ["source_spans.organization_id", "source_spans.id"],
            name="fk_clause_comparison_evidence_span_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position_no >= 0", name="position_nonnegative"),
        Index(
            "ix_clause_comparison_evidence_comparison_order",
            "organization_id", "comparison_id", "position_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    comparison_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(nullable=False)
    source_span_id: Mapped[UUID] = mapped_column(nullable=False)
    position_no: Mapped[int] = mapped_column(Integer, nullable=False)


__all__ = [
    "CONTRACT_CATEGORIES",
    "CORE_EXTRACTED_FIELD_KEYS",
    "RESULT_STATUSES",
    "RISK_FINDING_STATUSES",
    "RISK_SOURCES",
    "CLAUSE_COMPARISON_STATUSES",
    "ContractClassification",
    "ContractClassificationEvidence",
    "ExtractedField",
    "ExtractedFieldEvidence",
    "RiskFinding",
    "RiskFindingEvidence",
    "ClauseComparison",
    "ClauseComparisonEvidence",
]
