from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.shared.db import Base, UuidPrimaryKeyMixin
from backend.app.shared.tenant import PlatformContext, TenantContext

_SENSITIVE_KEY_PARTS = ("apikey", "authorization", "cookie", "csrf", "password", "secret", "token")


class AuditLog(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "actor_membership_id", "actor_id"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.id",
                "organization_memberships.user_id",
            ],
            name="fk_audit_logs_actor_membership_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "actor_membership_id IS NULL OR "
            "(organization_id IS NOT NULL AND actor_id IS NOT NULL)",
            name="membership_requires_actor_tenant",
        ),
        CheckConstraint("btrim(action) <> ''", name="action_not_blank"),
        CheckConstraint("btrim(resource_type) <> ''", name="resource_type_not_blank"),
        Index("ix_audit_logs_organization_created_at_id", "organization_id", "created_at", "id"),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_membership_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID | None]
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    before_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _assert_safe_summary(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = "".join(
                character for character in str(key).lower() if character.isalnum()
            )
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                raise ValueError("audit summary contains a sensitive field")
            _assert_safe_summary(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _assert_safe_summary(item)


def append_audit_log(
    session: Session,
    *,
    actor: TenantContext | PlatformContext | None,
    action: str,
    resource_type: str,
    request_id: str,
    resource_id: UUID | None = None,
    organization_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    _assert_safe_summary(before)
    _assert_safe_summary(after)

    actor_id: UUID | None = None
    actor_membership_id: UUID | None = None
    if isinstance(actor, TenantContext):
        if organization_id is not None and organization_id != actor.organization_id:
            raise ValueError("tenant actor cannot write an audit event for another organization")
        organization_id = actor.organization_id
        actor_id = actor.user_id
        actor_membership_id = actor.membership_id
    elif isinstance(actor, PlatformContext):
        actor_id = actor.user_id

    audit_log = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        actor_membership_id=actor_membership_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        before_summary_json=before,
        after_summary_json=after,
    )
    session.add(audit_log)
    return audit_log
