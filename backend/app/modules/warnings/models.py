from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin, VersionMixin

WARNING_STATUSES = ("pending_confirmation", "in_progress", "ignored", "resolved", "closed")
WARNING_PRIORITIES = ("high", "medium", "low")
WARNING_EVENT_TYPES = (
    "created",
    "confirm",
    "false_positive",
    "ignore",
    "assign",
    "note",
    "resolve",
    "close",
    "reopen",
)
NOTIFICATION_DELIVERY_STATUSES = ("queued", "delivered", "failed")


class Warning(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "warnings"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_warnings_organization_id_id"),
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_warnings_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "contract_id"],
            ["contracts.organization_id", "contracts.id"],
            name="fk_warnings_contract_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "risk_finding_id"],
            ["risk_findings.organization_id", "risk_findings.id"],
            name="fk_warnings_risk_finding_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "clause_comparison_id"],
            ["clause_comparisons.organization_id", "clause_comparisons.id"],
            name="fk_warnings_clause_comparison_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "extracted_field_id"],
            ["extracted_fields.organization_id", "extracted_fields.id"],
            name="fk_warnings_extracted_field_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "classification_id"],
            ["contract_classifications.organization_id", "contract_classifications.id"],
            name="fk_warnings_classification_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assignee_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_warnings_assignee_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "risk_finding_id IS NOT NULL OR clause_comparison_id IS NOT NULL "
            "OR extracted_field_id IS NOT NULL OR classification_id IS NOT NULL",
            name="warning_subject_required",
        ),
        CheckConstraint("severity IN ('high', 'medium', 'low')", name="severity_valid"),
        CheckConstraint("priority IN ('high', 'medium', 'low')", name="priority_valid"),
        CheckConstraint(
            "status IN ('pending_confirmation', 'in_progress', 'ignored', 'resolved', 'closed')",
            name="status_valid",
        ),
        CheckConstraint("btrim(trigger_type) <> ''", name="trigger_type_not_blank"),
        CheckConstraint("btrim(dedupe_key) <> ''", name="dedupe_key_not_blank"),
        CheckConstraint(
            "resolution IS NULL OR btrim(resolution) <> ''", name="resolution_not_blank"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "uq_warnings_active_dedupe",
            "organization_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('pending_confirmation', 'in_progress', 'resolved')"),
        ),
        Index(
            "ix_warnings_organization_status_triggered",
            "organization_id",
            "status",
            "triggered_at",
            "id",
        ),
        Index("ix_warnings_organization_assignee_due", "organization_id", "assignee_id", "due_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_id: Mapped[UUID] = mapped_column(nullable=False)
    risk_finding_id: Mapped[UUID | None] = mapped_column()
    clause_comparison_id: Mapped[UUID | None] = mapped_column()
    extracted_field_id: Mapped[UUID | None] = mapped_column()
    classification_id: Mapped[UUID | None] = mapped_column()
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_confirmation",
        server_default="pending_confirmation",
    )
    assignee_id: Mapped[UUID | None] = mapped_column()
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    revision_id: Mapped[UUID | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WarningEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "warning_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "warning_id"],
            ["warnings.organization_id", "warnings.id"],
            name="fk_warning_events_warning_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_warning_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('created', 'confirm', 'false_positive', 'ignore', 'assign', 'note', "
            "'resolve', 'close', 'reopen')",
            name="event_type_valid",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('pending_confirmation', 'in_progress', "
            "'ignored', 'resolved', 'closed')",
            name="from_status_valid",
        ),
        CheckConstraint(
            "to_status IS NULL OR to_status IN ('pending_confirmation', 'in_progress', "
            "'ignored', 'resolved', 'closed')",
            name="to_status_valid",
        ),
        CheckConstraint("note IS NULL OR btrim(note) <> ''", name="note_not_blank"),
        Index(
            "ix_warning_events_organization_warning_created",
            "organization_id",
            "warning_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    warning_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    actor_id: Mapped[UUID | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Notification(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_notifications_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "user_id",
            "warning_id",
            "channel",
            name="uq_notifications_recipient_warning_channel",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_notifications_user_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "warning_id"],
            ["warnings.organization_id", "warnings.id"],
            name="fk_notifications_warning_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint("channel IN ('in_app')", name="channel_valid"),
        CheckConstraint(
            "delivery_status IN ('queued', 'delivered', 'failed')", name="delivery_status_valid"
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint(
            "error_code IS NULL OR btrim(error_code) <> ''", name="error_code_not_blank"
        ),
        Index(
            "ix_notifications_organization_user_created",
            "organization_id",
            "user_id",
            "created_at",
            "id",
        ),
        Index("ix_notifications_organization_user_read", "organization_id", "user_id", "read_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    warning_id: Mapped[UUID] = mapped_column(nullable=False)
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="in_app", server_default="in_app"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
