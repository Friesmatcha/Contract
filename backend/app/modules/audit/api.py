from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.audit.schemas import AuditLogPage
from backend.app.modules.audit.service import audit_page_payload, list_audit_logs
from backend.app.modules.contracts.api import _read_context
from backend.app.modules.identity.api import Authenticated
from backend.app.modules.identity.organization import require_platform_admin
from backend.app.shared.errors import ApplicationError, ForbiddenError

router = APIRouter(tags=["audit"])
_ORGANIZATION_FILTERS = {
    "action",
    "resource_type",
    "actor_id",
    "created_from",
    "created_to",
    "sort",
    "direction",
    "limit",
    "cursor",
}
_PLATFORM_FILTERS = _ORGANIZATION_FILTERS | {"organization_id"}


def _reject_unknown_query(request: Request, allowed: set[str]) -> None:
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise ApplicationError(
            status_code=422,
            code="INVALID_FILTER",
            message="筛选字段无效。",
            details={"field": unknown[0]},
        )


def _validate_dates(created_from: datetime | None, created_to: datetime | None) -> None:
    if created_from is not None and created_to is not None and created_from >= created_to:
        raise ApplicationError(
            status_code=422,
            code="INVALID_FILTER",
            message="开始时间必须早于结束时间。",
            details={"field": "created_from"},
        )


def _page(
    database: DatabaseSession,
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
) -> AuditLogPage:
    return AuditLogPage.model_validate(
        audit_page_payload(
            list_audit_logs(
                database,
                organization_id=organization_id,
                action=action,
                resource_type=resource_type,
                actor_id=actor_id,
                created_from=created_from,
                created_to=created_to,
                limit=limit,
                cursor=cursor,
                direction=direction,
            )
        )
    )


@router.get(
    "/audit-logs",
    response_model=AuditLogPage,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_organization_audit_logs(
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    resource_type: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    actor_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Literal["created_at"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> AuditLogPage:
    _reject_unknown_query(request, _ORGANIZATION_FILTERS)
    _validate_dates(created_from, created_to)
    resolved_organization_id, role = _read_context(
        database,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=None,
        request_id=request.state.request_id,
    )
    if role != "org_admin":
        raise ForbiddenError("ORG_ADMIN_REQUIRED", "仅组织管理员可查看审计日志。")
    return _page(
        database,
        organization_id=resolved_organization_id,
        action=action,
        resource_type=resource_type,
        actor_id=actor_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        cursor=cursor,
        direction=direction,
    )


@router.get(
    "/platform/audit-logs",
    response_model=AuditLogPage,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_platform_audit_logs(
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: UUID | None = None,
    action: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    resource_type: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    actor_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Literal["created_at"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> AuditLogPage:
    _reject_unknown_query(request, _PLATFORM_FILTERS)
    _validate_dates(created_from, created_to)
    require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    return _page(
        database,
        organization_id=organization_id,
        action=action,
        resource_type=resource_type,
        actor_id=actor_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        cursor=cursor,
        direction=direction,
    )


__all__ = ["router"]
