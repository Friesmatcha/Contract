from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.db import (
    Base,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionMixin,
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class Organization(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        CheckConstraint("retention_days >= 0", name="retention_days_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_organizations_created_at_id", "created_at", "id"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    retention_days: Mapped[int] = mapped_column(nullable=False, default=180, server_default="180")


class User(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
        CheckConstraint(
            "normalized_email = lower(btrim(email))",
            name="normalized_email_canonical",
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_users_created_at_id", "created_at", "id"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class OrganizationMembership(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_memberships_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "id",
            "user_id",
            name="uq_memberships_organization_id_id_user_id",
        ),
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_memberships_organization_id_user_id",
        ),
        UniqueConstraint(
            "organization_id",
            "normalized_email",
            name="uq_memberships_organization_id_normalized_email",
        ),
        CheckConstraint(
            "normalized_email = lower(btrim(email))",
            name="normalized_email_canonical",
        ),
        CheckConstraint(
            "role IN ('org_admin', 'reviewer', 'viewer')",
            name="role_valid",
        ),
        CheckConstraint(
            "status IN ('pending_invitation', 'active', 'disabled')",
            name="status_valid",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_memberships_organization_created_at_id", "organization_id", "created_at", "id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_invitation",
        server_default="pending_invitation",
    )
