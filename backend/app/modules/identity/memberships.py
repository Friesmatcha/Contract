from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import (
    AuthSession,
    Organization,
    OrganizationMembership,
)
from backend.app.modules.identity.schemas import InviteMemberRequest, UpdateMemberRequest
from backend.app.modules.identity.service import issue_invitation_token_in_transaction
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
from backend.app.shared.tenant import TenantContext

MembershipSort = Literal["created_at", "display_name"]
MemberStatus = Literal["pending_invitation", "active", "disabled"]
DeliveryStatus = Literal["queued", "sent", "failed"]


@dataclass(frozen=True, slots=True)
class InvitationResult:
    membership: OrganizationMembership
    raw_token: str | None


def _now() -> datetime:
    return datetime.now(UTC)


def membership_payload(membership: OrganizationMembership) -> dict[str, Any]:
    return {
        "id": str(membership.id),
        "user_id": str(membership.user_id) if membership.user_id else None,
        "email": membership.email,
        "display_name": membership.display_name,
        "role": membership.role,
        "status": membership.status,
        "invited_at": membership.invited_at,
        "email_delivery_status": membership.email_delivery_status,
        "version": membership.version,
        "created_at": membership.created_at,
        "updated_at": membership.updated_at,
    }


def membership_page_payload(page: CursorPage[OrganizationMembership]) -> Mapping[str, Any]:
    return {
        "items": [membership_payload(item) for item in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


def list_members(
    session: Session,
    *,
    organization_id: UUID,
    q: str | None,
    role: str | None,
    status: MemberStatus | None,
    sort: MembershipSort,
    direction: SortDirection,
    limit: int,
    cursor: str | None,
) -> CursorPage[OrganizationMembership]:
    statement = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                OrganizationMembership.email.ilike(pattern),
                OrganizationMembership.display_name.ilike(pattern),
            )
        )
    if role is not None:
        statement = statement.where(OrganizationMembership.role == role)
    if status is not None:
        statement = statement.where(OrganizationMembership.status == status)
    if sort == "created_at":
        return paginate_by_created_at(
            session,
            statement,
            created_at_column=OrganizationMembership.created_at,
            id_column=OrganizationMembership.id,
            limit=limit,
            cursor=cursor,
            direction=direction,
        )
    return _paginate_by_display_name(
        session,
        statement,
        organization_id=organization_id,
        limit=limit,
        cursor=cursor,
        direction=direction,
    )


def _paginate_by_display_name(
    session: Session,
    statement: Any,
    *,
    organization_id: UUID,
    limit: int,
    cursor: str | None,
    direction: SortDirection,
) -> CursorPage[OrganizationMembership]:
    if not 1 <= limit <= 100:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="分页数量无效。",
            details={"field": "limit"},
        )
    name_column = func.lower(
        func.coalesce(OrganizationMembership.display_name, OrganizationMembership.email)
    )
    if cursor is not None:
        position = decode_cursor(cursor)
        anchor = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.id == position.id,
                OrganizationMembership.organization_id == organization_id,
            )
        )
        if anchor is None:
            raise InvalidCursorError
        anchor_name = (anchor.display_name or anchor.email).strip().lower()
        if direction == "desc":
            statement = statement.where(
                or_(
                    name_column < anchor_name,
                    and_(
                        name_column == anchor_name,
                        or_(
                            OrganizationMembership.created_at < position.created_at,
                            and_(
                                OrganizationMembership.created_at == position.created_at,
                                OrganizationMembership.id < position.id,
                            ),
                        ),
                    ),
                )
            )
        else:
            statement = statement.where(
                or_(
                    name_column > anchor_name,
                    and_(
                        name_column == anchor_name,
                        or_(
                            OrganizationMembership.created_at > position.created_at,
                            and_(
                                OrganizationMembership.created_at == position.created_at,
                                OrganizationMembership.id > position.id,
                            ),
                        ),
                    ),
                )
            )
    order = desc if direction == "desc" else asc
    rows = list(
        session.scalars(
            statement.order_by(
                order(name_column),
                order(OrganizationMembership.created_at),
                order(OrganizationMembership.id),
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


def invite_member(
    session: Session,
    *,
    actor: TenantContext,
    body: InviteMemberRequest,
    idempotency_key: str,
    request_id: str,
) -> InvitationResult:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/organizations/{organization_id}/members",
        path={"organization_id": actor.organization_id},
        body=body.model_dump(),
    )
    with UnitOfWork(session) as unit_of_work:
        created: OrganizationMembership | None = None
        issued_token: str | None = None

        def operation() -> IdempotencyResult:
            nonlocal created, issued_token
            membership = OrganizationMembership(
                id=uuid4(),
                organization_id=actor.organization_id,
                email=body.email,
                normalized_email=body.email,
                role=body.role,
                status="pending_invitation",
                invited_at=_now(),
                email_delivery_status="queued",
            )
            try:
                with session.begin_nested():
                    session.add(membership)
                    session.flush()
            except IntegrityError as exc:
                raise ApplicationError(
                    status_code=409,
                    code="MEMBERSHIP_ALREADY_EXISTS",
                    message="该邮箱已经存在于组织成员中。",
                ) from exc
            issued_token = issue_invitation_token_in_transaction(
                session, membership_id=membership.id
            )
            append_audit_log(
                session,
                actor=actor,
                action="organization.member_invited",
                resource_type="organization_membership",
                resource_id=membership.id,
                request_id=request_id,
                after={
                    "email": membership.email,
                    "role": membership.role,
                    "status": membership.status,
                    "email_delivery_status": membership.email_delivery_status,
                },
            )
            created = membership
            return IdempotencyResult(201, "organization_membership", membership.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/organizations/{organization_id}/members",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("membership idempotency record has no resource")
            created = session.get(OrganizationMembership, result.resource_id)
            issued_token = None
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("membership invitation returned no resource")
    return InvitationResult(created, issued_token)


def resend_invitation(
    session: Session,
    *,
    actor_user_id: UUID,
    member_id: UUID,
    idempotency_key: str,
    request_id: str,
    invitation_delivery_available: bool,
) -> InvitationResult:
    with UnitOfWork(session) as unit_of_work:
        membership = _authorized_member_for_update(
            session, actor_user_id=actor_user_id, member_id=member_id
        )
        actor = _tenant_context_for_member(
            session, actor_user_id=actor_user_id, organization_id=membership.organization_id
        )
        fingerprint = request_fingerprint(
            method="POST",
            operation_key="POST /api/v1/members/{member_id}/resend-invitation",
            path={"member_id": member_id},
            body={},
        )
        issued_token: str | None = None

        def operation() -> IdempotencyResult:
            nonlocal issued_token
            if membership.status != "pending_invitation":
                raise ApplicationError(
                    status_code=409,
                    code="MEMBER_NOT_PENDING_INVITATION",
                    message="只有待接受邀请的成员可以重发邀请。",
                )
            if not invitation_delivery_available:
                raise ApplicationError(
                    status_code=503,
                    code="SMTP_NOT_CONFIGURED",
                    message="认证邮件服务尚未配置。",
                )
            before = {
                "invited_at": (
                    membership.invited_at.isoformat() if membership.invited_at else None
                ),
                "email_delivery_status": membership.email_delivery_status,
            }
            issued_token = issue_invitation_token_in_transaction(
                session, membership_id=membership.id
            )
            membership.invited_at = _now()
            membership.email_delivery_status = "queued"
            membership.version += 1
            append_audit_log(
                session,
                actor=actor,
                action="organization.member_invitation_resent",
                resource_type="organization_membership",
                resource_id=membership.id,
                request_id=request_id,
                before=before,
                after={
                    "invited_at": (
                        membership.invited_at.isoformat() if membership.invited_at else None
                    ),
                    "email_delivery_status": membership.email_delivery_status,
                    "version": membership.version,
                },
            )
            return IdempotencyResult(202, "organization_membership", membership.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/members/{member_id}/resend-invitation",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            issued_token = None
        unit_of_work.commit()
    return InvitationResult(membership, issued_token)


def _authorized_member_for_update(
    session: Session, *, actor_user_id: UUID, member_id: UUID
) -> OrganizationMembership:
    membership = session.scalar(
        select(OrganizationMembership)
        .where(OrganizationMembership.id == member_id)
        .with_for_update()
    )
    if membership is None:
        raise ApplicationError(
            status_code=404, code="MEMBER_NOT_FOUND", message="成员不存在。"
        )
    organization = session.get(Organization, membership.organization_id)
    if organization is None or organization.status != "active":
        raise ApplicationError(
            status_code=404, code="MEMBER_NOT_FOUND", message="成员不存在。"
        )
    actor_membership = session.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == membership.organization_id,
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.status == "active",
        )
    )
    if actor_membership is None:
        raise ApplicationError(
            status_code=404, code="MEMBER_NOT_FOUND", message="成员不存在。"
        )
    if actor_membership.role != "org_admin":
        raise ApplicationError(
            status_code=403, code="ORG_ADMIN_REQUIRED", message="仅组织管理员可执行此操作。"
        )
    return membership


def _tenant_context_for_member(
    session: Session, *, actor_user_id: UUID, organization_id: UUID
) -> TenantContext:
    actor_membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.status == "active",
        )
    )
    if actor_membership is None or actor_membership.role != "org_admin":
        raise ApplicationError(
            status_code=403, code="ORG_ADMIN_REQUIRED", message="仅组织管理员可执行此操作。"
        )
    return TenantContext(
        organization_id=organization_id,
        user_id=actor_user_id,
        membership_id=actor_membership.id,
    )


def update_member(
    session: Session,
    *,
    actor_user_id: UUID,
    member_id: UUID,
    body: UpdateMemberRequest,
    request_id: str,
) -> OrganizationMembership:
    with UnitOfWork(session) as unit_of_work:
        membership = _authorized_member_for_update(
            session, actor_user_id=actor_user_id, member_id=member_id
        )
        actor = _tenant_context_for_member(
            session,
            actor_user_id=actor_user_id,
            organization_id=membership.organization_id,
        )
        if membership.version != body.version:
            raise ApplicationError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="资源已被更新，请刷新后重试。",
            )
        next_role = body.role or membership.role
        next_status = body.status or membership.status
        if next_status == "active" and membership.user_id is None:
            raise ApplicationError(
                status_code=409,
                code="INVALID_STATE_TRANSITION",
                message="邀请接受前不能激活成员。",
            )
        if (
            membership.role == "org_admin"
            and membership.status == "active"
            and (next_role != "org_admin" or next_status != "active")
        ):
            active_admins = list(
                session.scalars(
                    select(OrganizationMembership)
                    .where(
                        OrganizationMembership.organization_id == membership.organization_id,
                        OrganizationMembership.role == "org_admin",
                        OrganizationMembership.status == "active",
                    )
                    .with_for_update()
                )
            )
            if len(active_admins) <= 1:
                raise ApplicationError(
                    status_code=409,
                    code="LAST_ORG_ADMIN",
                    message="不能停用或降级组织最后一个有效管理员。",
                )
        before = {
            "role": membership.role,
            "status": membership.status,
            "version": membership.version,
        }
        membership.role = next_role
        membership.status = next_status
        membership.version += 1
        if membership.user_id is not None and (
            membership.role != before["role"] or membership.status != before["status"]
        ):
            session.execute(
                update(AuthSession).where(
                    AuthSession.user_id == membership.user_id,
                    AuthSession.revoked_at.is_(None),
                ).values(revoked_at=_now())
            )
        append_audit_log(
            session,
            actor=actor,
            action="organization.member_updated",
            resource_type="organization_membership",
            resource_id=membership.id,
            request_id=request_id,
            before=before,
            after={
                "role": membership.role,
                "status": membership.status,
                "version": membership.version,
            },
        )
        unit_of_work.commit()
    return membership


def mark_invitation_delivery(
    session_factory: sessionmaker[Session],
    *,
    membership_id: UUID,
    invited_at: datetime,
    status: DeliveryStatus,
) -> None:
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        membership = session.scalar(
            select(OrganizationMembership)
            .where(OrganizationMembership.id == membership_id)
            .with_for_update()
        )
        if (
            membership is not None
            and membership.status == "pending_invitation"
            and membership.invited_at == invited_at
            and membership.email_delivery_status == "queued"
        ):
            membership.email_delivery_status = status
            membership.version += 1
        unit_of_work.commit()
