import logging
from datetime import datetime
from typing import Annotated, Literal, cast
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request, Response, status
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings
from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.integrations.notifications.smtp import Mailer, UnavailableMailer
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.memberships import (
    InvitationResult,
    invite_member,
    list_members,
    mark_invitation_delivery,
    membership_page_payload,
    membership_payload,
    resend_invitation,
    update_member,
)
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
    CreateSupportAccessGrantRequest,
    InviteMemberRequest,
    MembershipPage,
    MembershipResponse,
    ModelConfigurationResponse,
    OrganizationProfileResponse,
    OrganizationResponse,
    OrganizationSettingsResponse,
    PlatformOrganizationPage,
    SupportAccessGrantPage,
    SupportAccessGrantResponse,
    UpdateMemberRequest,
    UpdateModelConfigurationRequest,
    UpdateOrganizationRequest,
    UpdateOrganizationSettingsRequest,
)
from backend.app.modules.identity.service import consume_rate_limit
from backend.app.modules.identity.support_access import (
    create_support_access_grant,
    list_support_access_grants,
    revoke_support_access_grant,
    support_access_grant_payload,
    support_access_page_payload,
)
from backend.app.shared.errors import ApplicationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["organization and platform configuration"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _require_invitation_delivery(request: Request) -> None:
    if not _invitation_delivery_available(request):
        raise ApplicationError(
            status_code=503,
            code="SMTP_NOT_CONFIGURED",
            message="认证邮件服务尚未配置。",
        )


def _invitation_delivery_available(request: Request) -> bool:
    settings = _settings(request)
    return not isinstance(request.app.state.mailer, UnavailableMailer) and bool(
        settings.frontend_base_url
    )


def _send_invitation_safely(
    mailer: Mailer,
    session_factory: sessionmaker[Session],
    *,
    membership_id: UUID,
    invited_at: datetime,
    recipient: str,
    invitation_url: str,
    request_id: str,
) -> None:
    try:
        mailer.send_invitation(recipient=recipient, invitation_url=invitation_url)
    except Exception as exc:
        mark_invitation_delivery(
            session_factory,
            membership_id=membership_id,
            invited_at=invited_at,
            status="failed",
        )
        logger.error(
            "identity_email_delivery_failed",
            extra={
                "request_id": request_id,
                "delivery_stage": "invitation",
                "error_class": type(exc).__name__,
            },
        )
    else:
        mark_invitation_delivery(
            session_factory,
            membership_id=membership_id,
            invited_at=invited_at,
            status="sent",
        )


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


@router.get(
    "/organizations/{organization_id}/members",
    response_model=MembershipPage,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_organization_members(
    organization_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
    q: Annotated[str | None, Query(max_length=255)] = None,
    member_role: Annotated[
        Literal["org_admin", "reviewer", "viewer"] | None, Query(alias="role")
    ] = None,
    member_status: Annotated[
        Literal["pending_invitation", "active", "disabled"] | None, Query(alias="status")
    ] = None,
    sort: Literal["created_at", "display_name"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> MembershipPage:
    require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    page = list_members(
        database,
        organization_id=organization_id,
        q=q,
        role=member_role,
        status=member_status,
        sort=sort,
        direction=direction,
        limit=limit,
        cursor=cursor,
    )
    return MembershipPage.model_validate(membership_page_payload(page))


@router.post(
    "/organizations/{organization_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def post_organization_member(
    organization_id: UUID,
    body: InviteMemberRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> MembershipResponse:
    _, actor, _ = require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    _require_invitation_delivery(request)
    result = invite_member(
        database,
        actor=actor,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    _queue_invitation_delivery(request, background_tasks, result)
    return MembershipResponse.model_validate(membership_payload(result.membership))


@router.post(
    "/members/{member_id}/resend-invitation",
    response_model=MembershipResponse,
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
def post_resend_member_invitation(
    member_id: UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> MembershipResponse:
    consume_rate_limit(
        database,
        action="invite:resend:user",
        key=str(authenticated.user.id),
        limit=5,
    )
    result = resend_invitation(
        database,
        actor_user_id=authenticated.user.id,
        member_id=member_id,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
        invitation_delivery_available=_invitation_delivery_available(request),
    )
    _queue_invitation_delivery(request, background_tasks, result)
    return MembershipResponse.model_validate(membership_payload(result.membership))


def _queue_invitation_delivery(
    request: Request,
    background_tasks: BackgroundTasks,
    result: InvitationResult,
) -> None:
    if result.raw_token is None or result.membership.invited_at is None:
        return
    settings = _settings(request)
    base_url = settings.frontend_base_url
    if not base_url:
        return
    session_factory = cast(sessionmaker[Session], request.app.state.session_factory)
    background_tasks.add_task(
        _send_invitation_safely,
        request.app.state.mailer,
        session_factory,
        membership_id=result.membership.id,
        invited_at=result.membership.invited_at,
        recipient=result.membership.email,
        invitation_url=(
            f"{base_url.rstrip('/')}/invitations/accept?"
            f"{urlencode({'token': result.raw_token})}"
        ),
        request_id=request.state.request_id,
    )


@router.patch(
    "/members/{member_id}",
    response_model=MembershipResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def patch_organization_member(
    member_id: UUID,
    body: UpdateMemberRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> MembershipResponse:
    member = update_member(
        database,
        actor_user_id=authenticated.user.id,
        member_id=member_id,
        body=body,
        request_id=request.state.request_id,
    )
    return MembershipResponse.model_validate(membership_payload(member))


@router.get(
    "/organizations/{organization_id}/support-access-grants",
    response_model=SupportAccessGrantPage,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_support_access_grants(
    organization_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
    grant_status: Annotated[
        Literal["active", "expired", "revoked"] | None, Query(alias="status")
    ] = None,
    platform_admin_user_id: UUID | None = None,
    sort: Literal["created_at", "expires_at"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> SupportAccessGrantPage:
    require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    page = list_support_access_grants(
        database,
        organization_id=organization_id,
        status=grant_status,
        platform_admin_user_id=platform_admin_user_id,
        sort=sort,
        direction=direction,
        limit=limit,
        cursor=cursor,
    )
    return SupportAccessGrantPage.model_validate(support_access_page_payload(page))


@router.post(
    "/organizations/{organization_id}/support-access-grants",
    response_model=SupportAccessGrantResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_support_access_grant(
    organization_id: UUID,
    body: CreateSupportAccessGrantRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> SupportAccessGrantResponse:
    _, actor, _ = require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    grant = create_support_access_grant(
        database,
        actor=actor,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    return SupportAccessGrantResponse.model_validate(support_access_grant_payload(grant))


@router.delete(
    "/organizations/{organization_id}/support-access-grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def delete_support_access_grant(
    organization_id: UUID,
    grant_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> Response:
    _, actor, _ = require_organization_member(
        database,
        organization_id=organization_id,
        user_id=authenticated.user.id,
        require_org_admin=True,
    )
    revoke_support_access_grant(
        database,
        actor=actor,
        grant_id=grant_id,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
