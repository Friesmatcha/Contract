from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin

REVIEW_STAGES = (
    "parsing",
    "classification",
    "extraction",
    "risk_analysis",
    "clause_comparison",
    "report",
)
ACTIVE_REVIEW_STATUSES = ("pending", "parsing", "reviewing", "pending_review")
WORKER_REQUEUE_STATUSES = ("pending", "parsing", "reviewing")
TERMINAL_REVIEW_STATUSES = ("completed", "failed", "archived")


class ReviewTask(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_review_tasks_organization_id_id"),
        UniqueConstraint("display_no", name="uq_review_tasks_display_no"),
        ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_review_tasks_contract_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "contract_file_id"],
            ["contract_files.organization_id", "contract_files.id"],
            name="fk_review_tasks_contract_file_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_review_tasks_document_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_bundle_version_id"],
            ["risk_rule_bundle_versions.organization_id", "risk_rule_bundle_versions.id"],
            name="fk_review_tasks_rule_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "clause_template_version_id"],
            ["clause_template_versions.organization_id", "clause_template_versions.id"],
            name="fk_review_tasks_clause_version_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_review_tasks_creator_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "completed_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_review_tasks_completed_by_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ("
            "'pending', 'parsing', 'reviewing', 'pending_review', "
            "'completed', 'failed', 'archived')",
            name="status_valid",
        ),
        CheckConstraint(
            "current_stage IN ("
            "'queued', 'parsing', 'classification', 'extraction', "
            "'risk_analysis', 'clause_comparison', 'report')",
            name="current_stage_valid",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"
        ),
        Index(
            "uq_review_tasks_active_contract",
            "organization_id",
            "contract_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending', 'parsing', 'reviewing', 'pending_review')"
            ),
        ),
        Index(
            "ix_review_tasks_organization_status_created",
            "organization_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_review_tasks_organization_contract_created",
            "organization_id",
            "contract_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_file_id: Mapped[UUID] = mapped_column(nullable=False)
    document_version_id: Mapped[UUID | None] = mapped_column()
    rule_bundle_version_id: Mapped[UUID] = mapped_column(nullable=False)
    clause_template_version_id: Mapped[UUID] = mapped_column(nullable=False)
    created_by: Mapped[UUID] = mapped_column(nullable=False)
    display_no: Mapped[str] = mapped_column(String(32), nullable=False)
    business_scenario: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_bundle_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[UUID | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewStageRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_stage_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_review_stage_runs_organization_id_id"
        ),
        UniqueConstraint(
            "organization_id",
            "review_task_id",
            "stage",
            "attempt_no",
            name="uq_review_stage_runs_task_stage_attempt",
        ),
        UniqueConstraint(
            "organization_id", "review_task_id", "id", name="uq_review_stage_runs_task_id"
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_review_stage_runs_task_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "stage IN ("
            "'parsing', 'classification', 'extraction', 'risk_analysis', "
            "'clause_comparison', 'report')",
            name="stage_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'retryable')",
            name="status_valid",
        ),
        CheckConstraint("attempt_no > 0", name="attempt_no_positive"),
        CheckConstraint("compensation_attempts >= 0", name="compensation_attempts_nonnegative"),
        CheckConstraint("input_fingerprint ~ '^[0-9a-f]{64}$'", name="input_fingerprint_hex"),
        Index(
            "ix_review_stage_runs_organization_lease",
            "organization_id",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_review_stage_runs_task_stage_attempt_desc",
            "organization_id",
            "review_task_id",
            "stage",
            "attempt_no",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    error_class: Mapped[str | None] = mapped_column(String(128))
    compensation_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class ModelCall(UuidPrimaryKeyMixin, Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_model_calls_organization_id_id"),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_model_calls_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id", "stage_run_id"],
            [
                "review_stage_runs.organization_id",
                "review_stage_runs.review_task_id",
                "review_stage_runs.id",
            ],
            name="fk_model_calls_stage_run_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "capability IN ('classification', 'extraction', 'risk_analysis', 'clause_comparison')",
            name="capability_valid",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'retryable', 'failed')", name="status_valid"
        ),
        CheckConstraint("attempt_no > 0", name="attempt_no_positive"),
        CheckConstraint(
            "token_input IS NULL OR token_input >= 0", name="token_input_nonnegative"
        ),
        CheckConstraint(
            "token_output IS NULL OR token_output >= 0", name="token_output_nonnegative"
        ),
        CheckConstraint("cost IS NULL OR cost >= 0", name="cost_nonnegative"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'", name="request_fingerprint_hex"
        ),
        CheckConstraint(
            "model_fingerprint ~ '^[0-9a-f]{64}$'", name="model_fingerprint_hex"
        ),
        Index(
            "ix_model_calls_organization_created", "organization_id", "created_at", "id"
        ),
        Index(
            "ix_model_calls_task_stage_created",
            "organization_id",
            "review_task_id",
            "stage_run_id",
            "created_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_run_id: Mapped[UUID] = mapped_column(nullable=False)
    capability: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    response_schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    sanitization_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    token_input: Mapped[int | None] = mapped_column(Integer)
    token_output: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_class: Mapped[str | None] = mapped_column(String(128))
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    repair_attempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
