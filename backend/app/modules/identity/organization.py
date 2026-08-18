from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.modules.identity.models import (
    AuthSession,
    Organization,
    OrganizationMembership,
    PlatformModelConfiguration,
    normalize_email,
)
from backend.app.modules.identity.schemas import (
    CreateOrganizationRequest,
    UpdateModelConfigurationRequest,
    UpdateOrganizationRequest,
    UpdateOrganizationSettingsRequest,
)
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, InvalidCursorError
from backend.app.shared.idempotency import (
    IdempotencyResult,
    execute_idempotent,
    platform_scope,
    request_fingerprint,
)
from backend.app.shared.pagination import CursorPage, CursorPosition, decode_cursor, encode_cursor
from backend.app.shared.tenant import PlatformContext, TenantContext

DEFAULT_FILE_SIZE_LIMIT_BYTES = 20 * 1024 * 1024
DEFAULT_PAGE_LIMIT = 100
DEFAULT_CONCURRENT_REVIEW_LIMIT = 3
DEFAULT_OCR_LOW_CONFIDENCE_THRESHOLD = 0.8
DEFAULT_RETENTION_DAYS = 180
DEFAULT_REPORT_WATERMARK = "仅供内部审核"
_SETTING_FIELDS = frozenset(
    {
        "file_size_limit_bytes",
        "page_limit",
        "concurrent_review_limit",
        "warn_on_medium_risk",
        "ocr_low_confidence_threshold",
        "retention_days",
        "report_watermark",
    }
)
_PERMISSIONS_BY_ROLE = {
    "org_admin": (
        "organization:read",
        "organization:settings:read",
        "organization:settings:write",
    ),
    "reviewer": (
        "organization:read",
        "contracts:read",
        "contracts:create",
        "reviews:write",
        "warnings:write",
    ),
    "viewer": ("organization:read", "contracts:read"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def default_organization_settings(retention_days: int = DEFAULT_RETENTION_DAYS) -> dict[str, Any]:
    return {
        "file_size_limit_bytes": DEFAULT_FILE_SIZE_LIMIT_BYTES,
        "page_limit": DEFAULT_PAGE_LIMIT,
        "concurrent_review_limit": DEFAULT_CONCURRENT_REVIEW_LIMIT,
        "warn_on_medium_risk": False,
        "ocr_low_confidence_threshold": DEFAULT_OCR_LOW_CONFIDENCE_THRESHOLD,
        "retention_days": retention_days,
        "report_watermark": DEFAULT_REPORT_WATERMARK,
    }


def organization_settings(organization: Organization) -> dict[str, Any]:
    settings = default_organization_settings(organization.retention_days)
    settings.update(
        {
            key: value
            for key, value in organization.settings_json.items()
            if key in _SETTING_FIELDS
        }
    )
    settings["retention_days"] = organization.retention_days
    return settings


def organization_payload(organization: Organization) -> dict[str, Any]:
    return {
        "id": str(organization.id),
        "name": organization.name,
        "status": organization.status,
        "retention_days": organization.retention_days,
        "settings": organization_settings(organization),
        "version": organization.version,
        "created_at": organization.created_at,
        "updated_at": organization.updated_at,
    }


def _platform_list_item(organization: Organization) -> dict[str, Any]:
    return {
        "id": str(organization.id),
        "name": organization.name,
        "status": organization.status,
        "retention_days": organization.retention_days,
        "created_at": organization.created_at,
    }


def require_platform_admin(user_id: UUID, is_platform_admin: bool) -> PlatformContext:
    if not is_platform_admin:
        raise ApplicationError(
            status_code=403,
            code="PLATFORM_ADMIN_REQUIRED",
            message="仅平台管理员可执行此操作。",
        )
    return PlatformContext(user_id)


def _organization_or_not_found(session: Session, organization_id: UUID) -> Organization:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise ApplicationError(
            status_code=404,
            code="ORGANIZATION_NOT_FOUND",
            message="组织不存在。",
        )
    return organization


def require_organization_member(
    session: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    require_org_admin: bool = False,
) -> tuple[Organization, TenantContext, str]:
    had_transaction = session.in_transaction()
    row = session.execute(
        select(Organization, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            Organization.id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    ).one_or_none()
    if row is None:
        raise ApplicationError(
            status_code=404,
            code="ORGANIZATION_NOT_FOUND",
            message="组织不存在。",
        )
    organization, membership = row
    if organization.status != "active":
        raise ApplicationError(
            status_code=404,
            code="ORGANIZATION_NOT_FOUND",
            message="组织不存在。",
        )
    if require_org_admin and membership.role != "org_admin":
        raise ApplicationError(
            status_code=403,
            code="ORG_ADMIN_REQUIRED",
            message="仅组织管理员可执行此操作。",
        )
    # End only the read transaction opened by this helper. A caller-owned
    # transaction may contain pending changes and must remain untouched.
    if not had_transaction and session.in_transaction():
        session.commit()
    return (
        organization,
        TenantContext(
            organization_id=organization.id,
            user_id=user_id,
            membership_id=membership.id,
        ),
        membership.role,
    )


def list_platform_organizations(
    session: Session,
    *,
    q: str | None,
    status: Literal["active", "disabled"] | None,
    sort: Literal["created_at", "name"],
    direction: Literal["asc", "desc"],
    limit: int,
    cursor: str | None,
) -> CursorPage[Organization]:
    if not 1 <= limit <= 100:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="分页数量无效。",
            details={"field": "limit"},
        )
    statement = select(Organization)
    if q:
        statement = statement.where(
            func.strpos(Organization.normalized_name, q.strip().lower()) > 0
        )
    if status is not None:
        statement = statement.where(Organization.status == status)

    if sort == "created_at":
        return _paginate_by_created_at(
            statement, session, limit=limit, cursor=cursor, direction=direction
        )
    return _paginate_by_name(statement, session, limit=limit, cursor=cursor, direction=direction)


def _paginate_by_created_at(
    statement: Any,
    session: Session,
    *,
    limit: int,
    cursor: str | None,
    direction: Literal["asc", "desc"],
) -> CursorPage[Organization]:
    if cursor is not None:
        position = decode_cursor(cursor)
        if direction == "desc":
            statement = statement.where(
                or_(
                    Organization.created_at < position.created_at,
                    and_(
                        Organization.created_at == position.created_at,
                        Organization.id < position.id,
                    ),
                )
            )
        else:
            statement = statement.where(
                or_(
                    Organization.created_at > position.created_at,
                    and_(
                        Organization.created_at == position.created_at,
                        Organization.id > position.id,
                    ),
                )
            )
    order = desc if direction == "desc" else asc
    rows = list(
        session.scalars(
            statement.order_by(order(Organization.created_at), order(Organization.id)).limit(
                limit + 1
            )
        )
    )
    return _cursor_page(rows, limit)


def _paginate_by_name(
    statement: Any,
    session: Session,
    *,
    limit: int,
    cursor: str | None,
    direction: Literal["asc", "desc"],
) -> CursorPage[Organization]:
    if cursor is not None:
        position = decode_cursor(cursor)
        anchor = session.get(Organization, position.id)
        if anchor is None:
            raise InvalidCursorError
        if direction == "desc":
            statement = statement.where(
                or_(
                    Organization.normalized_name < anchor.normalized_name,
                    and_(
                        Organization.normalized_name == anchor.normalized_name,
                        or_(
                            Organization.created_at < position.created_at,
                            and_(
                                Organization.created_at == position.created_at,
                                Organization.id < position.id,
                            ),
                        ),
                    ),
                )
            )
        else:
            statement = statement.where(
                or_(
                    Organization.normalized_name > anchor.normalized_name,
                    and_(
                        Organization.normalized_name == anchor.normalized_name,
                        or_(
                            Organization.created_at > position.created_at,
                            and_(
                                Organization.created_at == position.created_at,
                                Organization.id > position.id,
                            ),
                        ),
                    ),
                )
            )
    order = desc if direction == "desc" else asc
    rows = list(
        session.scalars(
            statement.order_by(
                order(Organization.normalized_name),
                order(Organization.created_at),
                order(Organization.id),
            ).limit(limit + 1)
        )
    )
    return _cursor_page(rows, limit)


def _cursor_page(rows: list[Organization], limit: int) -> CursorPage[Organization]:
    items = rows[:limit]
    has_more = len(rows) > limit
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(CursorPosition(created_at=last.created_at, id=last.id))
    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)


def create_organization(
    session: Session,
    *,
    actor: PlatformContext,
    body: CreateOrganizationRequest,
    idempotency_key: str,
    request_id: str,
) -> Organization:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/platform/organizations",
        body=body.model_dump(),
    )
    with UnitOfWork(session) as unit_of_work:
        created: Organization | None = None

        def operation() -> IdempotencyResult:
            nonlocal created
            organization = Organization(
                id=uuid4(),
                name=body.name,
                retention_days=body.retention_days,
                settings_json=default_organization_settings(body.retention_days),
            )
            membership = OrganizationMembership(
                organization_id=organization.id,
                email=body.initial_admin_email,
                normalized_email=normalize_email(body.initial_admin_email),
                role="org_admin",
                status="pending_invitation",
            )
            try:
                with session.begin_nested():
                    session.add_all([organization, membership])
                    session.flush()
            except IntegrityError as exc:
                raise ApplicationError(
                    status_code=409,
                    code="ORGANIZATION_NAME_CONFLICT",
                    message="组织名称已存在。",
                ) from exc
            append_audit_log(
                session,
                actor=actor,
                action="organization.created",
                resource_type="organization",
                resource_id=organization.id,
                request_id=request_id,
                after={
                    "name": organization.name,
                    "status": organization.status,
                    "retention_days": organization.retention_days,
                },
            )
            created = organization
            return IdempotencyResult(201, "organization", organization.id)

        result = execute_idempotent(
            session,
            scope=platform_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/platform/organizations",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("organization idempotency record has no resource")
            created = _organization_or_not_found(session, result.resource_id)
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("organization creation returned no resource")
    return created


def update_organization(
    session: Session,
    *,
    actor: PlatformContext,
    organization_id: UUID,
    body: UpdateOrganizationRequest,
    request_id: str,
) -> Organization:
    with UnitOfWork(session) as unit_of_work:
        organization = session.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if organization is None:
            raise ApplicationError(
                status_code=404,
                code="ORGANIZATION_NOT_FOUND",
                message="组织不存在。",
            )
        if organization.version != body.version:
            raise ApplicationError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="资源已被更新，请刷新后重试。",
            )
        before = {
            "name": organization.name,
            "status": organization.status,
            "retention_days": organization.retention_days,
        }
        if body.name is not None:
            try:
                with session.begin_nested():
                    organization.name = body.name
                    session.flush()
            except IntegrityError as exc:
                raise ApplicationError(
                    status_code=409,
                    code="ORGANIZATION_NAME_CONFLICT",
                    message="组织名称已存在。",
                ) from exc
        if body.status is not None:
            organization.status = body.status
        if body.retention_days is not None:
            organization.retention_days = body.retention_days
            settings = organization_settings(organization)
            settings["retention_days"] = body.retention_days
            organization.settings_json = settings
        if body.status == "disabled" and before["status"] != "disabled":
            member_user_ids = select(OrganizationMembership.user_id).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id.is_not(None),
            )
            session.execute(
                update(AuthSession)
                .where(AuthSession.user_id.in_(member_user_ids), AuthSession.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
        organization.version += 1
        append_audit_log(
            session,
            actor=actor,
            action="organization.updated",
            resource_type="organization",
            resource_id=organization.id,
            request_id=request_id,
            before=before,
            after={
                "name": organization.name,
                "status": organization.status,
                "retention_days": organization.retention_days,
            },
        )
        unit_of_work.commit()
    return organization


def organization_profile(
    organization: Organization,
    *,
    role: str,
) -> dict[str, Any]:
    permissions = _PERMISSIONS_BY_ROLE.get(role)
    if permissions is None:
        raise RuntimeError("unknown organization membership role")
    return {
        "id": str(organization.id),
        "name": organization.name,
        "status": organization.status,
        "my_role": role,
        "permissions": list(permissions),
    }


def update_organization_settings(
    session: Session,
    *,
    actor: TenantContext,
    organization: Organization,
    body: UpdateOrganizationSettingsRequest,
    request_id: str,
) -> dict[str, Any]:
    with UnitOfWork(session) as unit_of_work:
        locked = session.scalar(
            select(Organization).where(Organization.id == organization.id).with_for_update()
        )
        if locked is None:
            raise ApplicationError(
                status_code=404,
                code="ORGANIZATION_NOT_FOUND",
                message="组织不存在。",
            )
        if locked.version != body.version:
            raise ApplicationError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="资源已被更新，请刷新后重试。",
            )
        updates = body.model_dump(exclude_none=True, exclude={"version"})
        settings = organization_settings(locked)
        settings.update(updates)
        retention_days = int(settings["retention_days"])
        locked.retention_days = retention_days
        settings["retention_days"] = retention_days
        locked.settings_json = settings
        locked.version += 1
        append_audit_log(
            session,
            actor=actor,
            action="organization.settings_updated",
            resource_type="organization",
            resource_id=locked.id,
            request_id=request_id,
            before={"changed_fields": sorted(updates), "version": body.version},
            after={"changed_fields": sorted(updates), "version": locked.version},
        )
        unit_of_work.commit()
    return {**organization_settings(locked), "version": locked.version}


def model_environment_configured(settings: Settings) -> bool:
    return bool(
        settings.model_name
        and settings.model_api_key is not None
        and settings.model_api_key.get_secret_value().strip()
    )


def model_configuration_payload(
    configuration: PlatformModelConfiguration,
    settings: Settings,
) -> dict[str, Any]:
    return {
        "provider": settings.model_provider,
        "model": settings.model_name or "not-configured",
        "model_source": "environment",
        "timeout_seconds": configuration.timeout_seconds,
        "max_retries": configuration.max_retries,
        "hard_budget_enabled": False,
        "usage_tracking_enabled": configuration.usage_tracking_enabled,
        "organization_overrides_allowed": False,
        "secret_configured": model_environment_configured(settings),
        "status": configuration.status,
        "version": configuration.version,
    }


def _model_configuration_or_error(
    session: Session, *, for_update: bool = False
) -> PlatformModelConfiguration:
    statement = select(PlatformModelConfiguration).where(
        PlatformModelConfiguration.singleton_key == 1
    )
    if for_update:
        statement = statement.with_for_update()
    configuration = session.scalar(statement)
    if configuration is None:
        raise RuntimeError("platform model configuration is missing")
    return configuration


def get_model_configuration(session: Session) -> PlatformModelConfiguration:
    return _model_configuration_or_error(session)


def update_model_configuration(
    session: Session,
    *,
    actor: PlatformContext,
    body: UpdateModelConfigurationRequest,
    settings: Settings,
    request_id: str,
) -> PlatformModelConfiguration:
    if not model_environment_configured(settings):
        raise ApplicationError(
            status_code=503,
            code="MODEL_ENVIRONMENT_NOT_CONFIGURED",
            message="模型环境配置尚未完成。",
        )
    with UnitOfWork(session) as unit_of_work:
        configuration = _model_configuration_or_error(session, for_update=True)
        if configuration.version != body.version:
            raise ApplicationError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="资源已被更新，请刷新后重试。",
            )
        before = {
            "timeout_seconds": configuration.timeout_seconds,
            "max_retries": configuration.max_retries,
            "usage_tracking_enabled": configuration.usage_tracking_enabled,
            "status": configuration.status,
        }
        updates = body.model_dump(exclude_none=True, exclude={"version"})
        for field, value in updates.items():
            setattr(configuration, field, value)
        configuration.version += 1
        append_audit_log(
            session,
            actor=actor,
            action="platform.model_configuration_updated",
            resource_type="platform_model_configuration",
            resource_id=configuration.id,
            request_id=request_id,
            before=before,
            after={
                "timeout_seconds": configuration.timeout_seconds,
                "max_retries": configuration.max_retries,
                "usage_tracking_enabled": configuration.usage_tracking_enabled,
                "status": configuration.status,
            },
        )
        unit_of_work.commit()
    return configuration


def cursor_page_payload(page: CursorPage[Organization]) -> Mapping[str, Any]:
    return {
        "items": [_platform_list_item(organization) for organization in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }
