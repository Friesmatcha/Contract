from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.contracts.api import _read_context
from backend.app.modules.contracts.schemas import ContractType
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.organization import (
    require_organization_member,
    require_platform_admin,
)
from backend.app.modules.identity.support_access import authorize_support_access
from backend.app.modules.warnings.models import Warning
from backend.app.modules.warnings.schemas import (
    NotificationListQuery,
    NotificationPage,
    NotificationReadResponse,
    NotificationStatus,
    UnreadCountResponse,
    WarningDetailResponse,
    WarningEventRequest,
    WarningEventResponse,
    WarningListQuery,
    WarningPage,
    WarningSeverity,
    WarningStatus,
)
from backend.app.modules.warnings.service import (
    create_warning_event,
    get_warning,
    list_notifications,
    list_warnings,
    mark_notification_read,
    unread_count,
)
from backend.app.shared.tenant import TenantContext

warning_router = APIRouter(prefix="/warnings", tags=["warnings"])
notification_router = APIRouter(prefix="/notifications", tags=["notifications"])


def _warning_context(
    database: DatabaseSession,
    *,
    warning_id: UUID,
    authenticated: Authenticated,
    organization_id: UUID | None,
    support_grant_id: UUID | None,
    request_id: str,
) -> tuple[UUID, str | None, TenantContext | None]:
    had_transaction = database.in_transaction()
    warning_organization_id = database.scalar(
        select(Warning.organization_id).where(Warning.id == warning_id)
    )
    if warning_organization_id is None:
        from backend.app.shared.errors import ApplicationError

        raise ApplicationError(status_code=404, code="WARNING_NOT_FOUND", message="预警不存在。")
    if not had_transaction and database.in_transaction():
        # The warning lookup starts a read transaction; finish it before any
        # authorization path that may open the event service transaction.
        database.commit()
    if support_grant_id is not None:
        require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
        grant = authorize_support_access(
            database,
            grant_id=support_grant_id,
            platform_admin_user_id=authenticated.user.id,
            request_id=request_id,
        )
        if grant.organization_id != warning_organization_id:
            from backend.app.shared.errors import ApplicationError

            raise ApplicationError(
                status_code=404, code="WARNING_NOT_FOUND", message="预警不存在。"
            )
        return grant.organization_id, None, None
    if organization_id is not None and organization_id != warning_organization_id:
        from backend.app.shared.errors import ApplicationError

        raise ApplicationError(status_code=404, code="WARNING_NOT_FOUND", message="预警不存在。")
    _, tenant, role = require_organization_member(
        database,
        organization_id=warning_organization_id,
        user_id=authenticated.user.id,
    )
    return warning_organization_id, role, tenant


@warning_router.get(
    "",
    response_model=WarningPage,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_warnings(
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
    status_filter: Annotated[WarningStatus | None, Query(alias="status")] = None,
    severity: Annotated[WarningSeverity | None, Query()] = None,
    contract_type: Annotated[ContractType | None, Query()] = None,
    assignee_id: Annotated[UUID | None, Query()] = None,
    risk_type: Annotated[str | None, Query(max_length=128)] = None,
    triggered_from: Annotated[datetime | None, Query()] = None,
    triggered_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[Literal["triggered_at", "priority", "due_at"], Query()] = "triggered_at",
    direction: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> WarningPage:
    resolved_organization_id, role = _read_context(
        database,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=support_grant_id,
        request_id=request.state.request_id,
    )
    query = WarningListQuery.model_validate(
        {
            "status": status_filter,
            "severity": severity,
            "contract_type": contract_type,
            "assignee_id": assignee_id,
            "risk_type": risk_type,
            "triggered_from": triggered_from,
            "triggered_to": triggered_to,
            "sort": sort,
            "direction": direction,
            "limit": limit,
            "cursor": cursor,
        }
    )
    return WarningPage.model_validate(
        list_warnings(
            database,
            organization_id=resolved_organization_id,
            viewer_user_id=authenticated.user.id if role == "viewer" else None,
            query=query,
        )
    )


@warning_router.get(
    "/{warning_id}",
    response_model=WarningDetailResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_warning_detail(
    warning_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
) -> WarningDetailResponse:
    resolved_organization_id, role, _tenant = _warning_context(
        database,
        warning_id=warning_id,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=support_grant_id,
        request_id=request.state.request_id,
    )
    return WarningDetailResponse.model_validate(
        get_warning(
            database,
            organization_id=resolved_organization_id,
            warning_id=warning_id,
            viewer_user_id=authenticated.user.id if role == "viewer" else None,
        )
    )


@warning_router.post(
    "/{warning_id}/events",
    response_model=WarningEventResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_warning_event(
    warning_id: UUID,
    body: WarningEventRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
) -> WarningEventResponse:
    _resolved_organization_id, role, tenant = _warning_context(
        database,
        warning_id=warning_id,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=None,
        request_id=request.state.request_id,
    )
    if tenant is None or role is None:
        from backend.app.shared.errors import ForbiddenError

        raise ForbiddenError()
    return WarningEventResponse.model_validate(
        create_warning_event(
            database,
            actor=tenant,
            role=role,
            warning_id=warning_id,
            body=body,
            request_id=request.state.request_id,
        )
    )


@notification_router.get(
    "", response_model=NotificationPage, responses={401: {"model": ErrorResponse}}
)
def get_notifications(
    database: DatabaseSession,
    authenticated: Authenticated,
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    warning_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> NotificationPage:
    query = NotificationListQuery.model_validate(
        {"status": status_filter, "warning_id": warning_id, "limit": limit, "cursor": cursor}
    )
    return NotificationPage.model_validate(
        list_notifications(database, user_id=authenticated.user.id, query=query)
    )


@notification_router.post(
    "/{notification_id}/read",
    response_model=NotificationReadResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def post_notification_read(
    notification_id: UUID,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> NotificationReadResponse:
    return NotificationReadResponse.model_validate(
        mark_notification_read(
            database, user_id=authenticated.user.id, notification_id=notification_id
        )
    )


@notification_router.get(
    "/unread-count", response_model=UnreadCountResponse, responses={401: {"model": ErrorResponse}}
)
def get_unread_count(
    database: DatabaseSession, authenticated: Authenticated
) -> UnreadCountResponse:
    return UnreadCountResponse(unread_count=unread_count(database, user_id=authenticated.user.id))


__all__ = ["notification_router", "warning_router"]
