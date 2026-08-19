from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from backend.app.shared.db import (
    Base,
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionMixin,
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_organization_name(name: str) -> str:
    return name.strip().lower()


class Organization(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint(
            "normalized_name = lower(btrim(name))", name="normalized_name_canonical"
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        CheckConstraint("retention_days >= 0", name="retention_days_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_organizations_created_at_id", "created_at", "id"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
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

    @validates("name")
    def normalize_name(self, _key: str, value: str) -> str:
        normalized = value.strip()
        self.normalized_name = normalize_organization_name(normalized)
        return normalized


class PlatformModelConfiguration(UuidPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "platform_model_configurations"
    __table_args__ = (
        UniqueConstraint("singleton_key", name="uq_platform_model_configurations_singleton"),
        CheckConstraint("singleton_key = 1", name="singleton_key_valid"),
        CheckConstraint("timeout_seconds > 0", name="timeout_seconds_positive"),
        CheckConstraint("max_retries >= 0", name="max_retries_nonnegative"),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    singleton_key: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=60, server_default="60")
    max_retries: Mapped[int] = mapped_column(nullable=False, default=3, server_default="3")
    usage_tracking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )


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
        CheckConstraint(
            "email_delivery_status IS NULL OR "
            "email_delivery_status IN ('queued', 'sent', 'failed')",
            name="email_delivery_status_valid",
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
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_delivery_status: Mapped[str | None] = mapped_column(String(32))


class SupportAccessGrant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_support_access_grants_organization_id_id",
        ),
        CheckConstraint("btrim(reason) <> ''", name="reason_not_blank"),
        CheckConstraint("status IN ('active', 'expired', 'revoked')", name="status_valid"),
        CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        Index(
            "uq_support_access_grants_active_target",
            "organization_id",
            "platform_admin_user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_support_access_grants_organization_created_at_id",
            "organization_id",
            "created_at",
            "id",
        ),
        Index("ix_support_access_grants_organization_expires_at", "organization_id", "expires_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    platform_admin_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    granted_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class AuthSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        CheckConstraint("char_length(token_hash) = 64", name="token_hash_valid"),
        CheckConstraint("char_length(csrf_hash) = 64", name="csrf_hash_valid"),
        CheckConstraint(
            "csrf_previous_hash IS NULL OR char_length(csrf_previous_hash) = 64",
            name="csrf_previous_hash_valid",
        ),
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires_at", "idle_expires_at", "absolute_expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_previous_hash: Mapped[str | None] = mapped_column(String(64))
    csrf_previous_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None]
    last_seen_at: Mapped[datetime] = mapped_column(nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class AuthOneTimeToken(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_one_time_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_one_time_tokens_token_hash"),
        CheckConstraint("purpose IN ('password_reset', 'invitation')", name="purpose_valid"),
        CheckConstraint("char_length(token_hash) = 64", name="token_hash_valid"),
        CheckConstraint(
            "(purpose = 'password_reset' AND user_id IS NOT NULL AND membership_id IS NULL) OR "
            "(purpose = 'invitation' AND user_id IS NULL AND membership_id IS NOT NULL)",
            name="subject_matches_purpose",
        ),
        Index("ix_auth_one_time_tokens_expires_at", "expires_at"),
        Index("ix_auth_one_time_tokens_membership_active", "membership_id", "used_at"),
        Index(
            "uq_auth_one_time_tokens_active_password_reset",
            "user_id",
            unique=True,
            postgresql_where=text("purpose = 'password_reset' AND used_at IS NULL"),
        ),
        Index(
            "uq_auth_one_time_tokens_active_invitation",
            "membership_id",
            unique=True,
            postgresql_where=text("purpose = 'invitation' AND used_at IS NULL"),
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    membership_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="RESTRICT")
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None]


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        CheckConstraint("attempts > 0", name="attempts_positive"),
        Index("ix_auth_rate_limits_window_started_at", "window_started_at"),
    )

    action: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(primary_key=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
