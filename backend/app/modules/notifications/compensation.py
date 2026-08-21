from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.integrations.notifications.in_app import (
    NOTIFICATION_MAX_ATTEMPTS,
    NOTIFICATION_RETRY_DELAYS_SECONDS,
)
from backend.app.modules.warnings.models import Notification
from backend.app.observability.metrics import observe_warning_event
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork

NotificationDelivery = Callable[[Notification], None]


def _now() -> datetime:
    return datetime.now(UTC)


def _deliver_in_app(notification: Notification) -> None:
    if notification.channel != "in_app":
        raise RuntimeError("unsupported notification channel")


def _retry_delay(attempts: int) -> int:
    index = min(attempts - 1, len(NOTIFICATION_RETRY_DELAYS_SECONDS) - 1)
    return NOTIFICATION_RETRY_DELAYS_SECONDS[index]


def _audit(
    session: Session,
    *,
    notification: Notification,
    action: str,
    error_code: str | None,
) -> None:
    append_audit_log(
        session,
        actor=None,
        organization_id=notification.organization_id,
        action=action,
        resource_type="notification",
        resource_id=notification.id,
        request_id="notification-compensation",
        after={
            "warning_id": str(notification.warning_id),
            "delivery_status": notification.delivery_status,
            "attempts": notification.attempts,
            "error_code": error_code,
        },
    )


def retry_failed_notifications(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
    deliver: NotificationDelivery | None = None,
) -> list[UUID]:
    """Retry persisted failures without changing the Warning business fact."""
    now = now or _now()
    deliver = deliver or _deliver_in_app
    processed: list[UUID] = []
    with UnitOfWork(session) as unit_of_work:
        notifications = list(
            session.scalars(
                select(Notification)
                .where(
                    Notification.delivery_status == "failed",
                    Notification.attempts < NOTIFICATION_MAX_ATTEMPTS,
                    or_(
                        Notification.next_attempt_at.is_(None),
                        Notification.next_attempt_at <= now,
                    ),
                )
                .order_by(Notification.next_attempt_at, Notification.created_at, Notification.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for notification in notifications:
            notification.attempts += 1
            try:
                deliver(notification)
            except Exception:
                notification.delivery_status = "failed"
                notification.error_code = "IN_APP_DELIVERY_FAILED"
                if notification.attempts >= NOTIFICATION_MAX_ATTEMPTS:
                    notification.next_attempt_at = None
                    action = "notification.delivery_final_failed"
                else:
                    notification.next_attempt_at = now + timedelta(
                        seconds=_retry_delay(notification.attempts)
                    )
                    action = "notification.delivery_retryable"
                _audit(
                    session,
                    notification=notification,
                    action=action,
                    error_code=notification.error_code,
                )
            else:
                notification.delivery_status = "delivered"
                notification.next_attempt_at = None
                notification.error_code = None
                _audit(
                    session,
                    notification=notification,
                    action="notification.delivery_recovered",
                    error_code=None,
                )
            processed.append(notification.id)
            observe_warning_event("notification_compensation")
        unit_of_work.commit()
    return processed


__all__ = ["NotificationDelivery", "retry_failed_notifications"]
