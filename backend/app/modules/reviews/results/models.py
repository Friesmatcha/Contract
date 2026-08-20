from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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


__all__ = [
    "CONTRACT_CATEGORIES",
    "CORE_EXTRACTED_FIELD_KEYS",
    "RESULT_STATUSES",
    "ContractClassification",
    "ContractClassificationEvidence",
    "ExtractedField",
    "ExtractedFieldEvidence",
]
