from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.modules.identity.models import (
    SupportAccessGrant,
    User,
)
from backend.app.modules.identity.schemas import CreateSupportAccessGrantRequest
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, InvalidCursorError
from backend.app.shared.idempotency import (
    IdempotencyResult,
    execute_idempotent,
    organization_scope,
    request_fingerprint,
)
from backend.app.shared.pagination import (
    CursorPage,
    CursorPosition,
    SortDirection,
    decode_cursor,
    encode_cursor,
    paginate_by_created_at,
)
from backend.app.shared.tenant import PlatformContext, TenantContext

SupportGrantStatus = Literal["active", "expired", "revoked"]
SupportGrantSort = Literal["created_at", "expires_at"]


def _now() -> datetime:
    return datetime.now(UTC)


def _effective_status(grant: SupportAccessGrant, now: datetime) -> str:
    if grant.status == "active" and grant.expires_at <= now:
        return "expired"
    return grant.status


def support_access_grant_payload(
    grant: SupportAccessGrant, *, now: datetime | None = None
) -> dict[str, Any]:
    return {
        "id": str(grant.id),
        "organization_id": str(grant.organization_id),
        "platform_admin_user_id": str(grant.platform_admin_user_id),
        "reason": grant.reason,
        "status": _effective_status(grant, now or _now()),
        "granted_by": str(grant.granted_by),
        "created_at": grant.created_at,
        "expires_at": grant.expires_at,
    }


def support_access_page_payload(
    page: CursorPage[SupportAccessGrant], *, now: datetime | None = None
) -> Mapping[str, Any]:
    effective_now = now or _now()
    return {
        "items": [
            support_access_grant_payload(grant, now=effective_now) for grant in page.items
        ],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


def list_support_access_grants(
    session: Session,
    *,
    organization_id: UUID,
    status: SupportGrantStatus | None,
    platform_admin_user_id: UUID | None,
    sort: SupportGrantSort,
    direction: SortDirection,
    limit: int,
    cursor: str | None,
) -> CursorPage[SupportAccessGrant]:
    now = _now()
    statement = select(SupportAccessGrant).where(
        SupportAccessGrant.organization_id == organization_id
    )
    if status == "active":
        statement = statement.where(
            SupportAccessGrant.status == "active",
            SupportAccessGrant.expires_at > now,
        )
    elif status == "expired":
        statement = statement.where(
            or_(
                SupportAccessGrant.status == "expired",
                and_(
                    SupportAccessGrant.status == "active",
                    SupportAccessGrant.expires_at <= now,
                ),
            )
        )
    elif status == "revoked":
        statement = statement.where(SupportAccessGrant.status == "revoked")
    if platform_admin_user_id is not None:
        statement = statement.where(
            SupportAccessGrant.platform_admin_user_id == platform_admin_user_id
        )
    if sort == "created_at":
        return paginate_by_created_at(
            session,
            statement,
            created_at_column=SupportAccessGrant.created_at,
            id_column=SupportAccessGrant.id,
            limit=limit,
            cursor=cursor,
            direction=direction,
        )
    return _paginate_by_expires_at(
        session,
        statement,
        organization_id=organization_id,
        limit=limit,
        cursor=cursor,
        direction=direction,
    )


def _paginate_by_expires_at(
    session: Session,
    statement: Any,
    *,
    organization_id: UUID,
    limit: int,
    cursor: str | None,
    direction: SortDirection,
) -> CursorPage[SupportAccessGrant]:
    if not 1 <= limit <= 100:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="分页数量无效。",
            details={"field": "limit"},
        )
    if cursor is not None:
        position = decode_cursor(cursor)
        anchor = session.scalar(
            select(SupportAccessGrant).where(
                SupportAccessGrant.organization_id == organization_id,
                SupportAccessGrant.id == position.id,
            )
        )
        if anchor is None:
            raise InvalidCursorError
        order = desc if direction == "desc" else asc
        boundary = (
            SupportAccessGrant.expires_at < anchor.expires_at
            if direction == "desc"
            else SupportAccessGrant.expires_at > anchor.expires_at
        )
        tie_boundary = (
            SupportAccessGrant.created_at < position.created_at
            if direction == "desc"
            else SupportAccessGrant.created_at > position.created_at
        )
        id_boundary = (
            SupportAccessGrant.id < position.id
            if direction == "desc"
            else SupportAccessGrant.id > position.id
        )
        statement = statement.where(
            or_(
                boundary,
                and_(
                    SupportAccessGrant.expires_at == anchor.expires_at,
                    or_(
                        tie_boundary,
                        and_(
                            SupportAccessGrant.created_at == position.created_at,
                            id_boundary,
                        ),
                    ),
                ),
            )
        )
    else:
        order = desc if direction == "desc" else asc
    rows = list(
        session.scalars(
            statement.order_by(
                order(SupportAccessGrant.expires_at),
                order(SupportAccessGrant.created_at),
                order(SupportAccessGrant.id),
            ).limit(limit + 1)
        )
    )
    items = rows[:limit]
    has_more = len(rows) > limit
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(CursorPosition(created_at=last.created_at, id=last.id))
    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)


def create_support_access_grant(
    session: Session,
    *,
    actor: TenantContext,
    body: CreateSupportAccessGrantRequest,
    idempotency_key: str,
    request_id: str,
) -> SupportAccessGrant:
    expires_at = body.expires_at.astimezone(UTC)
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/organizations/{organization_id}/support-access-grants",
        path={"organization_id": actor.organization_id},
        body={
            "platform_admin_user_id": body.platform_admin_user_id,
            "reason": body.reason,
            "expires_at": expires_at,
        },
    )
    with UnitOfWork(session) as unit_of_work:
        created: SupportAccessGrant | None = None

        def operation() -> IdempotencyResult:
            nonlocal created
            now = _now()
            if expires_at <= now or expires_at > now + timedelta(hours=4):
                raise ApplicationError(
                    status_code=422,
                    code="SUPPORT_GRANT_DURATION_INVALID",
                    message="支持授权必须晚于当前时间且不超过 4 小时。",
                )
            session.execute(
                update(SupportAccessGrant)
                .where(
                    SupportAccessGrant.organization_id == actor.organization_id,
                    SupportAccessGrant.status == "active",
                    SupportAccessGrant.expires_at <= now,
                )
                .values(status="expired")
            )
            target = session.scalar(
                select(User).where(
                    User.id == body.platform_admin_user_id,
                    User.is_platform_admin.is_(True),
                    User.status == "active",
                )
            )
            if target is None:
                raise ApplicationError(
                    status_code=404,
                    code="PLATFORM_ADMIN_NOT_FOUND",
                    message="平台管理员不存在。",
                )
            grant = SupportAccessGrant(
                id=uuid4(),
                organization_id=actor.organization_id,
                platform_admin_user_id=body.platform_admin_user_id,
                reason=body.reason,
                status="active",
                granted_by=actor.user_id,
                expires_at=expires_at,
            )
            try:
                with session.begin_nested():
                    session.add(grant)
                    session.flush()
            except IntegrityError as exc:
                raise ApplicationError(
                    status_code=409,
                    code="ACTIVE_SUPPORT_GRANT_EXISTS",
                    message="该平台管理员已有有效支持授权。",
                ) from exc
            append_audit_log(
                session,
                actor=actor,
                action="support_access.grant_created",
                resource_type="support_access_grant",
                resource_id=grant.id,
                request_id=request_id,
                after={
                    "platform_admin_user_id": str(grant.platform_admin_user_id),
                    "reason": grant.reason,
                    "status": grant.status,
                    "expires_at": grant.expires_at.isoformat(),
                },
            )
            created = grant
            return IdempotencyResult(201, "support_access_grant", grant.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/organizations/{organization_id}/support-access-grants",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("support access idempotency record has no resource")
            created = session.scalar(
                select(SupportAccessGrant).where(
                    SupportAccessGrant.organization_id == actor.organization_id,
                    SupportAccessGrant.id == result.resource_id,
                )
            )
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("support access grant returned no resource")
    return created


def revoke_support_access_grant(
    session: Session,
    *,
    actor: TenantContext,
    grant_id: UUID,
    request_id: str,
) -> None:
    with UnitOfWork(session) as unit_of_work:
        grant = session.scalar(
            select(SupportAccessGrant)
            .where(
                SupportAccessGrant.organization_id == actor.organization_id,
                SupportAccessGrant.id == grant_id,
            )
            .with_for_update()
        )
        if grant is None:
            raise ApplicationError(
                status_code=404,
                code="SUPPORT_GRANT_NOT_FOUND",
                message="支持授权不存在。",
            )
        if grant.status == "active" and grant.expires_at > _now():
            before = {"status": grant.status}
            grant.status = "revoked"
            grant.revoked_at = _now()
            grant.revoked_by = actor.user_id
            append_audit_log(
                session,
                actor=actor,
                action="support_access.grant_revoked",
                resource_type="support_access_grant",
                resource_id=grant.id,
                request_id=request_id,
                before=before,
                after={"status": grant.status},
            )
        elif grant.status == "active":
            grant.status = "expired"
        unit_of_work.commit()


def authorize_support_access(
    session: Session,
    *,
    grant_id: UUID,
    platform_admin_user_id: UUID,
    request_id: str,
) -> SupportAccessGrant:
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        grant = session.scalar(
            select(SupportAccessGrant)
            .join(User, User.id == SupportAccessGrant.platform_admin_user_id)
            .where(
                SupportAccessGrant.id == grant_id,
                SupportAccessGrant.status == "active",
                SupportAccessGrant.expires_at > now,
                SupportAccessGrant.platform_admin_user_id == platform_admin_user_id,
                User.is_platform_admin.is_(True),
                User.status == "active",
            )
        )
        if grant is None:
            raise ApplicationError(
                status_code=403,
                code="SUPPORT_ACCESS_REQUIRED",
                message="需要有效的临时支持授权。",
            )
        append_audit_log(
            session,
            actor=PlatformContext(platform_admin_user_id),
            action="support_access.grant_used",
            resource_type="support_access_grant",
            resource_id=grant.id,
            organization_id=grant.organization_id,
            request_id=request_id,
            after={"grant_id": str(grant.id)},
        )
        unit_of_work.commit()
    return grant
