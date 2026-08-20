from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.modules.identity.models import Organization
from backend.app.modules.risks.rules.models import RiskRule, RiskRuleBundle, RiskRuleBundleVersion
from backend.app.modules.risks.rules.schemas import (
    CreateRiskRuleBundleRequest,
    CreateRiskRuleVersionRequest,
    RiskRuleInput,
    UpdateRiskRuleBundleRequest,
    UpdateRiskRuleVersionRequest,
)
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

RiskBundleSort = Literal["created_at", "name"]


def _now() -> datetime:
    return datetime.now(UTC)


def _error(code: str, message: str, *, status_code: int = 409) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message)


def _bundle_not_found() -> ApplicationError:
    return _error("RULE_BUNDLE_NOT_FOUND", "风险规则集不存在。", status_code=404)


def _version_not_found() -> ApplicationError:
    return _error("RULE_VERSION_NOT_FOUND", "风险规则版本不存在。", status_code=404)


def _schema_error(message: str) -> ApplicationError:
    return _error("RULE_SCHEMA_INVALID", message, status_code=422)


def _normalized_name(value: str) -> str:
    return value.strip().lower()


def _condition_error(message: str) -> ApplicationError:
    return _schema_error(f"规则条件无效：{message}")


def _contains_semantic(condition: Mapping[str, Any], *, depth: int = 1) -> bool:
    if depth > 5:
        raise _condition_error("条件层级或结构不受支持。")
    operator = condition["operator"]
    if operator in {"all", "any"}:
        contains_semantic = False
        for child in condition["conditions"]:
            contains_semantic |= _contains_semantic(child, depth=depth + 1)
        return contains_semantic
    if operator == "not":
        return _contains_semantic(condition["condition"], depth=depth + 1)
    return bool(operator == "semantic")


def validate_rules(rules: list[RiskRuleInput]) -> None:
    if not 1 <= len(rules) <= 200:
        raise _schema_error("规则版本必须包含 1 到 200 条规则。")
    keys: set[str] = set()
    for rule in rules:
        if rule.rule_key in keys:
            raise _schema_error("同一版本中的 rule_key 必须唯一。")
        keys.add(rule.rule_key)
        condition = rule.condition.model_dump(mode="json")
        contains_semantic = _contains_semantic(condition)
        if rule.engine == "deterministic" and contains_semantic:
            raise _schema_error("deterministic 引擎不能使用 semantic 条件。")


def _rule_payload(rule: RiskRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "rule_key": rule.rule_key,
        "risk_type": rule.risk_type,
        "engine": rule.engine,
        "condition": rule.condition_json,
        "severity": rule.severity,
        "suggestion": rule.suggestion,
        "enabled": rule.enabled,
    }


def _bundle_payload(bundle: RiskRuleBundle) -> dict[str, Any]:
    return {
        "organization_id": bundle.organization_id,
        "id": bundle.id,
        "name": bundle.name,
        "status": bundle.status,
        "current_published_version_id": bundle.current_published_version_id,
        "is_default": bundle.is_default,
        "version": bundle.version,
    }


def _bundle_for_update(
    session: Session, *, organization_id: UUID, bundle_id: UUID
) -> RiskRuleBundle:
    bundle = session.scalar(
        select(RiskRuleBundle)
        .where(RiskRuleBundle.organization_id == organization_id, RiskRuleBundle.id == bundle_id)
        .with_for_update()
    )
    if bundle is None:
        raise _bundle_not_found()
    return bundle


def _bundle_or_not_found(
    session: Session, *, organization_id: UUID, bundle_id: UUID
) -> RiskRuleBundle:
    bundle = session.scalar(
        select(RiskRuleBundle).where(
            RiskRuleBundle.organization_id == organization_id,
            RiskRuleBundle.id == bundle_id,
        )
    )
    if bundle is None:
        raise _bundle_not_found()
    return bundle


def _version_for_update(
    session: Session, *, organization_id: UUID, version_id: UUID
) -> RiskRuleBundleVersion:
    version = session.scalar(
        select(RiskRuleBundleVersion)
        .where(
            RiskRuleBundleVersion.organization_id == organization_id,
            RiskRuleBundleVersion.id == version_id,
        )
        .with_for_update()
    )
    if version is None:
        raise _version_not_found()
    return version


def _version_or_not_found(
    session: Session, *, organization_id: UUID, version_id: UUID
) -> RiskRuleBundleVersion:
    version = session.scalar(
        select(RiskRuleBundleVersion).where(
            RiskRuleBundleVersion.organization_id == organization_id,
            RiskRuleBundleVersion.id == version_id,
        )
    )
    if version is None:
        raise _version_not_found()
    return version


def _rules(session: Session, *, organization_id: UUID, version_id: UUID) -> list[RiskRule]:
    return list(
        session.scalars(
            select(RiskRule)
            .where(
                RiskRule.organization_id == organization_id,
                RiskRule.bundle_version_id == version_id,
            )
            .order_by(RiskRule.rule_key, RiskRule.id)
        )
    )


def _version_payload(
    session: Session, version: RiskRuleBundleVersion, bundle: RiskRuleBundle
) -> dict[str, Any]:
    return {
        "organization_id": version.organization_id,
        "id": version.id,
        "bundle_id": version.bundle_id,
        "version_no": version.version_no,
        "status": version.status,
        "change_note": version.change_note,
        "effective_at": version.effective_at,
        "published_by": version.published_by,
        "version": version.version,
        "is_default": bundle.is_default,
        "current_published_version_id": bundle.current_published_version_id,
        "rules": [
            _rule_payload(rule)
            for rule in _rules(
                session, organization_id=version.organization_id, version_id=version.id
            )
        ],
    }


def _cursor_for_bundle(bundle: RiskRuleBundle) -> str:
    return encode_cursor(CursorPosition(created_at=bundle.created_at, id=bundle.id))


def list_bundles(
    session: Session,
    *,
    organization_id: UUID,
    role: str,
    status: Literal["active", "disabled"] | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> CursorPage[RiskRuleBundle]:
    if not 1 <= limit <= 100:
        raise ApplicationError(status_code=422, code="VALIDATION_ERROR", message="分页数量无效。")
    statement = select(RiskRuleBundle).where(RiskRuleBundle.organization_id == organization_id)
    if role == "reviewer":
        statement = statement.where(RiskRuleBundle.current_published_version_id.is_not(None))
    if status is not None:
        statement = statement.where(RiskRuleBundle.status == status)
    normalized_query = q.strip().lower() if q else ""
    if normalized_query:
        statement = statement.where(
            func.strpos(RiskRuleBundle.normalized_name, normalized_query) > 0
        )
    if cursor:
        try:
            position = decode_cursor(cursor)
        except ApplicationError as exc:
            raise InvalidCursorError from exc
        statement = statement.where(
            or_(
                RiskRuleBundle.created_at < position.created_at,
                and_(
                    RiskRuleBundle.created_at == position.created_at,
                    RiskRuleBundle.id < position.id,
                ),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(desc(RiskRuleBundle.created_at), desc(RiskRuleBundle.id)).limit(
                limit + 1
            )
        )
    )
    items = rows[:limit]
    return CursorPage(
        items=items,
        next_cursor=_cursor_for_bundle(items[-1]) if len(rows) > limit and items else None,
        has_more=len(rows) > limit,
    )


def _visible_versions(
    session: Session,
    bundle: RiskRuleBundle,
    *,
    role: str,
    include_rules: bool,
) -> list[dict[str, Any]]:
    statement = select(RiskRuleBundleVersion).where(
        RiskRuleBundleVersion.organization_id == bundle.organization_id,
        RiskRuleBundleVersion.bundle_id == bundle.id,
    )
    if role == "reviewer":
        statement = statement.where(RiskRuleBundleVersion.status == "published")
    versions = list(session.scalars(statement.order_by(RiskRuleBundleVersion.version_no.desc())))
    return [
        {
            "organization_id": version.organization_id,
            "id": version.id,
            "version_no": version.version_no,
            "status": version.status,
            "change_note": version.change_note,
            "effective_at": version.effective_at,
            "published_by": version.published_by,
            "rule_count": session.scalar(
                select(func.count(RiskRule.id)).where(
                    RiskRule.organization_id == bundle.organization_id,
                    RiskRule.bundle_version_id == version.id,
                )
            )
            or 0,
            **(
                {
                    "rules": [
                        _rule_payload(rule)
                        for rule in _rules(
                            session,
                            organization_id=bundle.organization_id,
                            version_id=version.id,
                        )
                    ]
                }
                if include_rules
                else {}
            ),
        }
        for version in versions
    ]


def bundle_detail(
    session: Session,
    *,
    bundle: RiskRuleBundle,
    role: str,
    include_rules: bool = False,
) -> dict[str, Any]:
    return {
        **_bundle_payload(bundle),
        "versions": _visible_versions(
            session,
            bundle,
            role=role,
            include_rules=include_rules,
        ),
    }


def create_bundle(
    session: Session,
    *,
    actor: TenantContext,
    body: CreateRiskRuleBundleRequest,
    idempotency_key: str,
    request_id: str,
) -> RiskRuleBundle:
    fingerprint = request_fingerprint(
        method="POST", operation_key="POST /api/v1/risk-rule-bundles", body=body.model_dump()
    )
    created: RiskRuleBundle | None = None
    with UnitOfWork(session) as unit_of_work:

        def operation() -> IdempotencyResult:
            nonlocal created
            bundle = RiskRuleBundle(
                id=uuid4(),
                organization_id=actor.organization_id,
                name=body.name,
                normalized_name=_normalized_name(body.name),
            )
            session.add(bundle)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _error("RULE_BUNDLE_NAME_CONFLICT", "规则集名称已存在。") from exc
            append_audit_log(
                session,
                actor=actor,
                action="risk_rule_bundle.created",
                resource_type="risk_rule_bundle",
                resource_id=bundle.id,
                request_id=request_id,
                after={
                    "name": bundle.name,
                    "status": bundle.status,
                    "is_default": bundle.is_default,
                },
            )
            created = bundle
            return IdempotencyResult(201, "risk_rule_bundle", bundle.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/risk-rule-bundles",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("risk rule bundle idempotency record has no resource")
            created = _bundle_or_not_found(
                session, organization_id=actor.organization_id, bundle_id=result.resource_id
            )
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("risk rule bundle creation returned no resource")
    return created


def update_bundle(
    session: Session,
    *,
    actor: TenantContext,
    bundle_id: UUID,
    body: UpdateRiskRuleBundleRequest,
    request_id: str,
) -> RiskRuleBundle:
    with UnitOfWork(session) as unit_of_work:
        session.scalar(
            select(Organization).where(Organization.id == actor.organization_id).with_for_update()
        )
        bundle = _bundle_for_update(
            session, organization_id=actor.organization_id, bundle_id=bundle_id
        )
        if bundle.version != body.version:
            raise _error("RESOURCE_VERSION_CONFLICT", "资源已被更新，请刷新后重试。")
        before: dict[str, Any] = {
            "name": bundle.name,
            "status": bundle.status,
            "is_default": bundle.is_default,
            "version": bundle.version,
        }
        if body.is_default is False and bundle.is_default:
            raise _error("DEFAULT_RULE_BUNDLE_REQUIRED", "当前默认规则集必须先切换后才能取消默认。")
        if body.status == "disabled" and bundle.is_default:
            raise _error("DEFAULT_RULE_BUNDLE_REQUIRED", "当前默认规则集必须先切换后才能停用。")
        switched_from: dict[str, Any] | None = None
        try:
            with session.begin_nested():
                if body.name is not None:
                    bundle.name = body.name
                    bundle.normalized_name = _normalized_name(body.name)
                if body.status is not None:
                    bundle.status = body.status
                if body.is_default:
                    if bundle.status != "active" or bundle.current_published_version_id is None:
                        raise _error(
                            "DEFAULT_RULE_BUNDLE_CONFLICT",
                            "只有 active 且已发布的规则集可以设为默认。",
                        )
                    previous = session.scalar(
                        select(RiskRuleBundle)
                        .where(
                            RiskRuleBundle.organization_id == actor.organization_id,
                            RiskRuleBundle.is_default.is_(True),
                            RiskRuleBundle.id != bundle.id,
                        )
                        .with_for_update()
                    )
                    if previous is not None:
                        switched_from = {
                            "bundle_id": str(previous.id),
                            "version": previous.version,
                        }
                        previous.is_default = False
                        previous.version += 1
                        session.flush()
                    bundle.is_default = True
                bundle.version += 1
                session.flush()
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name == "uq_risk_rule_bundles_default":
                raise _error(
                    "DEFAULT_RULE_BUNDLE_CONFLICT", "默认规则集已被其他请求更新，请重试。"
                ) from exc
            raise _error("RULE_BUNDLE_NAME_CONFLICT", "规则集名称已存在。") from exc
        after: dict[str, Any] = {
            "name": bundle.name,
            "status": bundle.status,
            "is_default": bundle.is_default,
            "version": bundle.version,
        }
        if body.is_default:
            before["organization_default_bundle_id"] = (
                switched_from["bundle_id"] if switched_from is not None else None
            )
            after["organization_default_bundle_id"] = str(bundle.id)
            if switched_from is not None:
                before["organization_default_bundle_version"] = switched_from["version"]
                after["previous_default_bundle_version"] = switched_from["version"] + 1
        append_audit_log(
            session,
            actor=actor,
            action="risk_rule_bundle.updated",
            resource_type="risk_rule_bundle",
            resource_id=bundle.id,
            request_id=request_id,
            before=before,
            after=after,
        )
        unit_of_work.commit()
    return bundle


def create_version(
    session: Session,
    *,
    actor: TenantContext,
    bundle_id: UUID,
    body: CreateRiskRuleVersionRequest,
    idempotency_key: str,
    request_id: str,
) -> RiskRuleBundleVersion:
    validate_rules(body.rules)
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/risk-rule-bundles/{bundle_id}/versions",
        path={"bundle_id": bundle_id},
        body=body.model_dump(mode="json"),
    )
    created: RiskRuleBundleVersion | None = None
    with UnitOfWork(session) as unit_of_work:

        def operation() -> IdempotencyResult:
            nonlocal created
            bundle = _bundle_for_update(
                session, organization_id=actor.organization_id, bundle_id=bundle_id
            )
            if bundle.status != "active":
                raise _error("RULE_BUNDLE_DISABLED", "停用的规则集不能创建新版本。")
            if body.source_version_id is not None:
                try:
                    source = _version_or_not_found(
                        session,
                        organization_id=actor.organization_id,
                        version_id=body.source_version_id,
                    )
                except ApplicationError as exc:
                    if exc.code != "RULE_VERSION_NOT_FOUND":
                        raise
                    raise _error(
                        "VERSION_SOURCE_INVALID",
                        "来源版本必须是同一规则集的已发布版本。",
                    ) from exc
                if source.bundle_id != bundle.id or source.status != "published":
                    raise _error("VERSION_SOURCE_INVALID", "来源版本必须是同一规则集的已发布版本。")
            next_no = (
                session.scalar(
                    select(func.max(RiskRuleBundleVersion.version_no)).where(
                        RiskRuleBundleVersion.organization_id == actor.organization_id,
                        RiskRuleBundleVersion.bundle_id == bundle.id,
                    )
                )
                or 0
            ) + 1
            version = RiskRuleBundleVersion(
                id=uuid4(),
                organization_id=actor.organization_id,
                bundle_id=bundle.id,
                version_no=next_no,
                change_note=body.change_note,
            )
            session.add(version)
            session.flush()
            session.add_all(
                [
                    RiskRule(
                        id=uuid4(),
                        organization_id=actor.organization_id,
                        bundle_version_id=version.id,
                        rule_key=rule.rule_key,
                        risk_type=rule.risk_type,
                        engine=rule.engine,
                        condition_json=rule.condition.model_dump(mode="json"),
                        severity=rule.severity,
                        suggestion=rule.suggestion,
                        enabled=rule.enabled,
                    )
                    for rule in body.rules
                ]
            )
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="risk_rule_version.created",
                resource_type="risk_rule_bundle_version",
                resource_id=version.id,
                request_id=request_id,
                after={
                    "bundle_id": str(bundle.id),
                    "version_no": version.version_no,
                    "status": version.status,
                },
            )
            created = version
            return IdempotencyResult(201, "risk_rule_bundle_version", version.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/risk-rule-bundles/{bundle_id}/versions",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("risk rule version idempotency record has no resource")
            created = _version_for_update(
                session, organization_id=actor.organization_id, version_id=result.resource_id
            )
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("risk rule version creation returned no resource")
    return created


def get_version(
    session: Session, *, organization_id: UUID, version_id: UUID, role: str
) -> dict[str, Any]:
    version = _version_or_not_found(session, organization_id=organization_id, version_id=version_id)
    if role == "reviewer" and version.status != "published":
        raise _error("FORBIDDEN", "审核员只能读取已发布的风险规则版本。", status_code=403)
    bundle = _bundle_or_not_found(
        session, organization_id=organization_id, bundle_id=version.bundle_id
    )
    return _version_payload(session, version, bundle)


def update_version(
    session: Session,
    *,
    actor: TenantContext,
    version_id: UUID,
    body: UpdateRiskRuleVersionRequest,
    request_id: str,
) -> RiskRuleBundleVersion:
    if body.rules is not None:
        validate_rules(body.rules)
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
        if body.rules is not None:
            session.query(RiskRule).filter(
                RiskRule.organization_id == actor.organization_id,
                RiskRule.bundle_version_id == version.id,
            ).delete(synchronize_session=False)
            session.add_all(
                [
                    RiskRule(
                        id=uuid4(),
                        organization_id=actor.organization_id,
                        bundle_version_id=version.id,
                        rule_key=rule.rule_key,
                        risk_type=rule.risk_type,
                        engine=rule.engine,
                        condition_json=rule.condition.model_dump(mode="json"),
                        severity=rule.severity,
                        suggestion=rule.suggestion,
                        enabled=rule.enabled,
                    )
                    for rule in body.rules
                ]
            )
        version.version += 1
        session.flush()
        append_audit_log(
            session,
            actor=actor,
            action="risk_rule_version.updated",
            resource_type="risk_rule_bundle_version",
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
        bundle = _bundle_for_update(
            session, organization_id=actor.organization_id, bundle_id=version.bundle_id
        )
        if version.status != "draft":
            raise _error("VERSION_NOT_DRAFT", "只有草稿版本可以发布。")
        if bundle.status != "active":
            raise _error("RULE_BUNDLE_DISABLED", "停用的规则集不能发布新版本。")
        rules = _rules(session, organization_id=actor.organization_id, version_id=version.id)
        try:
            validated_rules = [
                RiskRuleInput(
                    rule_key=rule.rule_key,
                    risk_type=rule.risk_type,
                    engine=rule.engine,
                    condition=rule.condition_json,
                    severity=rule.severity,
                    suggestion=rule.suggestion,
                    enabled=rule.enabled,
                )
                for rule in rules
            ]
        except ValidationError as exc:
            raise _schema_error("规则版本未通过白名单 Schema 校验。") from exc
        validate_rules(validated_rules)
        version.status = "published"
        version.effective_at = _now()
        version.published_by = actor.user_id
        version.version += 1
        bundle.current_published_version_id = version.id
        if (
            session.scalar(
                select(RiskRuleBundle.id).where(
                    RiskRuleBundle.organization_id == actor.organization_id,
                    RiskRuleBundle.is_default.is_(True),
                )
            )
            is None
        ):
            bundle.is_default = True
        bundle.version += 1
        try:
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="risk_rule_version.published",
                resource_type="risk_rule_bundle_version",
                resource_id=version.id,
                request_id=request_id,
                after={
                    "bundle_id": str(bundle.id),
                    "status": version.status,
                    "is_default": bundle.is_default,
                    "effective_at": version.effective_at.isoformat()
                    if version.effective_at is not None
                    else None,
                },
            )
            unit_of_work.commit()
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name == "uq_risk_rule_bundles_default":
                raise _error(
                    "DEFAULT_RULE_BUNDLE_CONFLICT", "默认规则集已被其他请求更新，请重试。"
                ) from exc
            raise
    return _version_payload(session, version, bundle)


def install_risk_rule_baseline(
    session: Session,
    *,
    organization_id: UUID,
    request_id: str = "system-risk-rule-baseline",
) -> None:
    if (
        session.scalar(
            select(RiskRuleBundle.id).where(RiskRuleBundle.organization_id == organization_id)
        )
        is not None
    ):
        return
    bundle = RiskRuleBundle(
        id=uuid4(),
        organization_id=organization_id,
        name="内置风险规则基线",
        normalized_name="内置风险规则基线",
        status="active",
        is_default=False,
    )
    session.add(bundle)
    session.flush()
    version = RiskRuleBundleVersion(
        id=uuid4(),
        organization_id=organization_id,
        bundle_id=bundle.id,
        version_no=1,
        status="draft",
        change_note="系统内置演示基线，不代表具体企业法律意见。",
    )
    session.add(version)
    session.flush()
    baseline = [
        (
            "unlimited_liability",
            "unlimited_liability",
            "无限责任或责任范围不封顶",
            "high",
            {"operator": "keyword", "field": "contract_text", "value": "无限责任"},
        ),
        (
            "excessive_liquidated_damages",
            "excessive_liquidated_damages",
            "违约金计算方式不合理",
            "high",
            {"operator": "keyword", "field": "contract_text", "value": "违约金"},
        ),
        (
            "unilateral_termination",
            "unilateral_termination",
            "单方解除或变更权不对等",
            "high",
            {"operator": "keyword", "field": "contract_text", "value": "单方解除"},
        ),
        (
            "unclear_payment",
            "unclear_payment",
            "付款条件不清晰或周期过长",
            "medium",
            {"operator": "field_missing", "field": "payment_terms"},
        ),
        (
            "missing_acceptance",
            "missing_acceptance",
            "验收标准缺失",
            "high",
            {"operator": "field_missing", "field": "acceptance_standard"},
        ),
        (
            "broad_confidentiality",
            "broad_confidentiality",
            "保密义务范围过宽",
            "medium",
            {"operator": "keyword", "field": "contract_text", "value": "永久保密"},
        ),
        (
            "unclear_ip",
            "unclear_ip",
            "知识产权归属不清",
            "high",
            {"operator": "field_missing", "field": "intellectual_property"},
        ),
        (
            "data_compliance",
            "data_compliance",
            "数据合规责任缺失",
            "high",
            {"operator": "field_missing", "field": "data_compliance"},
        ),
        (
            "unfavorable_dispute",
            "unfavorable_dispute",
            "争议解决安排可能不利",
            "medium",
            {"operator": "field_missing", "field": "dispute_resolution"},
        ),
        (
            "auto_renewal",
            "auto_renewal",
            "自动续期或隐性义务",
            "medium",
            {"operator": "keyword", "field": "contract_text", "value": "自动续期"},
        ),
        (
            "force_majeure",
            "force_majeure",
            "不可抗力或迟延履行条款缺失",
            "low",
            {"operator": "field_missing", "field": "force_majeure"},
        ),
    ]
    session.add_all(
        [
            RiskRule(
                id=uuid4(),
                organization_id=organization_id,
                bundle_version_id=version.id,
                rule_key=rule_key,
                risk_type=risk_type,
                engine="deterministic",
                condition_json=condition,
                severity=severity,
                suggestion=f"请复核“{title}”相关约定，并结合组织政策确认。",
                enabled=True,
            )
            for rule_key, risk_type, title, severity, condition in baseline
        ]
    )
    session.flush()
    version.status = "published"
    version.effective_at = _now()
    bundle.current_published_version_id = version.id
    bundle.is_default = True
    session.flush()
    append_audit_log(
        session,
        actor=None,
        organization_id=organization_id,
        action="risk_rule_version.published",
        resource_type="risk_rule_bundle_version",
        resource_id=version.id,
        request_id=request_id,
        after={
            "bundle_id": str(bundle.id),
            "status": version.status,
            "is_default": bundle.is_default,
            "effective_at": version.effective_at.isoformat(),
            "source": "system_baseline",
        },
    )
