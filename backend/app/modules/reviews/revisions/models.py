from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, UuidPrimaryKeyMixin


class ResultRevision(UuidPrimaryKeyMixin, Base):
    __tablename__ = "result_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "review_task_id"],
            ["review_tasks.organization_id", "review_tasks.id"],
            name="fk_result_revisions_review_task_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_result_revisions_actor_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "subject_type IN ("
            "'classification', 'extracted_field', 'risk_finding', 'clause_comparison')",
            name="subject_type_valid",
        ),
        CheckConstraint(
            "version_before > 0 AND version_after = version_before + 1", name="versions_valid"
        ),
        Index(
            "ix_result_revisions_organization_task_created",
            "organization_id",
            "review_task_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_result_revisions_organization_subject_created",
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
    before_json: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=False), nullable=False)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=False), nullable=False)
    version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000))
    actor_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["ResultRevision"]
