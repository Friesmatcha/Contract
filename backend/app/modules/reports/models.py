from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin

REPORT_FORMATS = ("html", "pdf")
REPORT_STATUSES = ("generating", "ready", "failed", "expired")


class Report(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_reports_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "file_object_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_reports_file_object_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("format IN ('html', 'pdf')", name="format_valid"),
        CheckConstraint(
            "status IN ('generating', 'ready', 'failed', 'expired')", name="status_valid"
        ),
        CheckConstraint("btrim(display_no) <> ''", name="display_no_not_blank"),
        CheckConstraint("btrim(template_version) <> ''", name="template_version_not_blank"),
        CheckConstraint(
            "(status = 'generating' AND file_object_id IS NULL AND generated_at IS NULL "
            "AND expires_at IS NULL) OR "
            "(status = 'failed' AND file_object_id IS NULL AND generated_at IS NULL "
            "AND expires_at IS NULL) OR "
            "(status IN ('ready', 'expired') AND file_object_id IS NOT NULL "
            "AND generated_at IS NOT NULL AND expires_at IS NOT NULL)",
            name="lifecycle_consistent",
        ),
        Index(
            "uq_reports_generating_task_format",
            "organization_id",
            "review_task_id",
            "format",
            unique=True,
            postgresql_where=text("status = 'generating'"),
        ),
        Index(
            "ix_reports_organization_task_created",
            "organization_id",
            "review_task_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_reports_organization_status_created",
            "organization_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_reports_organization_lease",
            "organization_id",
            "status",
            "lease_expires_at",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    display_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generating", server_default="generating"
    )
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    template_version: Mapped[str] = mapped_column(String(128), nullable=False)
    file_object_id: Mapped[UUID | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["REPORT_FORMATS", "REPORT_STATUSES", "Report"]
