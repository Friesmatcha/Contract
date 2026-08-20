import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, func, or_, select, text
from sqlalchemy.orm import Session

from backend.app.modules.contracts.models import (
    Contract,
    ContractAccessGrant,
    ContractFile,
    FileObject,
)
from backend.app.modules.contracts.schemas import (
    ContractAccessGrantRequest,
    CreateContractRequest,
    UpdateContractRequest,
)
from backend.app.modules.identity.models import Organization, OrganizationMembership, User
from backend.app.modules.reviews.models import ACTIVE_REVIEW_STATUSES, ReviewTask
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, InvalidCursorError
from backend.app.shared.idempotency import (
    IdempotencyResult,
    execute_idempotent,
    organization_scope,
    request_fingerprint,
)
from backend.app.shared.tenant import TenantContext

ContractSort = Literal["created_at", "updated_at", "title"]
SortDirection = Literal["asc", "desc"]


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found() -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code="CONTRACT_NOT_FOUND",
        message="合同不存在。",
    )


def _contract_or_not_found(
    session: Session, *, organization_id: UUID, contract_id: UUID, for_update: bool = False
) -> Contract:
    statement = select(Contract).where(
        Contract.organization_id == organization_id,
        Contract.id == contract_id,
    )
    if for_update:
        statement = statement.with_for_update()
    contract = session.scalar(statement)
    if contract is None:
        raise _not_found()
    return contract


def _next_display_no(session: Session) -> str:
    sequence_value = session.execute(
        text("SELECT nextval('contract_display_no_seq')")
    ).scalar_one()
    return f"CTR-{_now().strftime('%Y%m%d')}-{int(sequence_value):06d}"


def _file_summaries(session: Session, contract: Contract) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ContractFile, FileObject)
        .join(
            FileObject,
            and_(
                FileObject.organization_id == ContractFile.organization_id,
                FileObject.id == ContractFile.file_object_id,
            ),
        )
        .where(
            ContractFile.organization_id == contract.organization_id,
            ContractFile.contract_id == contract.id,
        )
        .order_by(ContractFile.version_no.desc())
    ).all()
    return [
        {
            "id": file_object.id,
            "version_no": contract_file.version_no,
            "is_current": contract_file.is_current,
            "original_name": file_object.original_name,
            "media_type": file_object.media_type,
            "size_bytes": file_object.size_bytes,
            "scan_status": file_object.scan_status,
            "storage_status": file_object.storage_status,
            "created_at": contract_file.created_at,
            "external_model_notice_acknowledged_at": (
                contract_file.external_model_notice_acknowledged_at
            ),
        }
        for contract_file, file_object in rows
    ]


def _empty_file_and_review(session: Session, contract: Contract) -> dict[str, Any]:
    files = _file_summaries(session, contract)
    latest_review = session.scalar(
        select(ReviewTask)
        .where(
            ReviewTask.organization_id == contract.organization_id,
            ReviewTask.contract_id == contract.id,
        )
        .order_by(ReviewTask.created_at.desc(), ReviewTask.id.desc())
    )
    return {
        "id": contract.id,
        "display_no": contract.display_no,
        "title": contract.title,
        "declared_type": contract.declared_type,
        "status": contract.status,
        "owner_id": contract.owner_id,
        "current_file": next((file for file in files if file["is_current"]), None),
        "files": files,
        "latest_review": (
            {"id": latest_review.id, "status": latest_review.status}
            if latest_review is not None
            else None
        ),
        "created_at": contract.created_at,
        "updated_at": contract.updated_at,
        "version": contract.version,
    }


def contract_payload(session: Session, contract: Contract) -> dict[str, Any]:
    return _empty_file_and_review(session, contract)


def contract_status_payload(contract: Contract) -> dict[str, Any]:
    return {
        "id": contract.id,
        "status": contract.status,
        "archived_at": contract.archived_at,
    }


def access_grant_payload(grant: ContractAccessGrant) -> dict[str, Any]:
    return {
        "contract_id": grant.contract_id,
        "user_id": grant.user_id,
        "access_level": grant.access_level,
    }


def create_contract(
    session: Session,
    *,
    actor: TenantContext,
    body: CreateContractRequest,
    idempotency_key: str,
    request_id: str,
) -> Contract:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/contracts",
        body=body.model_dump(),
    )
    created: Contract | None = None
    with UnitOfWork(session) as unit_of_work:

        def operation() -> IdempotencyResult:
            nonlocal created
            contract = Contract(
                id=uuid4(),
                organization_id=actor.organization_id,
                display_no=_next_display_no(session),
                title=body.title,
                declared_type=body.declared_type,
                owner_id=actor.user_id,
            )
            session.add(contract)
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="contract.created",
                resource_type="contract",
                resource_id=contract.id,
                request_id=request_id,
                after={
                    "display_no": contract.display_no,
                    "title": contract.title,
                    "declared_type": contract.declared_type,
                    "status": contract.status,
                },
            )
            created = contract
            return IdempotencyResult(201, "contract", contract.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/contracts",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("contract idempotency record has no resource")
            created = session.get(Contract, result.resource_id)
            if created is None:
                raise RuntimeError("contract idempotency resource is missing")
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("contract creation returned no resource")
    return created


def _cursor_encode(*, sort: ContractSort, value: str, contract: Contract) -> str:
    payload = {
        "created_at": contract.created_at.isoformat(),
        "id": str(contract.id),
        "sort": sort,
        "value": value,
        "v": 1,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def _cursor_decode(value: str, *, sort: ContractSort) -> tuple[str, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding))
        if not isinstance(payload, dict) or set(payload) != {
            "created_at",
            "id",
            "sort",
            "value",
            "v",
        }:
            raise ValueError
        if payload["v"] != 1 or payload["sort"] != sort:
            raise ValueError
        datetime.fromisoformat(payload["created_at"])
        return str(payload["value"]), UUID(str(payload["id"]))
    except (TypeError, ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise InvalidCursorError from exc


def _sort_column(sort: ContractSort) -> Any:
    if sort == "title":
        return func.lower(Contract.title)
    return getattr(Contract, sort)


def list_contracts(
    session: Session,
    *,
    organization_id: UUID,
    viewer_user_id: UUID | None,
    q: str | None,
    status: str | None,
    declared_type: str | None,
    owner_id: UUID | None,
    sort: ContractSort,
    direction: SortDirection,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    statement = select(Contract).where(Contract.organization_id == organization_id)
    if viewer_user_id is not None:
        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == Contract.organization_id,
                ContractAccessGrant.contract_id == Contract.id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(Contract.title.ilike(pattern), Contract.display_no.ilike(pattern))
        )
    if status is not None:
        statement = statement.where(Contract.status == status)
    if declared_type is not None:
        statement = statement.where(Contract.declared_type == declared_type)
    if owner_id is not None:
        statement = statement.where(Contract.owner_id == owner_id)
    if not 1 <= limit <= 100:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="分页数量无效。",
            details={"field": "limit"},
        )

    sort_column = _sort_column(sort)
    if cursor is not None:
        cursor_value, cursor_id = _cursor_decode(cursor, sort=sort)
        typed_value: Any = cursor_value
        if sort in {"created_at", "updated_at"}:
            try:
                typed_value = datetime.fromisoformat(cursor_value)
            except ValueError as exc:
                raise InvalidCursorError from exc
        if direction == "desc":
            boundary = or_(
                sort_column < typed_value,
                and_(sort_column == typed_value, Contract.id < cursor_id),
            )
        else:
            boundary = or_(
                sort_column > typed_value,
                and_(sort_column == typed_value, Contract.id > cursor_id),
            )
        statement = statement.where(boundary)

    order = desc if direction == "desc" else asc
    rows = list(
        session.scalars(
            statement.order_by(order(sort_column), order(Contract.id)).limit(limit + 1)
        )
    )
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit and items:
        last = items[-1]
        last_value = (
            (last.title or "").strip().lower()
            if sort == "title"
            else getattr(last, sort).isoformat()
        )
        next_cursor = _cursor_encode(sort=sort, value=last_value, contract=last)
    return {
        "items": [contract_payload(session, contract) for contract in items],
        "next_cursor": next_cursor,
        "has_more": len(rows) > limit,
    }


def get_contract(
    session: Session,
    *,
    organization_id: UUID,
    contract_id: UUID,
    viewer_user_id: UUID | None,
) -> Contract:
    statement = select(Contract).where(
        Contract.organization_id == organization_id,
        Contract.id == contract_id,
    )
    if viewer_user_id is not None:
        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == Contract.organization_id,
                ContractAccessGrant.contract_id == Contract.id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    contract = session.scalar(statement)
    if contract is None:
        raise _not_found()
    return contract


def update_contract(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    body: UpdateContractRequest,
    request_id: str,
) -> Contract:
    with UnitOfWork(session) as unit_of_work:
        contract = _contract_or_not_found(
            session,
            organization_id=actor.organization_id,
            contract_id=contract_id,
            for_update=True,
        )
        if contract.status == "archived":
            raise ApplicationError(
                status_code=409,
                code="CONTRACT_ARCHIVED",
                message="归档合同不可修改。",
            )
        if contract.version != body.version:
            raise ApplicationError(
                status_code=409,
                code="RESOURCE_VERSION_CONFLICT",
                message="资源已被更新，请刷新后重试。",
            )
        before = {
            "title": contract.title,
            "declared_type": contract.declared_type,
            "version": contract.version,
        }
        if "title" in body.model_fields_set and body.title is not None:
            contract.title = body.title
        if "declared_type" in body.model_fields_set:
            contract.declared_type = body.declared_type
        contract.version += 1
        append_audit_log(
            session,
            actor=actor,
            action="contract.updated",
            resource_type="contract",
            resource_id=contract.id,
            request_id=request_id,
            before=before,
            after={
                "title": contract.title,
                "declared_type": contract.declared_type,
                "version": contract.version,
            },
        )
        unit_of_work.commit()
    return contract


def archive_contract(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    request_id: str,
) -> Contract:
    with UnitOfWork(session) as unit_of_work:
        organization = session.scalar(
            select(Organization)
            .where(Organization.id == actor.organization_id)
            .with_for_update()
        )
        if organization is None or organization.status != "active":
            raise ApplicationError(
                status_code=404,
                code="ORGANIZATION_NOT_FOUND",
                message="组织不存在。",
            )
        contract = _contract_or_not_found(
            session,
            organization_id=actor.organization_id,
            contract_id=contract_id,
            for_update=True,
        )
        if contract.status == "active":
            active_review = session.scalar(
                select(ReviewTask.id)
                .where(
                    ReviewTask.organization_id == actor.organization_id,
                    ReviewTask.contract_id == contract.id,
                    ReviewTask.status.in_(ACTIVE_REVIEW_STATUSES),
                )
                .limit(1)
            )
            if active_review is not None:
                raise ApplicationError(
                    status_code=409,
                    code="ACTIVE_REVIEW_EXISTS",
                    message="合同存在正在处理的审核任务，暂不能归档。",
                )
            contract.status = "archived"
            contract.archived_at = _now()
            contract.version += 1
            append_audit_log(
                session,
                actor=actor,
                action="contract.archived",
                resource_type="contract",
                resource_id=contract.id,
                request_id=request_id,
                before={"status": "active"},
                after={
                    "status": contract.status,
                    "archived_at": contract.archived_at.isoformat(),
                },
            )
        unit_of_work.commit()
    return contract


def restore_contract(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    request_id: str,
) -> Contract:
    with UnitOfWork(session) as unit_of_work:
        contract = _contract_or_not_found(
            session,
            organization_id=actor.organization_id,
            contract_id=contract_id,
            for_update=True,
        )
        if contract.status != "archived":
            raise ApplicationError(
                status_code=409,
                code="CONTRACT_NOT_ARCHIVED",
                message="合同当前未归档。",
            )
        contract.status = "active"
        contract.archived_at = None
        contract.version += 1
        append_audit_log(
            session,
            actor=actor,
            action="contract.restored",
            resource_type="contract",
            resource_id=contract.id,
            request_id=request_id,
            before={"status": "archived"},
            after={"status": contract.status, "archived_at": None},
        )
        unit_of_work.commit()
    return contract


def _target_member(
    session: Session, *, organization_id: UUID, user_id: UUID
) -> OrganizationMembership | None:
    return session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )


def _validate_access_target(
    session: Session, *, organization_id: UUID, user_id: UUID, require_viewer: bool
) -> OrganizationMembership:
    user = session.get(User, user_id)
    if user is None:
        raise ApplicationError(
            status_code=404,
            code="CONTRACT_OR_USER_NOT_FOUND",
            message="合同或用户不存在。",
        )
    membership = _target_member(session, organization_id=organization_id, user_id=user_id)
    if membership is None:
        raise ApplicationError(
            status_code=409,
            code="CROSS_ORGANIZATION_ACCESS",
            message="用户不属于当前组织。",
        )
    if require_viewer and (membership.status != "active" or membership.role != "viewer"):
        raise ApplicationError(
            status_code=404,
            code="CONTRACT_OR_USER_NOT_FOUND",
            message="合同或用户不存在。",
        )
    return membership


def grant_contract_access(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    user_id: UUID,
    body: ContractAccessGrantRequest,
    request_id: str,
) -> ContractAccessGrant:
    with UnitOfWork(session) as unit_of_work:
        contract = _contract_or_not_found(
            session,
            organization_id=actor.organization_id,
            contract_id=contract_id,
            for_update=True,
        )
        _validate_access_target(
            session,
            organization_id=actor.organization_id,
            user_id=user_id,
            require_viewer=True,
        )
        grant = session.scalar(
            select(ContractAccessGrant)
            .where(
                ContractAccessGrant.organization_id == actor.organization_id,
                ContractAccessGrant.contract_id == contract.id,
                ContractAccessGrant.user_id == user_id,
            )
            .with_for_update()
        )
        if grant is None:
            grant = ContractAccessGrant(
                organization_id=actor.organization_id,
                contract_id=contract.id,
                user_id=user_id,
                access_level=body.access_level,
            )
            session.add(grant)
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="contract.access_granted",
                resource_type="contract_access_grant",
                resource_id=grant.id,
                request_id=request_id,
                after={
                    "contract_id": str(contract.id),
                    "user_id": str(user_id),
                    "access_level": grant.access_level,
                },
            )
        elif grant.access_level != body.access_level:
            grant.access_level = body.access_level
        unit_of_work.commit()
    return grant


def revoke_contract_access(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    user_id: UUID,
    request_id: str,
) -> None:
    with UnitOfWork(session) as unit_of_work:
        contract = _contract_or_not_found(
            session,
            organization_id=actor.organization_id,
            contract_id=contract_id,
            for_update=True,
        )
        _validate_access_target(
            session,
            organization_id=actor.organization_id,
            user_id=user_id,
            require_viewer=False,
        )
        grant = session.scalar(
            select(ContractAccessGrant)
            .where(
                ContractAccessGrant.organization_id == actor.organization_id,
                ContractAccessGrant.contract_id == contract.id,
                ContractAccessGrant.user_id == user_id,
            )
            .with_for_update()
        )
        if grant is not None:
            session.delete(grant)
            append_audit_log(
                session,
                actor=actor,
                action="contract.access_revoked",
                resource_type="contract_access_grant",
                resource_id=grant.id,
                request_id=request_id,
                before={
                    "contract_id": str(contract.id),
                    "user_id": str(user_id),
                    "access_level": grant.access_level,
                },
                after={"revoked": True},
            )
        unit_of_work.commit()
