from datetime import datetime
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
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import Base, TimestampMixin, UuidPrimaryKeyMixin


class FileCleanupOperation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_cleanup_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_file_cleanup_operations_organization",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "file_object_id"],
            ["file_objects.organization_id", "file_objects.id"],
            name="fk_file_cleanup_operations_file_object_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "operation_type IN ('write', 'cleanup')",
            name="operation_type_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'claimed', 'file_deleted', 'finalized', 'retryable', "
            "'skipped', 'final_failed')",
            name="status_valid",
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint(
            "error_code IS NULL OR btrim(error_code) <> ''",
            name="error_code_not_blank",
        ),
        UniqueConstraint(
            "operation_type", "storage_key", name="uq_file_cleanup_operations_type_key"
        ),
        Index(
            "ix_file_cleanup_operations_claim",
            "operation_type",
            "status",
            "next_attempt_at",
            "lease_expires_at",
        ),
        Index(
            "ix_file_cleanup_operations_organization_created",
            "organization_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    file_object_id: Mapped[UUID | None] = mapped_column()
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["FileCleanupOperation"]
