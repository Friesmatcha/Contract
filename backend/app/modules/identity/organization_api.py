from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status

from backend.app.config import Settings
from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.organization import (
    _organization_or_not_found,
    create_organization,
    cursor_page_payload,
    get_model_configuration,
    list_platform_organizations,
    model_configuration_payload,
    organization_payload,
    organization_profile,
    organization_settings,
    require_organization_member,
    require_platform_admin,
    update_model_configuration,
    update_organization,
    update_organization_settings,
)
from backend.app.modules.identity.schemas import (
    CreateOrganizationRequest,
    ModelConfigurationResponse,
    OrganizationProfileResponse,
    OrganizationResponse,
    OrganizationSettingsResponse,
    PlatformOrganizationPage,
    UpdateModelConfigurationRequest,
    UpdateOrganizationRequest,
    UpdateOrganizationSettingsRequest,
)
from backend.app.shared.errors import ApplicationError

router = APIRouter(tags=["organization and platform configuration"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


@router.get(
    "/platform/organizations",
    response_model=PlatformOrganizationPage,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def get_platform_organizations(
    database: DatabaseSession,
    authenticated: Authenticated,
    q: Annotated[str | None, Query(max_length=255)] = None,
    organization_status: Annotated[
        Literal["active", "disabled"] | None, Query(alias="status")
    ] = None,
    sort: Literal["created_at", "name"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> PlatformOrganizationPage:
    require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    page = list_platform_organizations(
        database,
        q=q,
        status=organization_status,
        sort=sort,
        direction=direction,
        limit=limit,
        cursor=cursor,
    )
    return PlatformOrganizationPage.model_validate(cursor_page_payload(page))


@router.post(
    "/platform/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_platform_organization(
    body: CreateOrganizationRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> OrganizationResponse:
    actor = require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    organization = create_organization(
        database,
        actor=actor,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    return OrganizationResponse.model_validate(organization_payload(organization))


@router.get(
    "/platform/organizations/{organization_id}",
    response_model=OrganizationResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_platform_organization(
    organization_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
) -> OrganizationResponse:
    require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    organization = _organization_or_not_found(database, organization_id)
    return OrganizationResponse.model_validate(organization_payload(organization))


@router.patch(
    "/platform/organizations/{organization_id}",
    response_model=OrganizationResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_platform_organization(
    organization_id: UUID,
    body: UpdateOrganizationRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> OrganizationResponse:
    actor = require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    organization = update_organization(
        database,
        actor=actor,
        organization_id=organization_id,
        body=body,
        request_id=request.state.request_id,
    )
    return OrganizationResponse.model_validate(organization_payload(organization))


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationProfileResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_organization_profile(
    organization_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
) -> OrganizationProfileResponse:
    organization, _tenant, role = require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
    )
    return OrganizationProfileResponse.model_validate(organization_profile(organization, role=role))


@router.get(
    "/organizations/{organization_id}/settings",
    response_model=OrganizationSettingsResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_organization_settings(
    organization_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
) -> OrganizationSettingsResponse:
    organization, _tenant, role = require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
    )
    if role != "org_admin":
        raise ApplicationError(
            status_code=403,
            code="ORG_ADMIN_REQUIRED",
            message="仅组织管理员可执行此操作。",
        )
    return OrganizationSettingsResponse.model_validate(
        {**organization_settings(organization), "version": organization.version}
    )


@router.patch(
    "/organizations/{organization_id}/settings",
    response_model=OrganizationSettingsResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_organization_settings(
    organization_id: UUID,
    body: UpdateOrganizationSettingsRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> OrganizationSettingsResponse:
    organization, tenant, role = require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    if role != "org_admin":
        raise ApplicationError(
            status_code=403,
            code="ORG_ADMIN_REQUIRED",
            message="仅组织管理员可执行此操作。",
        )
    payload = update_organization_settings(
        database,
        actor=tenant,
        organization=organization,
        body=body,
        request_id=request.state.request_id,
    )
    return OrganizationSettingsResponse.model_validate(payload)


@router.get(
    "/platform/model-configuration",
    response_model=ModelConfigurationResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def get_platform_model_configuration(
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
) -> ModelConfigurationResponse:
    require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    configuration = get_model_configuration(database)
    return ModelConfigurationResponse.model_validate(
        model_configuration_payload(configuration, _settings(request))
    )


@router.patch(
    "/platform/model-configuration",
    response_model=ModelConfigurationResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def patch_platform_model_configuration(
    body: UpdateModelConfigurationRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> ModelConfigurationResponse:
    actor = require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
    configuration = update_model_configuration(
        database,
        actor=actor,
        body=body,
        settings=_settings(request),
        request_id=request.state.request_id,
    )
    return ModelConfigurationResponse.model_validate(
        model_configuration_payload(configuration, _settings(request))
    )
