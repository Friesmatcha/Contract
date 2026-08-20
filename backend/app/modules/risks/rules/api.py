from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.models import Organization, OrganizationMembership
from backend.app.modules.identity.organization import require_organization_member
from backend.app.modules.risks.rules.models import RiskRuleBundle, RiskRuleBundleVersion
from backend.app.modules.risks.rules.schemas import (
    CreateRiskRuleBundleRequest,
    CreateRiskRuleVersionRequest,
    CursorPageResponse,
    PublishRiskRuleVersionRequest,
    RiskRuleBundleDetailResponse,
    RiskRuleBundleResponse,
    RiskRuleVersionResponse,
    UpdateRiskRuleBundleRequest,
    UpdateRiskRuleVersionRequest,
)
from backend.app.modules.risks.rules.service import (
    _bundle_or_not_found,
    _bundle_payload,
    _version_payload,
    bundle_detail,
    create_bundle,
    create_version,
    get_version,
    list_bundles,
    publish_version,
    update_bundle,
    update_version,
)
from backend.app.shared.errors import ApplicationError, ForbiddenError
from backend.app.shared.tenant import TenantContext

router = APIRouter(tags=["versioned risk rules"])


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


def _bundle_context(
    database: DatabaseSession,
    *,
    bundle_id: UUID,
    user_id: UUID,
    admin: bool = False,
) -> tuple[RiskRuleBundle, Organization, TenantContext, str]:
    bundle = database.scalar(select(RiskRuleBundle).where(RiskRuleBundle.id == bundle_id))
    if bundle is None:
        raise ApplicationError(
            status_code=404,
            code="RULE_BUNDLE_NOT_FOUND",
            message="风险规则集不存在。",
        )
    organization, tenant, role = _resource_context(
        database,
        user_id=user_id,
        organization_id=bundle.organization_id,
        not_found_code="RULE_BUNDLE_NOT_FOUND",
        not_found_message="风险规则集不存在。",
        admin=admin,
    )
    return bundle, organization, tenant, role


def _version_context(
    database: DatabaseSession,
    *,
    version_id: UUID,
    user_id: UUID,
    admin: bool = False,
) -> tuple[RiskRuleBundleVersion, Organization, TenantContext, str]:
    version = database.scalar(
        select(RiskRuleBundleVersion).where(RiskRuleBundleVersion.id == version_id)
    )
    if version is None:
        raise ApplicationError(
            status_code=404,
            code="RULE_VERSION_NOT_FOUND",
            message="风险规则版本不存在。",
        )
    organization, tenant, role = _resource_context(
        database,
        user_id=user_id,
        organization_id=version.organization_id,
        not_found_code="RULE_VERSION_NOT_FOUND",
        not_found_message="风险规则版本不存在。",
        admin=admin,
    )
    return version, organization, tenant, role


@router.get(
    "/risk-rule-bundles",
    response_model=CursorPageResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_risk_rule_bundles(
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    bundle_status: Annotated[Literal["active", "disabled"] | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> CursorPageResponse:
    organization, _, role = _context(
        database,
        user_id=authenticated.user.id,
        organization_id=organization_id,
    )
    page = list_bundles(
        database,
        organization_id=organization.id,
        role=role,
        status=bundle_status,
        q=q,
        limit=limit,
        cursor=cursor,
    )
    return CursorPageResponse(
        items=[RiskRuleBundleResponse.model_validate(_bundle_payload(item)) for item in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/risk-rule-bundles",
    response_model=RiskRuleBundleResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_risk_rule_bundle(
    body: CreateRiskRuleBundleRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
) -> RiskRuleBundleResponse:
    _, tenant, _ = _context(
        database, user_id=authenticated.user.id, organization_id=organization_id, admin=True
    )
    bundle = create_bundle(
        database,
        actor=tenant,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    return RiskRuleBundleResponse.model_validate(_bundle_payload(bundle))


@router.get(
    "/risk-rule-bundles/{bundle_id}",
    response_model=RiskRuleBundleDetailResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_risk_rule_bundle(
    bundle_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
    include_rules: Annotated[bool, Query()] = False,
) -> RiskRuleBundleDetailResponse:
    bundle, _, _, role = _bundle_context(
        database,
        bundle_id=bundle_id,
        user_id=authenticated.user.id,
    )
    return RiskRuleBundleDetailResponse.model_validate(
        bundle_detail(
            database,
            bundle=bundle,
            role=role,
            include_rules=include_rules,
        )
    )


@router.patch(
    "/risk-rule-bundles/{bundle_id}",
    response_model=RiskRuleBundleResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_risk_rule_bundle(
    bundle_id: UUID,
    body: UpdateRiskRuleBundleRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RiskRuleBundleResponse:
    _, _, tenant, _ = _bundle_context(
        database,
        bundle_id=bundle_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    bundle = update_bundle(
        database, actor=tenant, bundle_id=bundle_id, body=body, request_id=request.state.request_id
    )
    return RiskRuleBundleResponse.model_validate(_bundle_payload(bundle))


@router.post(
    "/risk-rule-bundles/{bundle_id}/versions",
    response_model=RiskRuleVersionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_risk_rule_version(
    bundle_id: UUID,
    body: CreateRiskRuleVersionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> RiskRuleVersionResponse:
    _, _, tenant, _ = _bundle_context(
        database,
        bundle_id=bundle_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    version = create_version(
        database,
        actor=tenant,
        bundle_id=bundle_id,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    bundle = _bundle_or_not_found(
        database, organization_id=tenant.organization_id, bundle_id=version.bundle_id
    )
    return RiskRuleVersionResponse.model_validate(_version_payload(database, version, bundle))


@router.get(
    "/risk-rule-bundle-versions/{version_id}",
    response_model=RiskRuleVersionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_risk_rule_version(
    version_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
) -> RiskRuleVersionResponse:
    _, organization, _, role = _version_context(
        database,
        version_id=version_id,
        user_id=authenticated.user.id,
    )
    return RiskRuleVersionResponse.model_validate(
        get_version(
            database,
            organization_id=organization.id,
            version_id=version_id,
            role=role,
        )
    )


@router.patch(
    "/risk-rule-bundle-versions/{version_id}",
    response_model=RiskRuleVersionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_risk_rule_version(
    version_id: UUID,
    body: UpdateRiskRuleVersionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RiskRuleVersionResponse:
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
    bundle = _bundle_or_not_found(
        database, organization_id=tenant.organization_id, bundle_id=version.bundle_id
    )
    return RiskRuleVersionResponse.model_validate(_version_payload(database, version, bundle))


@router.post(
    "/risk-rule-bundle-versions/{version_id}/publish",
    response_model=RiskRuleVersionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_publish_risk_rule_version(
    version_id: UUID,
    body: PublishRiskRuleVersionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RiskRuleVersionResponse:
    _, _, tenant, _ = _version_context(
        database,
        version_id=version_id,
        user_id=authenticated.user.id,
        admin=True,
    )
    return RiskRuleVersionResponse.model_validate(
        publish_version(
            database, actor=tenant, version_id=version_id, request_id=request.state.request_id
        )
    )
