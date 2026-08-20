from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.modules.identity.models import OrganizationMembership
from backend.app.modules.warnings.models import Notification, Warning


def create_warning_notifications(
    session: Session,
    *,
    warning: Warning,
    title: str,
    body: str,
    recipients: Iterable[UUID] | None = None,
) -> list[Notification]:
    """Persist one idempotent in-app notification per active reviewer/admin."""
    recipient_ids = (
        list(recipients)
        if recipients is not None
        else [
            membership.user_id
            for membership in session.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == warning.organization_id,
                    OrganizationMembership.role.in_(("org_admin", "reviewer")),
                    OrganizationMembership.status == "active",
                    OrganizationMembership.user_id.is_not(None),
                )
            )
            if membership.user_id is not None
        ]
    )
    notifications: list[Notification] = []
    for user_id in dict.fromkeys(recipient_ids):
        existing = session.scalar(
            select(Notification).where(
                Notification.organization_id == warning.organization_id,
                Notification.user_id == user_id,
                Notification.warning_id == warning.id,
                Notification.channel == "in_app",
            )
        )
        if existing is not None:
            notifications.append(existing)
            continue
        try:
            with session.begin_nested():
                notification = Notification(
                    organization_id=warning.organization_id,
                    user_id=user_id,
                    warning_id=warning.id,
                    channel="in_app",
                    title=title,
                    body=body,
                    delivery_status="delivered",
                    attempts=1,
                )
                session.add(notification)
                session.flush()
        except Exception:
            notification = Notification(
                organization_id=warning.organization_id,
                user_id=user_id,
                warning_id=warning.id,
                channel="in_app",
                title=title,
                body=body,
                delivery_status="failed",
                attempts=1,
                error_code="IN_APP_DELIVERY_FAILED",
            )
            session.add(notification)
        notifications.append(notification)
    return notifications


__all__ = ["create_warning_notifications"]
