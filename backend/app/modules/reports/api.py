from collections.abc import Iterator
from typing import Annotated, BinaryIO, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.organization import (
    require_organization_member,
    require_platform_admin,
)
from backend.app.modules.identity.support_access import authorize_support_access
from backend.app.modules.reports.models import Report
from backend.app.modules.reports.schemas import (
    CreateReportRequest,
    ReportCreateResponse,
    ReportResponse,
)
from backend.app.modules.reports.service import create_report, get_report, get_report_download
from backend.app.shared.errors import ApplicationError, ForbiddenError, RateLimitedError

router = APIRouter(tags=["reports"])


def _writer(role: str) -> None:
    if role not in {"org_admin", "reviewer"}:
        raise ForbiddenError()


def _report_not_found() -> ApplicationError:
    return ApplicationError(status_code=404, code="REPORT_NOT_FOUND", message="报告不存在。")


def _report_organization(database: DatabaseSession, *, report_id: UUID) -> UUID:
    organization_id = database.scalar(select(Report.organization_id).where(Report.id == report_id))
    database.commit()
    if organization_id is None:
        raise _report_not_found()
    return organization_id


def _report_tenant(
    database: DatabaseSession, *, report_id: UUID, user_id: UUID
) -> tuple[UUID, str]:
    organization_id = _report_organization(database, report_id=report_id)
    try:
        _, tenant, role = require_organization_member(
            database, organization_id=organization_id, user_id=user_id
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise _report_not_found() from exc
        raise
    return tenant.organization_id, role


def _stream_file(file_handle: BinaryIO, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    try:
        while chunk := file_handle.read(chunk_size):
            yield chunk
    finally:
        file_handle.close()


@router.post(
    "/review-tasks/{review_task_id}/reports",
    response_model=ReportCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def post_report(
    review_task_id: UUID,
    body: CreateReportRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> ReportCreateResponse:
    from backend.app.modules.reviews.api import _task_tenant

    tenant, role = _task_tenant(database, task_id=review_task_id, user_id=authenticated.user.id)
    _writer(role)
    report, _ = create_report(
        database,
        actor=tenant,
        task_id=review_task_id,
        report_format=body.format,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
        renderer=request.app.state.report_renderer,
    )
    return ReportCreateResponse.model_validate(
        {
            "id": report.id,
            "review_task_id": report.review_task_id,
            "format": report.format,
            "status": report.status,
        }
    )


@router.get(
    "/reports/{report_id}",
    response_model=ReportResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_report_endpoint(
    report_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
) -> ReportResponse:
    if support_grant_id is not None:
        require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
        grant = authorize_support_access(
            database,
            grant_id=support_grant_id,
            platform_admin_user_id=authenticated.user.id,
            request_id=request.state.request_id,
        )
        organization_id = grant.organization_id
        viewer_user_id = None
    else:
        organization_id, role = _report_tenant(
            database, report_id=report_id, user_id=authenticated.user.id
        )
        viewer_user_id = authenticated.user.id if role == "viewer" else None
    return ReportResponse.model_validate(
        get_report(
            database,
            organization_id=organization_id,
            report_id=report_id,
            viewer_user_id=viewer_user_id,
        )
    )


@router.get(
    "/reports/{report_id}/download",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def get_report_download_endpoint(
    report_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    disposition: Annotated[Literal["attachment", "inline"], Query()] = "attachment",
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
) -> StreamingResponse:
    if support_grant_id is not None or authenticated.user.is_platform_admin:
        raise _report_not_found()
    organization_id, role = _report_tenant(
        database, report_id=report_id, user_id=authenticated.user.id
    )
    try:
        from backend.app.modules.identity.service import consume_rate_limit

        consume_rate_limit(
            database,
            action="report:download",
            key=f"{organization_id}:{authenticated.user.id}",
            limit=120,
        )
    except RateLimitedError as exc:
        raise ApplicationError(
            status_code=429,
            code="DOWNLOAD_RATE_LIMITED",
            message="报告下载请求过于频繁，请稍后重试。",
        ) from exc
    report, file_object = get_report_download(
        database,
        organization_id=organization_id,
        report_id=report_id,
        viewer_user_id=authenticated.user.id if role == "viewer" else None,
        file_store=request.app.state.file_store,
    )
    handle = request.app.state.file_store.open(file_object.storage_key)
    safe_name = file_object.original_name.replace("\r", "").replace("\n", "")
    encoded_name = quote(safe_name)
    return StreamingResponse(
        _stream_file(handle),
        media_type="text/html" if report.format == "html" else "application/pdf",
        headers={
            "Content-Length": str(file_object.size_bytes),
            "Content-Disposition": (
                f'{disposition}; filename="download"; '
                f'filename*=UTF-8\'\'{encoded_name}'
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


__all__ = ["router"]
