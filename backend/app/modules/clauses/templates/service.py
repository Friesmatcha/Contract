from collections.abc import Mapping
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.modules.clauses.templates.models import (
    ClauseTemplate,
    ClauseTemplateVersion,
    StandardClause,
)
from backend.app.modules.clauses.templates.schemas import (
    CreateClauseTemplateRequest,
    CreateClauseTemplateVersionRequest,
    StandardClauseInput,
    UpdateClauseTemplateRequest,
    UpdateClauseTemplateVersionRequest,
)
from backend.app.modules.identity.models import Organization
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, InvalidCursorError
from backend.app.shared.idempotency import (
    IdempotencyResult,
    execute_idempotent,
    organization_scope,
    request_fingerprint,
)
from backend.app.shared.pagination import CursorPage, CursorPosition, decode_cursor, encode_cursor
from backend.app.shared.tenant import TenantContext

ClauseTemplateSort = Literal["created_at", "name"]


def _now() -> datetime:
    return datetime.now(UTC)


def _error(code: str, message: str, *, status_code: int = 409) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message)


def _template_not_found() -> ApplicationError:
    return _error("TEMPLATE_NOT_FOUND", "条款模板不存在。", status_code=404)


def _version_not_found() -> ApplicationError:
    return _error("TEMPLATE_VERSION_NOT_FOUND", "条款模板版本不存在。", status_code=404)


def _schema_error(message: str) -> ApplicationError:
    return _error("CLAUSE_SCHEMA_INVALID", message, status_code=422)


def normalize_business_scenario(value: str | None) -> str:
    normalized = value.strip().lower() if value is not None else ""
    return normalized or "standard"


def _normalized_name(value: str) -> str:
    return value.strip().lower()


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 3:
        raise _schema_error("适用条件嵌套层级过深。")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise _schema_error("适用条件不能包含非有限数字。")
        return
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise _schema_error("适用条件字段过多。")
        for key, item in value.items():
            if not isinstance(key, str) or not 0 < len(key.strip()) <= 128:
                raise _schema_error("适用条件字段名无效。")
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 32:
            raise _schema_error("适用条件列表过长。")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    raise _schema_error("适用条件只能是 JSON 对象。")


def validate_clauses(clauses: list[StandardClauseInput], *, require_nonempty: bool = False) -> None:
    if require_nonempty and not clauses:
        raise _schema_error("发布版本至少需要一条标准条款。")
    keys: set[str] = set()
    orders: set[int] = set()
    for clause in clauses:
        if clause.clause_key in keys:
            raise _schema_error("同一版本中的 clause_key 必须唯一。")
        if clause.order_no in orders:
            raise _schema_error("同一版本中的 order_no 必须唯一。")
        keys.add(clause.clause_key)
        orders.add(clause.order_no)
        _validate_json_value(clause.applicability)


def _clause_payload(clause: StandardClause) -> dict[str, Any]:
    return {
        "id": clause.id,
        "clause_key": clause.clause_key,
        "name": clause.name,
        "standard_text": clause.standard_text,
        "allowed_deviation": clause.allowed_deviation,
        "severity": clause.severity,
        "applicability": clause.applicability_json,
        "suggestion": clause.suggestion,
        "enabled": clause.enabled,
        "order_no": clause.order_no,
    }


def _template_payload(template: ClauseTemplate) -> dict[str, Any]:
    return {
        "organization_id": template.organization_id,
        "id": template.id,
        "name": template.name,
        "contract_type": template.contract_type,
        "business_scenario": template.business_scenario,
        "status": template.status,
        "current_published_version_id": template.current_published_version_id,
        "is_default": template.is_default,
        "version": template.version,
    }


def _template_for_update(
    session: Session, *, organization_id: UUID, template_id: UUID
) -> ClauseTemplate:
    template = session.scalar(
        select(ClauseTemplate)
        .where(
            ClauseTemplate.organization_id == organization_id,
            ClauseTemplate.id == template_id,
        )
        .with_for_update()
    )
    if template is None:
        raise _template_not_found()
    return template


def _template_or_not_found(
    session: Session, *, organization_id: UUID, template_id: UUID
) -> ClauseTemplate:
    template = session.scalar(
        select(ClauseTemplate).where(
            ClauseTemplate.organization_id == organization_id,
            ClauseTemplate.id == template_id,
        )
    )
    if template is None:
        raise _template_not_found()
    return template


def _version_for_update(
    session: Session, *, organization_id: UUID, version_id: UUID
) -> ClauseTemplateVersion:
    version = session.scalar(
        select(ClauseTemplateVersion)
        .where(
            ClauseTemplateVersion.organization_id == organization_id,
            ClauseTemplateVersion.id == version_id,
        )
        .with_for_update()
    )
    if version is None:
        raise _version_not_found()
    return version


def _version_or_not_found(
    session: Session, *, organization_id: UUID, version_id: UUID
) -> ClauseTemplateVersion:
    version = session.scalar(
        select(ClauseTemplateVersion).where(
            ClauseTemplateVersion.organization_id == organization_id,
            ClauseTemplateVersion.id == version_id,
        )
    )
    if version is None:
        raise _version_not_found()
    return version


def _clauses(session: Session, *, organization_id: UUID, version_id: UUID) -> list[StandardClause]:
    return list(
        session.scalars(
            select(StandardClause)
            .where(
                StandardClause.organization_id == organization_id,
                StandardClause.template_version_id == version_id,
            )
            .order_by(StandardClause.order_no, StandardClause.id)
        )
    )


def _clause_inputs(
    session: Session, *, organization_id: UUID, version_id: UUID
) -> list[StandardClauseInput]:
    try:
        return [
            StandardClauseInput(
                clause_key=clause.clause_key,
                name=clause.name,
                standard_text=clause.standard_text,
                allowed_deviation=clause.allowed_deviation,
                severity=clause.severity,
                applicability=clause.applicability_json,
                suggestion=clause.suggestion,
                enabled=clause.enabled,
                order_no=clause.order_no,
            )
            for clause in _clauses(
                session, organization_id=organization_id, version_id=version_id
            )
        ]
    except ValidationError as exc:
        raise _schema_error("模板版本未通过标准条款 Schema 校验。") from exc


def _version_payload(
    session: Session,
    version: ClauseTemplateVersion,
    template: ClauseTemplate,
) -> dict[str, Any]:
    return {
        "organization_id": version.organization_id,
        "id": version.id,
        "template_id": version.template_id,
        "version_no": version.version_no,
        "status": version.status,
        "change_note": version.change_note,
        "effective_at": version.effective_at,
        "published_by": version.published_by,
        "version": version.version,
        "is_default": template.is_default,
        "current_published_version_id": template.current_published_version_id,
        "clauses": [_clause_payload(clause) for clause in _clauses(
            session, organization_id=version.organization_id, version_id=version.id
        )],
    }


def _cursor_for_template(template: ClauseTemplate) -> str:
    return encode_cursor(CursorPosition(created_at=template.created_at, id=template.id))


def list_templates(
    session: Session,
    *,
    organization_id: UUID,
    role: str,
    contract_type: str | None,
    business_scenario: str | None,
    status: Literal["active", "disabled"] | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> CursorPage[ClauseTemplate]:
    if not 1 <= limit <= 100:
        raise _error("VALIDATION_ERROR", "分页数量无效。", status_code=422)
    statement = select(ClauseTemplate).where(ClauseTemplate.organization_id == organization_id)
    if role == "reviewer":
        statement = statement.where(ClauseTemplate.current_published_version_id.is_not(None))
    if contract_type is not None:
        statement = statement.where(ClauseTemplate.contract_type == contract_type)
    if business_scenario is not None:
        statement = statement.where(
            ClauseTemplate.business_scenario == normalize_business_scenario(business_scenario)
        )
    if status is not None:
        statement = statement.where(ClauseTemplate.status == status)
    normalized_query = q.strip().lower() if q else ""
    if normalized_query:
        statement = statement.where(
            func.strpos(ClauseTemplate.normalized_name, normalized_query) > 0
        )
    if cursor:
        try:
            position = decode_cursor(cursor)
        except ApplicationError as exc:
            raise InvalidCursorError from exc
        statement = statement.where(
            or_(
                ClauseTemplate.created_at < position.created_at,
                and_(
                    ClauseTemplate.created_at == position.created_at,
                    ClauseTemplate.id < position.id,
                ),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(desc(ClauseTemplate.created_at), desc(ClauseTemplate.id)).limit(
                limit + 1
            )
        )
    )
    items = rows[:limit]
    return CursorPage(
        items=items,
        next_cursor=_cursor_for_template(items[-1]) if len(rows) > limit and items else None,
        has_more=len(rows) > limit,
    )


def _visible_versions(
    session: Session,
    template: ClauseTemplate,
    *,
    role: str,
    include_clauses: bool,
) -> list[dict[str, Any]]:
    statement = select(ClauseTemplateVersion).where(
        ClauseTemplateVersion.organization_id == template.organization_id,
        ClauseTemplateVersion.template_id == template.id,
    )
    if role == "reviewer":
        statement = statement.where(ClauseTemplateVersion.status == "published")
    versions = list(session.scalars(statement.order_by(ClauseTemplateVersion.version_no.desc())))
    return [
        {
            "organization_id": version.organization_id,
            "id": version.id,
            "version_no": version.version_no,
            "status": version.status,
            "change_note": version.change_note,
            "effective_at": version.effective_at,
            "published_by": version.published_by,
            **(
                {
                    "clauses": [
                        _clause_payload(clause)
                        for clause in _clauses(
                            session,
                            organization_id=template.organization_id,
                            version_id=version.id,
                        )
                    ]
                }
                if include_clauses
                else {}
            ),
        }
        for version in versions
    ]


def template_detail(
    session: Session,
    *,
    template: ClauseTemplate,
    role: str,
    include_clauses: bool = False,
) -> dict[str, Any]:
    return {
        **_template_payload(template),
        "versions": _visible_versions(
            session,
            template,
            role=role,
            include_clauses=include_clauses,
        ),
    }


def create_template(
    session: Session,
    *,
    actor: TenantContext,
    body: CreateClauseTemplateRequest,
    idempotency_key: str,
    request_id: str,
) -> ClauseTemplate:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/clause-templates",
        body=body.model_dump(),
    )
    created: ClauseTemplate | None = None
    with UnitOfWork(session) as unit_of_work:

        def operation() -> IdempotencyResult:
            nonlocal created
            template = ClauseTemplate(
                id=uuid4(),
                organization_id=actor.organization_id,
                name=body.name,
                normalized_name=_normalized_name(body.name),
                contract_type=body.contract_type,
                business_scenario=normalize_business_scenario(body.business_scenario),
            )
            session.add(template)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _error("TEMPLATE_NAME_CONFLICT", "条款模板名称已存在。") from exc
            append_audit_log(
                session,
                actor=actor,
                action="clause_template.created",
                resource_type="clause_template",
                resource_id=template.id,
                request_id=request_id,
                after={
                    "name": template.name,
                    "contract_type": template.contract_type,
                    "business_scenario": template.business_scenario,
                    "status": template.status,
                },
            )
            created = template
            return IdempotencyResult(201, "clause_template", template.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/clause-templates",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("clause template idempotency record has no resource")
            created = _template_or_not_found(
                session, organization_id=actor.organization_id, template_id=result.resource_id
            )
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("clause template creation returned no resource")
    return created


def update_template(
    session: Session,
    *,
    actor: TenantContext,
    template_id: UUID,
    body: UpdateClauseTemplateRequest,
    request_id: str,
) -> ClauseTemplate:
    with UnitOfWork(session) as unit_of_work:
        session.scalar(
            select(Organization).where(Organization.id == actor.organization_id).with_for_update()
        )
        template = _template_for_update(
            session, organization_id=actor.organization_id, template_id=template_id
        )
        if template.version != body.version:
            raise _error("RESOURCE_VERSION_CONFLICT", "资源已被更新，请刷新后重试。")
        before: dict[str, Any] = {
            "name": template.name,
            "business_scenario": template.business_scenario,
            "status": template.status,
            "is_default": template.is_default,
            "version": template.version,
        }
        if body.is_default is False and template.is_default:
            raise _error(
                "DEFAULT_CLAUSE_TEMPLATE_REQUIRED", "当前默认模板必须先切换后才能取消默认。"
            )
        if body.status == "disabled" and template.is_default:
            raise _error(
                "DEFAULT_CLAUSE_TEMPLATE_REQUIRED", "当前默认模板必须先切换后才能停用。"
            )
        if body.business_scenario is not None and normalize_business_scenario(
            body.business_scenario
        ) != template.business_scenario and template.is_default:
            raise _error(
                "DEFAULT_CLAUSE_TEMPLATE_REQUIRED", "当前默认模板必须先切换后才能修改场景。"
            )

        switched_from: dict[str, Any] | None = None
        try:
            with session.begin_nested():
                if body.name is not None:
                    template.name = body.name
                    template.normalized_name = _normalized_name(body.name)
                if body.business_scenario is not None:
                    template.business_scenario = normalize_business_scenario(body.business_scenario)
                if body.status is not None:
                    template.status = body.status
                if body.is_default:
                    if template.status != "active" or template.current_published_version_id is None:
                        raise _error(
                            "DEFAULT_CLAUSE_TEMPLATE_CONFLICT",
                            "只有 active 且已发布的模板可以设为默认。",
                        )
                    previous = session.scalar(
                        select(ClauseTemplate)
                        .where(
                            ClauseTemplate.organization_id == actor.organization_id,
                            ClauseTemplate.contract_type == template.contract_type,
                            ClauseTemplate.business_scenario == template.business_scenario,
                            ClauseTemplate.is_default.is_(True),
                            ClauseTemplate.id != template.id,
                        )
                        .with_for_update()
                    )
                    if previous is not None:
                        switched_from = {
                            "template_id": str(previous.id),
                            "version": previous.version,
                        }
                        previous.is_default = False
                        previous.version += 1
                        session.flush()
                    template.is_default = True
                template.version += 1
                session.flush()
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name == "uq_clause_templates_default":
                raise _error(
                    "DEFAULT_CLAUSE_TEMPLATE_CONFLICT", "默认模板已被其他请求更新，请重试。"
                ) from exc
            raise _error("TEMPLATE_NAME_CONFLICT", "条款模板名称已存在。") from exc
        after: dict[str, Any] = {
            "name": template.name,
            "business_scenario": template.business_scenario,
            "status": template.status,
            "is_default": template.is_default,
            "version": template.version,
        }
        if body.is_default:
            before["organization_default_template_id"] = (
                switched_from["template_id"] if switched_from is not None else None
            )
            after["organization_default_template_id"] = str(template.id)
            if switched_from is not None:
                before["previous_default_template_version"] = switched_from["version"]
                after["previous_default_template_version"] = switched_from["version"] + 1
        append_audit_log(
            session,
            actor=actor,
            action="clause_template.updated",
            resource_type="clause_template",
            resource_id=template.id,
            request_id=request_id,
            before=before,
            after=after,
        )
        unit_of_work.commit()
    return template


def create_version(
    session: Session,
    *,
    actor: TenantContext,
    template_id: UUID,
    body: CreateClauseTemplateVersionRequest,
    idempotency_key: str,
    request_id: str,
) -> ClauseTemplateVersion:
    validate_clauses(body.clauses)
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/clause-templates/{template_id}/versions",
        path={"template_id": template_id},
        body=body.model_dump(mode="json"),
    )
    created: ClauseTemplateVersion | None = None
    with UnitOfWork(session) as unit_of_work:

        def operation() -> IdempotencyResult:
            nonlocal created
            template = _template_for_update(
                session, organization_id=actor.organization_id, template_id=template_id
            )
            if template.status != "active":
                raise _error("TEMPLATE_DISABLED", "停用的模板不能创建新版本。")
            if body.source_version_id is not None:
                try:
                    source = _version_or_not_found(
                        session,
                        organization_id=actor.organization_id,
                        version_id=body.source_version_id,
                    )
                except ApplicationError as exc:
                    if exc.code != "TEMPLATE_VERSION_NOT_FOUND":
                        raise
                    raise _error(
                        "VERSION_SOURCE_INVALID", "来源版本必须是同一模板的已发布版本。"
                    ) from exc
                if source.template_id != template.id or source.status != "published":
                    raise _error("VERSION_SOURCE_INVALID", "来源版本必须是同一模板的已发布版本。")
            next_no = (
                session.scalar(
                    select(func.max(ClauseTemplateVersion.version_no)).where(
                        ClauseTemplateVersion.organization_id == actor.organization_id,
                        ClauseTemplateVersion.template_id == template.id,
                    )
                )
                or 0
            ) + 1
            version = ClauseTemplateVersion(
                id=uuid4(),
                organization_id=actor.organization_id,
                template_id=template.id,
                version_no=next_no,
                change_note=body.change_note,
            )
            session.add(version)
            session.flush()
            session.add_all(
                [
                    StandardClause(
                        id=uuid4(),
                        organization_id=actor.organization_id,
                        template_version_id=version.id,
                        clause_key=clause.clause_key,
                        name=clause.name,
                        standard_text=clause.standard_text,
                        allowed_deviation=clause.allowed_deviation,
                        severity=clause.severity,
                        applicability_json=clause.applicability,
                        suggestion=clause.suggestion,
                        enabled=clause.enabled,
                        order_no=clause.order_no,
                    )
                    for clause in body.clauses
                ]
            )
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="clause_template_version.created",
                resource_type="clause_template_version",
                resource_id=version.id,
                request_id=request_id,
                after={
                    "template_id": str(template.id),
                    "version_no": version.version_no,
                    "status": version.status,
                    "clause_count": len(body.clauses),
                },
            )
            created = version
            return IdempotencyResult(201, "clause_template_version", version.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/clause-templates/{template_id}/versions",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("clause template version idempotency record has no resource")
            created = _version_for_update(
                session, organization_id=actor.organization_id, version_id=result.resource_id
            )
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("clause template version creation returned no resource")
    return created


def get_version(
    session: Session, *, organization_id: UUID, version_id: UUID, role: str
) -> dict[str, Any]:
    version = _version_or_not_found(session, organization_id=organization_id, version_id=version_id)
    if role == "reviewer" and version.status != "published":
        raise _error("FORBIDDEN", "审核员只能读取已发布的条款模板版本。", status_code=403)
    template = _template_or_not_found(
        session, organization_id=organization_id, template_id=version.template_id
    )
    return _version_payload(session, version, template)


def update_version(
    session: Session,
    *,
    actor: TenantContext,
    version_id: UUID,
    body: UpdateClauseTemplateVersionRequest,
    request_id: str,
) -> ClauseTemplateVersion:
    if body.clauses is not None:
        validate_clauses(body.clauses)
    with UnitOfWork(session) as unit_of_work:
        version = _version_for_update(
            session, organization_id=actor.organization_id, version_id=version_id
        )
        if version.status != "draft":
            raise _error("VERSION_ALREADY_PUBLISHED", "已发布版本不可编辑。")
        if version.version != body.version:
            raise _error("RESOURCE_VERSION_CONFLICT", "资源已被更新，请刷新后重试。")
        if body.change_note is not None:
            version.change_note = body.change_note
        if body.clauses is not None:
            session.query(StandardClause).filter(
                StandardClause.organization_id == actor.organization_id,
                StandardClause.template_version_id == version.id,
            ).delete(synchronize_session=False)
            session.add_all(
                [
                    StandardClause(
                        id=uuid4(),
                        organization_id=actor.organization_id,
                        template_version_id=version.id,
                        clause_key=clause.clause_key,
                        name=clause.name,
                        standard_text=clause.standard_text,
                        allowed_deviation=clause.allowed_deviation,
                        severity=clause.severity,
                        applicability_json=clause.applicability,
                        suggestion=clause.suggestion,
                        enabled=clause.enabled,
                        order_no=clause.order_no,
                    )
                    for clause in body.clauses
                ]
            )
        version.version += 1
        session.flush()
        append_audit_log(
            session,
            actor=actor,
            action="clause_template_version.updated",
            resource_type="clause_template_version",
            resource_id=version.id,
            request_id=request_id,
            after={
                "version_no": version.version_no,
                "status": version.status,
                "resource_version": version.version,
            },
        )
        unit_of_work.commit()
    return version


def publish_version(
    session: Session,
    *,
    actor: TenantContext,
    version_id: UUID,
    request_id: str,
) -> dict[str, Any]:
    with UnitOfWork(session) as unit_of_work:
        session.scalar(
            select(Organization).where(Organization.id == actor.organization_id).with_for_update()
        )
        version = _version_for_update(
            session, organization_id=actor.organization_id, version_id=version_id
        )
        template = _template_for_update(
            session, organization_id=actor.organization_id, template_id=version.template_id
        )
        if version.status != "draft":
            raise _error("VERSION_NOT_DRAFT", "只有草稿版本可以发布。")
        if template.status != "active":
            raise _error("TEMPLATE_DISABLED", "停用的模板不能发布新版本。")
        clauses = _clause_inputs(
            session, organization_id=actor.organization_id, version_id=version.id
        )
        validate_clauses(clauses, require_nonempty=True)
        version.status = "published"
        version.effective_at = _now()
        version.published_by = actor.user_id
        version.version += 1
        template.current_published_version_id = version.id
        if (
            session.scalar(
                select(ClauseTemplate.id).where(
                    ClauseTemplate.organization_id == actor.organization_id,
                    ClauseTemplate.contract_type == template.contract_type,
                    ClauseTemplate.business_scenario == template.business_scenario,
                    ClauseTemplate.is_default.is_(True),
                )
            )
            is None
        ):
            template.is_default = True
        template.version += 1
        try:
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="clause_template_version.published",
                resource_type="clause_template_version",
                resource_id=version.id,
                request_id=request_id,
                after={
                    "template_id": str(template.id),
                    "contract_type": template.contract_type,
                    "business_scenario": template.business_scenario,
                    "status": version.status,
                    "is_default": template.is_default,
                    "effective_at": version.effective_at.isoformat()
                    if version.effective_at is not None
                    else None,
                },
            )
            unit_of_work.commit()
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name == "uq_clause_templates_default":
                raise _error(
                    "DEFAULT_CLAUSE_TEMPLATE_CONFLICT", "默认模板已被其他请求更新，请重试。"
                ) from exc
            raise
    return _version_payload(session, version, template)
