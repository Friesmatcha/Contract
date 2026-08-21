from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, UuidPrimaryKeyMixin


class Feedback(UuidPrimaryKeyMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_feedback_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_feedback_creator_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "subject_type IN ("
            "'classification', 'extracted_field', 'risk_finding', 'clause_comparison')",
            name="subject_type_valid",
        ),
        CheckConstraint(
            "label IN ('correct', 'incorrect', 'modified', 'ignored')", name="label_valid"
        ),
        Index("ix_feedback_organization_created", "organization_id", "created_at", "id"),
        Index(
            "ix_feedback_organization_task", "organization_id", "review_task_id", "created_at", "id"
        ),
        Index(
            "ix_feedback_organization_subject",
            "organization_id",
            "subject_type",
            "subject_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    review_task_id: Mapped[UUID] = mapped_column(nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False)
    label: Mapped[str] = mapped_column(String(16), nullable=False)
    corrected_value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=False))
    note: Mapped[str | None] = mapped_column(String(2000))
    created_by: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["Feedback"]
