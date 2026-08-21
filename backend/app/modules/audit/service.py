from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.shared.audit import AuditLog
from backend.app.shared.pagination import CursorPage, paginate_by_created_at


def list_audit_logs(
    session: Session,
    *,
    organization_id: UUID | None,
    action: str | None,
    resource_type: str | None,
    actor_id: UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    cursor: str | None,
    direction: str,
) -> CursorPage[AuditLog]:
    statement = select(AuditLog)
    if organization_id is not None:
        statement = statement.where(AuditLog.organization_id == organization_id)
    if action is not None:
        statement = statement.where(AuditLog.action == action)
    if resource_type is not None:
        statement = statement.where(AuditLog.resource_type == resource_type)
    if actor_id is not None:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if created_from is not None:
        statement = statement.where(AuditLog.created_at >= created_from)
    if created_to is not None:
        statement = statement.where(AuditLog.created_at < created_to)
    return paginate_by_created_at(
        session,
        statement,
        created_at_column=AuditLog.created_at,
        id_column=AuditLog.id,
        limit=limit,
        cursor=cursor,
        direction="asc" if direction == "asc" else "desc",
    )


def audit_page_payload(page: CursorPage[AuditLog]) -> dict[str, object]:
    return {
        "items": [
            {
                "id": row.id,
                "organization_id": row.organization_id,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "actor_id": row.actor_id,
                "request_id": row.request_id,
                "before_summary": row.before_summary_json,
                "after_summary": row.after_summary_json,
                "created_at": row.created_at,
            }
            for row in page.items
        ],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }
