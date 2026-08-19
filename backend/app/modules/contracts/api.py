from collections.abc import Iterator
from typing import Annotated, BinaryIO, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.contracts.files.service import (
    authorize_file_download,
    upload_contract_file,
)
from backend.app.modules.contracts.models import FileObject
from backend.app.modules.contracts.schemas import (
    ContractAccessGrantRequest,
    ContractAccessGrantResponse,
    ContractFileUploadResponse,
    ContractPage,
    ContractResponse,
    ContractStatusResponse,
    ContractType,
    CreateContractRequest,
    UpdateContractRequest,
)
from backend.app.modules.contracts.service import (
    access_grant_payload,
    archive_contract,
    contract_payload,
    contract_status_payload,
    create_contract,
    get_contract,
    grant_contract_access,
    list_contracts,
    restore_contract,
    revoke_contract_access,
    update_contract,
)
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.models import Organization, OrganizationMembership
from backend.app.modules.identity.organization import (
    require_organization_member,
    require_platform_admin,
)
from backend.app.modules.identity.service import AuthenticatedSession
from backend.app.modules.identity.support_access import authorize_support_access
from backend.app.shared.errors import ApplicationError, ForbiddenError, RateLimitedError
from backend.app.shared.tenant import TenantContext

router = APIRouter(prefix="/contracts", tags=["contract catalog and viewer access"])
file_router = APIRouter(prefix="/files", tags=["secure contract files"])


def _current_organization(
    database: DatabaseSession,
    *,
    user_id: UUID,
    organization_id: UUID | None,
) -> tuple[Organization, TenantContext, str]:
    if organization_id is not None:
        return require_organization_member(
            database,
            organization_id=organization_id,
            user_id=user_id,
        )

    rows = database.execute(
        select(Organization, OrganizationMembership)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
            Organization.status == "active",
        )
    ).all()
    if not rows:
        raise ApplicationError(
            status_code=404,
            code="ORGANIZATION_NOT_FOUND",
            message="组织不存在。",
        )
    if len(rows) > 1:
        raise ApplicationError(
            status_code=409,
            code="ORGANIZATION_CONTEXT_REQUIRED",
            message="请先选择当前组织。",
        )
    organization, membership = rows[0]
    database.commit()
    return (
        organization,
        TenantContext(
            organization_id=organization.id,
            user_id=user_id,
            membership_id=membership.id,
        ),
        membership.role,
    )


def _require_writer(role: str) -> None:
    if role not in {"org_admin", "reviewer"}:
        raise ForbiddenError()


def _write_context(
    database: DatabaseSession,
    *,
    contract_id: UUID,
    user_id: UUID,
    require_org_admin: bool = False,
) -> TenantContext:
    from backend.app.modules.contracts.models import Contract

    organization_id = database.scalar(
        select(Contract.organization_id).where(Contract.id == contract_id)
    )
    if organization_id is None:
        raise ApplicationError(
            status_code=404,
            code="CONTRACT_NOT_FOUND",
            message="合同不存在。",
        )
    database.commit()
    try:
        _, tenant, role = require_organization_member(
            database,
            organization_id=organization_id,
            user_id=user_id,
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise ApplicationError(
                status_code=404,
                code="CONTRACT_NOT_FOUND",
                message="合同不存在。",
            ) from exc
        raise
    if require_org_admin:
        if role != "org_admin":
            raise ApplicationError(
                status_code=403,
                code="ORG_ADMIN_REQUIRED",
                message="仅组织管理员可执行此操作。",
            )
    else:
        _require_writer(role)
    return tenant


def _read_context(
    database: DatabaseSession,
    *,
    authenticated: AuthenticatedSession,
    organization_id: UUID | None,
    support_grant_id: UUID | None,
    request_id: str,
) -> tuple[UUID, str | None]:
    if support_grant_id is not None:
        require_platform_admin(
            authenticated.user.id,
            authenticated.user.is_platform_admin,
        )
        grant = authorize_support_access(
            database,
            grant_id=support_grant_id,
            platform_admin_user_id=authenticated.user.id,
            request_id=request_id,
        )
        return grant.organization_id, None
    _, tenant, role = _current_organization(
        database,
        user_id=authenticated.user.id,
        organization_id=organization_id,
    )
    return tenant.organization_id, role


@router.post(
    "",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def post_contract(
    body: CreateContractRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
) -> ContractResponse:
    _, tenant, role = _current_organization(
        database,
        user_id=authenticated.user.id,
        organization_id=organization_id,
    )
    _require_writer(role)
    contract = create_contract(
        database,
        actor=tenant,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    return ContractResponse.model_validate(contract_payload(database, contract))


@router.get(
    "",
    response_model=ContractPage,
    responses={
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_contracts(
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    support_grant_id: Annotated[
        UUID | None, Header(alias="X-Support-Access-Grant")
    ] = None,
    q: Annotated[str | None, Query(max_length=255)] = None,
    contract_status: Annotated[
        Literal["active", "archived"] | None, Query(alias="status")
    ] = None,
    declared_type: ContractType | None = None,
    owner_id: UUID | None = None,
    sort: Literal["created_at", "updated_at", "title"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> ContractPage:
    resolved_organization_id, role = _read_context(
        database,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=support_grant_id,
        request_id=request.state.request_id,
    )
    page = list_contracts(
        database,
        organization_id=resolved_organization_id,
        viewer_user_id=authenticated.user.id if role == "viewer" else None,
        q=q,
        status=contract_status,
        declared_type=declared_type,
        owner_id=owner_id,
        sort=sort,
        direction=direction,
        limit=limit,
        cursor=cursor,
    )
    return ContractPage.model_validate(page)


@router.get(
    "/{contract_id}",
    response_model=ContractResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_contract_detail(
    contract_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    support_grant_id: Annotated[
        UUID | None, Header(alias="X-Support-Access-Grant")
    ] = None,
) -> ContractResponse:
    resolved_organization_id, role = _read_context(
        database,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=support_grant_id,
        request_id=request.state.request_id,
    )
    contract = get_contract(
        database,
        organization_id=resolved_organization_id,
        contract_id=contract_id,
        viewer_user_id=authenticated.user.id if role == "viewer" else None,
    )
    return ContractResponse.model_validate(contract_payload(database, contract))


@router.patch(
    "/{contract_id}",
    response_model=ContractResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_contract(
    contract_id: UUID,
    body: UpdateContractRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ContractResponse:
    tenant = _write_context(
        database,
        contract_id=contract_id,
        user_id=authenticated.user.id,
    )
    contract = update_contract(
        database,
        actor=tenant,
        contract_id=contract_id,
        body=body,
        request_id=request.state.request_id,
    )
    return ContractResponse.model_validate(contract_payload(database, contract))


@router.post(
    "/{contract_id}/archive",
    response_model=ContractStatusResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def post_archive_contract(
    contract_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ContractStatusResponse:
    tenant = _write_context(
        database,
        contract_id=contract_id,
        user_id=authenticated.user.id,
    )
    contract = archive_contract(
        database,
        actor=tenant,
        contract_id=contract_id,
        request_id=request.state.request_id,
    )
    return ContractStatusResponse.model_validate(contract_status_payload(contract))


@router.post(
    "/{contract_id}/restore",
    response_model=ContractStatusResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def post_restore_contract(
    contract_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ContractStatusResponse:
    tenant = _write_context(
        database,
        contract_id=contract_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    contract = restore_contract(
        database,
        actor=tenant,
        contract_id=contract_id,
        request_id=request.state.request_id,
    )
    return ContractStatusResponse.model_validate(contract_status_payload(contract))


@router.put(
    "/{contract_id}/access-grants/{user_id}",
    response_model=ContractAccessGrantResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def put_contract_access_grant(
    contract_id: UUID,
    user_id: UUID,
    body: ContractAccessGrantRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ContractAccessGrantResponse:
    tenant = _write_context(
        database,
        contract_id=contract_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    grant = grant_contract_access(
        database,
        actor=tenant,
        contract_id=contract_id,
        user_id=user_id,
        body=body,
        request_id=request.state.request_id,
    )
    return ContractAccessGrantResponse.model_validate(access_grant_payload(grant))


@router.delete(
    "/{contract_id}/access-grants/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def delete_contract_access_grant(
    contract_id: UUID,
    user_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> Response:
    tenant = _write_context(
        database,
        contract_id=contract_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    revoke_contract_access(
        database,
        actor=tenant,
        contract_id=contract_id,
        user_id=user_id,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{contract_id}/files",
    response_model=ContractFileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def post_contract_file(
    contract_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    file: Annotated[UploadFile, File(...)],
    external_model_notice_acknowledged: Annotated[bool, Form(...)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
    make_current: Annotated[bool, Form()] = True,
) -> ContractFileUploadResponse:
    tenant = _write_context(
        database,
        contract_id=contract_id,
        user_id=authenticated.user.id,
    )
    result = upload_contract_file(
        database,
        actor=tenant,
        contract_id=contract_id,
        source=file.file,
        original_name=file.filename,
        media_type=file.content_type,
        make_current=make_current,
        external_model_notice_acknowledged=external_model_notice_acknowledged,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
        file_store=request.app.state.file_store,
        antivirus_scanner=request.app.state.antivirus_scanner,
    )
    return ContractFileUploadResponse.model_validate(result)


def _stream_file(file_handle: BinaryIO, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    try:
        while chunk := file_handle.read(chunk_size):
            yield chunk
    finally:
        file_handle.close()


def _download_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code="FILE_NOT_FOUND",
        message="文件不存在。",
    )


@file_router.get(
    "/{file_id}/download",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def get_contract_file_download(
    file_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    disposition: Annotated[Literal["attachment", "inline"], Query()] = "attachment",
    support_grant_id: Annotated[
        UUID | None, Header(alias="X-Support-Access-Grant")
    ] = None,
) -> StreamingResponse:
    if support_grant_id is not None:
        raise _download_not_found()
    organization_id = database.scalar(
        select(FileObject.organization_id).where(FileObject.id == file_id)
    )
    if organization_id is None:
        raise _download_not_found()
    database.commit()
    try:
        _, tenant, role = require_organization_member(
            database,
            organization_id=organization_id,
            user_id=authenticated.user.id,
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise _download_not_found() from exc
        raise
    try:
        from backend.app.modules.identity.service import consume_rate_limit

        consume_rate_limit(
            database,
            action="file:download",
            key=f"{tenant.organization_id}:{tenant.user_id}",
            limit=120,
        )
    except RateLimitedError as exc:
        raise ApplicationError(
            status_code=429,
            code="DOWNLOAD_RATE_LIMITED",
            message="文件下载请求过于频繁，请稍后重试。",
        ) from exc
    file_object = authorize_file_download(
        database,
        actor=tenant,
        file_id=file_id,
        viewer_user_id=authenticated.user.id if role == "viewer" else None,
        request_id=request.state.request_id,
        disposition=disposition,
        file_store=request.app.state.file_store,
    )
    handle = request.app.state.file_store.open(file_object.storage_key)
    encoded_name = quote(file_object.original_name.replace("\r", "").replace("\n", ""))
    content_disposition = f"{disposition}; filename=\"download\"; filename*=UTF-8''{encoded_name}"
    return StreamingResponse(
        _stream_file(handle),
        media_type=file_object.media_type,
        headers={
            "Content-Length": str(file_object.size_bytes),
            "Content-Disposition": content_disposition,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )
