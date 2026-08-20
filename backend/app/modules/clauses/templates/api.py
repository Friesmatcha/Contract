from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.clauses.templates.models import ClauseTemplate, ClauseTemplateVersion
from backend.app.modules.clauses.templates.schemas import (
    ClauseTemplateCursorPageResponse,
    ClauseTemplateDetailResponse,
    ClauseTemplateResponse,
    ClauseTemplateVersionResponse,
    ContractType,
    CreateClauseTemplateRequest,
    CreateClauseTemplateVersionRequest,
    PublishClauseTemplateVersionRequest,
    TemplateStatus,
    UpdateClauseTemplateRequest,
    UpdateClauseTemplateVersionRequest,
)
from backend.app.modules.clauses.templates.service import (
    _template_or_not_found,
    _template_payload,
    _version_payload,
    create_template,
    create_version,
    get_version,
    list_templates,
    publish_version,
    template_detail,
    update_template,
    update_version,
)
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.models import Organization, OrganizationMembership
from backend.app.modules.identity.organization import require_organization_member
from backend.app.shared.errors import ApplicationError, ForbiddenError
from backend.app.shared.tenant import TenantContext

router = APIRouter(tags=["versioned clause templates"])


def _context(
    database: DatabaseSession,
    *,
    user_id: UUID,
    organization_id: UUID | None,
    admin: bool = False,
) -> tuple[Organization, TenantContext, str]:
    if organization_id is not None:
        organization, tenant, role = require_organization_member(
            database,
            organization_id=organization_id,
            user_id=user_id,
        )
    else:
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
        tenant = TenantContext(
            organization_id=organization.id,
            user_id=user_id,
            membership_id=membership.id,
        )
        role = membership.role
        database.commit()
    if admin and role != "org_admin":
        raise ForbiddenError("ORG_ADMIN_REQUIRED", "仅组织管理员可执行此操作。")
    if not admin and role not in {"org_admin", "reviewer"}:
        raise ForbiddenError()
    return organization, tenant, role


def _resource_context(
    database: DatabaseSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    not_found_code: str,
    not_found_message: str,
    admin: bool = False,
) -> tuple[Organization, TenantContext, str]:
    try:
        organization, tenant, role = require_organization_member(
            database,
            organization_id=organization_id,
            user_id=user_id,
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise ApplicationError(
                status_code=404,
                code=not_found_code,
                message=not_found_message,
            ) from exc
        raise
    if admin and role != "org_admin":
        raise ForbiddenError("ORG_ADMIN_REQUIRED", "仅组织管理员可执行此操作。")
    if not admin and role not in {"org_admin", "reviewer"}:
        raise ForbiddenError()
    database.commit()
    return organization, tenant, role


def _template_context(
    database: DatabaseSession,
    *,
    template_id: UUID,
    user_id: UUID,
    admin: bool = False,
) -> tuple[ClauseTemplate, Organization, TenantContext, str]:
    template = database.scalar(select(ClauseTemplate).where(ClauseTemplate.id == template_id))
    if template is None:
        raise ApplicationError(
            status_code=404,
            code="TEMPLATE_NOT_FOUND",
            message="条款模板不存在。",
        )
    organization, tenant, role = _resource_context(
        database,
        user_id=user_id,
        organization_id=template.organization_id,
        not_found_code="TEMPLATE_NOT_FOUND",
        not_found_message="条款模板不存在。",
        admin=admin,
    )
    return template, organization, tenant, role


def _version_context(
    database: DatabaseSession,
    *,
    version_id: UUID,
    user_id: UUID,
    admin: bool = False,
) -> tuple[ClauseTemplateVersion, Organization, TenantContext, str]:
    version = database.scalar(
        select(ClauseTemplateVersion).where(ClauseTemplateVersion.id == version_id)
    )
    if version is None:
        raise ApplicationError(
            status_code=404,
            code="TEMPLATE_VERSION_NOT_FOUND",
            message="条款模板版本不存在。",
        )
    organization, tenant, role = _resource_context(
        database,
        user_id=user_id,
        organization_id=version.organization_id,
        not_found_code="TEMPLATE_VERSION_NOT_FOUND",
        not_found_message="条款模板版本不存在。",
        admin=admin,
    )
    return version, organization, tenant, role


@router.get(
    "/clause-templates",
    response_model=ClauseTemplateCursorPageResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_clause_templates(
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    template_contract_type: Annotated[ContractType | None, Query(alias="contract_type")] = None,
    business_scenario: Annotated[str | None, Query(max_length=128)] = None,
    template_status: Annotated[TemplateStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> ClauseTemplateCursorPageResponse:
    organization, _, role = _context(
        database,
        user_id=authenticated.user.id,
        organization_id=organization_id,
    )
    page = list_templates(
        database,
        organization_id=organization.id,
        role=role,
        contract_type=template_contract_type,
        business_scenario=business_scenario,
        status=template_status,
        q=q,
        limit=limit,
        cursor=cursor,
    )
    return ClauseTemplateCursorPageResponse(
        items=[
            ClauseTemplateResponse.model_validate(_template_payload(item))
            for item in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/clause-templates",
    response_model=ClauseTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_clause_template(
    body: CreateClauseTemplateRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
) -> ClauseTemplateResponse:
    _, tenant, _ = _context(
        database,
        user_id=authenticated.user.id,
        organization_id=organization_id,
        admin=True,
    )
    template = create_template(
        database,
        actor=tenant,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    return ClauseTemplateResponse.model_validate(_template_payload(template))


@router.get(
    "/clause-templates/{template_id}",
    response_model=ClauseTemplateDetailResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_clause_template(
    template_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
    include_clauses: Annotated[bool, Query()] = False,
) -> ClauseTemplateDetailResponse:
    template, _, _, role = _template_context(
        database,
        template_id=template_id,
        user_id=authenticated.user.id,
    )
    return ClauseTemplateDetailResponse.model_validate(
        template_detail(
            database,
            template=template,
            role=role,
            include_clauses=include_clauses,
        )
    )


@router.patch(
    "/clause-templates/{template_id}",
    response_model=ClauseTemplateResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_clause_template(
    template_id: UUID,
    body: UpdateClauseTemplateRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ClauseTemplateResponse:
    _, _, tenant, _ = _template_context(
        database,
        template_id=template_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    template = update_template(
        database,
        actor=tenant,
        template_id=template_id,
        body=body,
        request_id=request.state.request_id,
    )
    return ClauseTemplateResponse.model_validate(_template_payload(template))


@router.post(
    "/clause-templates/{template_id}/versions",
    response_model=ClauseTemplateVersionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_clause_template_version(
    template_id: UUID,
    body: CreateClauseTemplateVersionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> ClauseTemplateVersionResponse:
    _, _, tenant, _ = _template_context(
        database,
        template_id=template_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    version = create_version(
        database,
        actor=tenant,
        template_id=template_id,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    template = _template_or_not_found(
        database, organization_id=tenant.organization_id, template_id=version.template_id
    )
    return ClauseTemplateVersionResponse.model_validate(
        _version_payload(database, version, template)
    )


@router.get(
    "/clause-template-versions/{version_id}",
    response_model=ClauseTemplateVersionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_clause_template_version(
    version_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
) -> ClauseTemplateVersionResponse:
    _, organization, _, role = _version_context(
        database,
        version_id=version_id,
        user_id=authenticated.user.id,
    )
    return ClauseTemplateVersionResponse.model_validate(
        get_version(
            database,
            organization_id=organization.id,
            version_id=version_id,
            role=role,
        )
    )


@router.patch(
    "/clause-template-versions/{version_id}",
    response_model=ClauseTemplateVersionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_clause_template_version(
    version_id: UUID,
    body: UpdateClauseTemplateVersionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ClauseTemplateVersionResponse:
    _, _, tenant, _ = _version_context(
        database,
        version_id=version_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    version = update_version(
        database,
        actor=tenant,
        version_id=version_id,
        body=body,
        request_id=request.state.request_id,
    )
    template = _template_or_not_found(
        database, organization_id=tenant.organization_id, template_id=version.template_id
    )
    return ClauseTemplateVersionResponse.model_validate(
        _version_payload(database, version, template)
    )


@router.post(
    "/clause-template-versions/{version_id}/publish",
    response_model=ClauseTemplateVersionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_publish_clause_template_version(
    version_id: UUID,
    body: PublishClauseTemplateVersionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ClauseTemplateVersionResponse:
    _, _, tenant, _ = _version_context(
        database,
        version_id=version_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    return ClauseTemplateVersionResponse.model_validate(
        publish_version(
            database,
            actor=tenant,
            version_id=version_id,
            request_id=request.state.request_id,
        )
    )
