import base64
import binascii
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.orm import Session

from backend.app.integrations.notifications.in_app import create_warning_notifications
from backend.app.modules.contracts.models import Contract, ContractAccessGrant
from backend.app.modules.documents.models import DocumentVersion
from backend.app.modules.identity.models import Organization, OrganizationMembership
from backend.app.modules.identity.organization import organization_settings
from backend.app.modules.reviews.models import ReviewTask
from backend.app.modules.reviews.results.models import (
    ClauseComparison,
    ClauseComparisonEvidence,
    ContractClassification,
    ContractClassificationEvidence,
    ExtractedField,
    ExtractedFieldEvidence,
    RiskFinding,
    RiskFindingEvidence,
)
from backend.app.modules.reviews.results.service import _source_locator_payload
from backend.app.modules.warnings.models import (
    Notification,
    Warning,
    WarningEvent,
)
from backend.app.modules.warnings.schemas import (
    NotificationListQuery,
    WarningEventRequest,
    WarningListQuery,
)
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, ForbiddenError, InvalidCursorError
from backend.app.shared.tenant import TenantContext

_ACTIVE_WARNING_STATUSES = ("pending_confirmation", "in_progress", "resolved")
_WARNING_PRIORITY = {"high": 0, "medium": 1, "low": 2}
_EVENT_STATUS: dict[str, tuple[str, str]] = {
    "confirm": ("pending_confirmation", "in_progress"),
    "false_positive": ("pending_confirmation", "ignored"),
    "ignore": ("pending_confirmation", "ignored"),
    "resolve": ("in_progress", "resolved"),
    "close": ("resolved", "closed"),
    "reopen": ("ignored", "in_progress"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _error(code: str, message: str, *, status_code: int = 409) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message)


def _warning_or_not_found(
    session: Session, *, organization_id: UUID, warning_id: UUID, for_update: bool = False
) -> Warning:
    statement = select(Warning).where(
        Warning.organization_id == organization_id, Warning.id == warning_id
    )
    if for_update:
        statement = statement.with_for_update()
    warning = session.scalar(statement)
    if warning is None:
        raise ApplicationError(status_code=404, code="WARNING_NOT_FOUND", message="预警不存在。")
    return warning


def _safe_cursor_payload(sort: str, value: Any, item_id: UUID) -> str:
    payload = {"sort": sort, "value": value, "id": str(item_id), "v": 1}
    return (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def _decode_warning_cursor(value: str, sort: str) -> tuple[Any, UUID]:
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding))
        if payload.get("v") != 1 or payload.get("sort") != sort:
            raise ValueError
        return payload["value"], UUID(payload["id"])
    except (binascii.Error, UnicodeDecodeError, TypeError, ValueError, KeyError) as exc:
        raise InvalidCursorError from exc


def _cursor_datetime(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidCursorError from exc
    if parsed.tzinfo is None:
        raise InvalidCursorError
    return parsed


def _source_ids_for_warning(session: Session, warning: Warning) -> list[UUID]:
    def merge_primary(primary_id: UUID | None, related_ids: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(item for item in (primary_id, *related_ids) if item is not None))

    if warning.risk_finding_id is not None:
        primary_id = session.scalar(
            select(RiskFinding.evidence_span_id).where(
                RiskFinding.organization_id == warning.organization_id,
                RiskFinding.id == warning.risk_finding_id,
            )
        )
        related_ids = list(
            session.scalars(
                select(RiskFindingEvidence.source_span_id)
                .where(
                    RiskFindingEvidence.organization_id == warning.organization_id,
                    RiskFindingEvidence.finding_id == warning.risk_finding_id,
                )
                .order_by(RiskFindingEvidence.position_no)
            )
        )
        return merge_primary(primary_id, related_ids)
    if warning.clause_comparison_id is not None:
        primary_id = session.scalar(
            select(ClauseComparison.evidence_span_id).where(
                ClauseComparison.organization_id == warning.organization_id,
                ClauseComparison.id == warning.clause_comparison_id,
            )
        )
        related_ids = list(
            session.scalars(
                select(ClauseComparisonEvidence.source_span_id)
                .where(
                    ClauseComparisonEvidence.organization_id == warning.organization_id,
                    ClauseComparisonEvidence.comparison_id == warning.clause_comparison_id,
                )
                .order_by(ClauseComparisonEvidence.position_no)
            )
        )
        return merge_primary(primary_id, related_ids)
    if warning.extracted_field_id is not None:
        primary_id = session.scalar(
            select(ExtractedField.evidence_span_id).where(
                ExtractedField.organization_id == warning.organization_id,
                ExtractedField.id == warning.extracted_field_id,
            )
        )
        related_ids = list(
            session.scalars(
                select(ExtractedFieldEvidence.source_span_id)
                .where(
                    ExtractedFieldEvidence.organization_id == warning.organization_id,
                    ExtractedFieldEvidence.extracted_field_id == warning.extracted_field_id,
                )
                .order_by(ExtractedFieldEvidence.position_no)
            )
        )
        return merge_primary(primary_id, related_ids)
    if warning.classification_id is not None:
        primary_id = session.scalar(
            select(ContractClassification.evidence_span_id).where(
                ContractClassification.organization_id == warning.organization_id,
                ContractClassification.id == warning.classification_id,
            )
        )
        related_ids = list(
            session.scalars(
                select(ContractClassificationEvidence.source_span_id)
                .where(
                    ContractClassificationEvidence.organization_id == warning.organization_id,
                    ContractClassificationEvidence.classification_id == warning.classification_id,
                )
                .order_by(ContractClassificationEvidence.position_no)
            )
        )
        return merge_primary(primary_id, related_ids)
    return []


def _warning_subject(warning: Warning) -> tuple[str, UUID]:
    for name in (
        "risk_finding_id",
        "clause_comparison_id",
        "extracted_field_id",
        "classification_id",
    ):
        value = getattr(warning, name)
        if value is not None:
            return name.removesuffix("_id"), value
    raise RuntimeError("warning has no subject")


def _dedupe_key(
    task_id: UUID, trigger_type: str, subject_id: UUID, source_span_id: UUID | None
) -> str:
    return (
        f"task:{task_id}:trigger:{trigger_type}:subject:{subject_id}:"
        f"span:{source_span_id or 'none'}"
    )


def _create_warning(
    session: Session,
    *,
    task: ReviewTask,
    trigger_type: str,
    severity: str,
    priority: str,
    subject_type: str,
    subject_id: UUID,
    source_span_id: UUID | None,
    metadata: dict[str, Any],
) -> Warning:
    key = _dedupe_key(task.id, trigger_type, subject_id, source_span_id)
    warning = session.scalar(
        select(Warning)
        .where(
            Warning.organization_id == task.organization_id,
            Warning.dedupe_key == key,
            Warning.status.in_(_ACTIVE_WARNING_STATUSES),
        )
        .with_for_update()
    )
    if warning is not None:
        return warning
    warning = Warning(
        id=uuid4(),
        organization_id=task.organization_id,
        review_task_id=task.id,
        contract_id=task.contract_id,
        risk_finding_id=subject_id if subject_type == "risk_finding" else None,
        clause_comparison_id=subject_id if subject_type == "clause_comparison" else None,
        extracted_field_id=subject_id if subject_type == "extracted_field" else None,
        classification_id=subject_id if subject_type == "contract_classification" else None,
        trigger_type=trigger_type,
        triggered_at=_now(),
        dedupe_key=key,
        severity=severity,
        priority=priority,
    )
    session.add(warning)
    session.flush()
    session.add(
        WarningEvent(
            organization_id=task.organization_id,
            warning_id=warning.id,
            event_type="created",
            from_status=None,
            to_status=warning.status,
            actor_id=None,
            metadata_json={
                "trigger_type": trigger_type,
                "subject_type": subject_type,
                "subject_id": str(subject_id),
                "source_span_id": str(source_span_id) if source_span_id else None,
                "rule_bundle_version_id": str(task.rule_bundle_version_id),
                **metadata,
            },
        )
    )
    title = f"发现{ {'high': '高', 'medium': '中', 'low': '低'}.get(severity, '') }风险预警"
    create_warning_notifications(
        session,
        warning=warning,
        title=title,
        body="请前往预警中心查看证据并完成复核。",
    )
    return warning


def generate_warnings(session: Session, *, task: ReviewTask) -> list[Warning]:
    """Create warnings after all machine result stages have committed."""
    organization = session.scalar(
        select(Organization).where(Organization.id == task.organization_id).with_for_update()
    )
    if organization is None:
        return []
    settings = organization_settings(organization)
    warnings: list[Warning] = []
    findings = list(
        session.scalars(
            select(RiskFinding).where(
                RiskFinding.organization_id == task.organization_id,
                RiskFinding.review_task_id == task.id,
                RiskFinding.status == "pending_review",
            )
        )
    )
    for finding in findings:
        if finding.severity == "high" or (
            finding.severity == "medium" and settings["warn_on_medium_risk"]
        ):
            span_id = finding.evidence_span_id
            if span_id is None:
                continue
            warnings.append(
                _create_warning(
                    session,
                    task=task,
                    trigger_type="high_risk" if finding.severity == "high" else "medium_risk",
                    severity=finding.severity,
                    priority=finding.severity,
                    subject_type="risk_finding",
                    subject_id=finding.id,
                    source_span_id=span_id,
                    metadata={"risk_type": finding.risk_type},
                )
            )
    threshold = float(settings["ocr_low_confidence_threshold"])
    fields = list(
        session.scalars(
            select(ExtractedField).where(
                ExtractedField.organization_id == task.organization_id,
                ExtractedField.review_task_id == task.id,
                ExtractedField.confidence < threshold,
                ExtractedField.evidence_span_id.is_not(None),
            )
        )
    )
    for field in fields:
        if field.evidence_span_id is not None:
            warnings.append(
                _create_warning(
                    session,
                    task=task,
                    trigger_type="low_confidence",
                    severity="medium",
                    priority="medium",
                    subject_type="extracted_field",
                    subject_id=field.id,
                    source_span_id=field.evidence_span_id,
                    metadata={"field_key": field.field_key},
                )
            )
    classification = session.scalar(
        select(ContractClassification).where(
            ContractClassification.organization_id == task.organization_id,
            ContractClassification.review_task_id == task.id,
            ContractClassification.confidence < threshold,
        )
    )
    if classification is not None:
        warnings.append(
            _create_warning(
                session,
                task=task,
                trigger_type="low_confidence",
                severity="medium",
                priority="medium",
                subject_type="contract_classification",
                subject_id=classification.id,
                source_span_id=classification.evidence_span_id,
                metadata={"subject": "classification"},
            )
        )
    comparisons = list(
        session.scalars(
            select(ClauseComparison).where(
                ClauseComparison.organization_id == task.organization_id,
                ClauseComparison.review_task_id == task.id,
                ClauseComparison.status.in_(("deviated", "missing", "uncertain")),
            )
        )
    )
    for comparison in comparisons:
        if comparison.evidence_span_id is None and comparison.status != "missing":
            continue
        warnings.append(
            _create_warning(
                session,
                task=task,
                trigger_type="clause_review",
                severity=comparison.severity,
                priority=comparison.severity,
                subject_type="clause_comparison",
                subject_id=comparison.id,
                source_span_id=comparison.evidence_span_id,
                metadata={"clause_key": comparison.clause_key},
            )
        )
    return warnings


def _warning_list_statement(
    session: Session,
    *,
    organization_id: UUID,
    viewer_user_id: UUID | None,
    query: WarningListQuery,
) -> tuple[Any, Any]:
    statement = (
        select(Warning)
        .join(
            Contract,
            and_(
                Contract.organization_id == Warning.organization_id,
                Contract.id == Warning.contract_id,
            ),
        )
        .where(Warning.organization_id == organization_id)
    )
    if viewer_user_id is not None:
        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == Warning.organization_id,
                ContractAccessGrant.contract_id == Warning.contract_id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    if query.status is not None:
        statement = statement.where(Warning.status == query.status)
    if query.severity is not None:
        statement = statement.where(Warning.severity == query.severity)
    if query.contract_type is not None:
        statement = statement.where(Contract.declared_type == query.contract_type)
    if query.assignee_id is not None:
        statement = statement.where(Warning.assignee_id == query.assignee_id)
    if query.risk_type is not None:
        statement = statement.join(
            RiskFinding,
            and_(
                RiskFinding.organization_id == Warning.organization_id,
                RiskFinding.id == Warning.risk_finding_id,
            ),
        ).where(RiskFinding.risk_type == query.risk_type)
    if query.triggered_from is not None:
        statement = statement.where(Warning.triggered_at >= query.triggered_from)
    if query.triggered_to is not None:
        statement = statement.where(Warning.triggered_at <= query.triggered_to)
    return statement, select(func.count()).select_from(statement.subquery())


def list_warnings(
    session: Session, *, organization_id: UUID, viewer_user_id: UUID | None, query: WarningListQuery
) -> dict[str, Any]:
    statement, count_statement = _warning_list_statement(
        session, organization_id=organization_id, viewer_user_id=viewer_user_id, query=query
    )
    count_source = count_statement.get_final_froms()[0]
    cursor_value: Any = None
    cursor_id: UUID | None = None
    page_value: Callable[[Warning], Any]
    if query.cursor is not None:
        cursor_value, cursor_id = _decode_warning_cursor(query.cursor, query.sort)
    if query.sort == "triggered_at":
        key_column: Any = Warning.triggered_at
        if cursor_value is not None and cursor_id is not None:
            value = _cursor_datetime(cursor_value)
            boundary = (
                or_(key_column < value, and_(key_column == value, Warning.id < cursor_id))
                if query.direction == "desc"
                else or_(key_column > value, and_(key_column == value, Warning.id > cursor_id))
            )
        order = desc if query.direction == "desc" else asc
        ordered = statement.order_by(order(key_column), order(Warning.id))

        def page_value(item: Warning) -> str:
            return item.triggered_at.isoformat()
    elif query.sort == "priority":
        key_column = case(
            (Warning.priority == "high", 0), (Warning.priority == "medium", 1), else_=2
        )
        if cursor_value is not None and cursor_id is not None:
            numeric = int(cursor_value)
            boundary = (
                or_(key_column < numeric, and_(key_column == numeric, Warning.id < cursor_id))
                if query.direction == "desc"
                else or_(key_column > numeric, and_(key_column == numeric, Warning.id > cursor_id))
            )
        order = desc if query.direction == "desc" else asc
        ordered = statement.order_by(order(key_column), order(Warning.id))

        def page_value(item: Warning) -> int:
            return _WARNING_PRIORITY[item.priority]
    else:
        key_column = Warning.due_at
        if cursor_id is not None:
            if cursor_value is None:
                boundary = and_(
                    key_column.is_(None),
                    Warning.id < cursor_id if query.direction == "desc" else Warning.id > cursor_id,
                )
            else:
                value = _cursor_datetime(cursor_value)
                boundary = (
                    or_(
                        key_column.is_(None),
                        key_column < value,
                        and_(key_column == value, Warning.id < cursor_id),
                    )
                    if query.direction == "desc"
                    else or_(
                        key_column.is_(None),
                        key_column > value,
                        and_(key_column == value, Warning.id > cursor_id),
                    )
                )
        order = desc if query.direction == "desc" else asc
        ordered = statement.order_by(order(key_column).nullslast(), order(Warning.id))

        def page_value(item: Warning) -> str | None:
            return item.due_at.isoformat() if item.due_at is not None else None

    if cursor_id is not None:
        ordered = ordered.where(boundary)
    rows = list(session.scalars(ordered.limit(query.limit + 1)))
    items = rows[: query.limit]
    unprocessed_count = (
        session.scalar(
            count_statement.where(
                count_source.c.status.in_(("pending_confirmation", "in_progress"))
            )
        )
        or 0
    )
    high_count = session.scalar(count_statement.where(count_source.c.severity == "high")) or 0
    next_cursor = None
    if len(rows) > query.limit and items:
        next_cursor = _safe_cursor_payload(query.sort, page_value(items[-1]), items[-1].id)
    return {
        "items": [_warning_list_payload(item) for item in items],
        "next_cursor": next_cursor,
        "has_more": len(rows) > query.limit,
        "summary": {"unprocessed_count": int(unprocessed_count), "high_count": int(high_count)},
    }


def _warning_list_payload(warning: Warning) -> dict[str, Any]:
    return {
        key: getattr(warning, key)
        for key in (
            "id",
            "contract_id",
            "review_task_id",
            "severity",
            "status",
            "priority",
            "assignee_id",
            "due_at",
            "trigger_type",
            "triggered_at",
        )
    }


def get_warning(
    session: Session, *, organization_id: UUID, warning_id: UUID, viewer_user_id: UUID | None
) -> dict[str, Any]:
    statement = (
        select(Warning)
        .join(
            Contract,
            and_(
                Contract.organization_id == Warning.organization_id,
                Contract.id == Warning.contract_id,
            ),
        )
        .where(Warning.organization_id == organization_id, Warning.id == warning_id)
    )
    if viewer_user_id is not None:
        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == Warning.organization_id,
                ContractAccessGrant.contract_id == Warning.contract_id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    warning = session.scalar(statement)
    if warning is None:
        raise ApplicationError(status_code=404, code="WARNING_NOT_FOUND", message="预警不存在。")
    task = session.scalar(
        select(ReviewTask).where(
            ReviewTask.organization_id == organization_id, ReviewTask.id == warning.review_task_id
        )
    )
    document = None
    if task is not None and task.document_version_id is not None:
        document = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.id == task.document_version_id,
                DocumentVersion.status == "succeeded",
            )
        )
    evidence: list[dict[str, Any]] = []
    if document is not None:
        for source_span_id in _source_ids_for_warning(session, warning):
            evidence.append(
                _source_locator_payload(
                    session,
                    organization_id=organization_id,
                    document=document,
                    source_span_id=source_span_id,
                )
            )
    membership = None
    if warning.assignee_id is not None:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == warning.assignee_id,
            )
        )
    events = list(
        session.scalars(
            select(WarningEvent)
            .where(
                WarningEvent.organization_id == organization_id,
                WarningEvent.warning_id == warning.id,
            )
            .order_by(WarningEvent.created_at, WarningEvent.id)
        )
    )
    return {
        "id": warning.id,
        "contract_id": warning.contract_id,
        "review_task_id": warning.review_task_id,
        "trigger_type": warning.trigger_type,
        "triggered_at": warning.triggered_at,
        "severity": warning.severity,
        "priority": warning.priority,
        "status": warning.status,
        "risk_finding_id": warning.risk_finding_id,
        "clause_comparison_id": warning.clause_comparison_id,
        "extracted_field_id": warning.extracted_field_id,
        "classification_id": warning.classification_id,
        "assignee": (
            {
                "id": membership.user_id,
                "display_name": membership.display_name,
                "email": membership.email,
            }
            if membership and membership.user_id
            else None
        ),
        "assignee_id": warning.assignee_id,
        "due_at": warning.due_at,
        "resolution": warning.resolution,
        "revision_id": warning.revision_id,
        "closed_at": warning.closed_at,
        "evidence": evidence,
        "events": [
            {
                "event_id": event.id,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor_id": event.actor_id,
                "note": event.note,
                "assignee_id": event.metadata_json.get("assignee_id"),
                "due_at": event.metadata_json.get("due_at"),
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


def create_warning_event(
    session: Session,
    *,
    actor: TenantContext,
    role: str,
    warning_id: UUID,
    body: WarningEventRequest,
    request_id: str,
) -> dict[str, Any]:
    if role not in {"org_admin", "reviewer"}:
        raise ForbiddenError()
    with UnitOfWork(session) as unit_of_work:
        warning = _warning_or_not_found(
            session, organization_id=actor.organization_id, warning_id=warning_id, for_update=True
        )
        event_type = body.type
        current_status = warning.status
        if event_type in {"assign", "note"}:
            if current_status not in {"pending_confirmation", "in_progress"}:
                raise _error("INVALID_STATE_TRANSITION", "当前预警状态不允许追加该事件。")
        elif event_type in {"false_positive", "ignore"}:
            if current_status not in {"pending_confirmation", "in_progress"}:
                raise _error("INVALID_STATE_TRANSITION", "当前预警状态不允许该操作。")
        elif event_type == "reopen":
            if role != "org_admin" or current_status not in {"ignored", "closed"}:
                raise _error(
                    "INVALID_STATE_TRANSITION",
                    "当前账户或预警状态不允许重新打开。",
                    status_code=403 if role != "org_admin" else 409,
                )
        else:
            expected = _EVENT_STATUS.get(event_type)
            if expected is None or current_status != expected[0]:
                raise _error("INVALID_STATE_TRANSITION", "当前预警状态不允许该操作。")
        if event_type == "assign":
            if body.assignee_id is None:
                raise _error("ACTION_FIELD_REQUIRED", "分派必须指定责任人。", status_code=422)
            assignee = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == actor.organization_id,
                    OrganizationMembership.user_id == body.assignee_id,
                    OrganizationMembership.role == "reviewer",
                    OrganizationMembership.status == "active",
                )
            )
            if assignee is None:
                raise _error(
                    "ACTION_FIELD_REQUIRED", "责任人必须是同组织有效审核员。", status_code=422
                )
        if event_type == "note" and body.note is None:
            raise _error("ACTION_FIELD_REQUIRED", "说明不能为空。", status_code=422)
        if event_type == "close" and body.resolution is None and body.revision_id is None:
            raise _error("ACTION_FIELD_REQUIRED", "关闭必须提供结论或修订引用。", status_code=422)
        from_status = warning.status
        to_status = warning.status
        if event_type in {"false_positive", "ignore"}:
            to_status = "ignored"
            warning.status = to_status
        elif event_type in _EVENT_STATUS:
            to_status = _EVENT_STATUS[event_type][1]
            warning.status = to_status
        if event_type == "assign":
            warning.assignee_id = body.assignee_id
            warning.due_at = body.due_at
        elif event_type == "close":
            warning.resolution = body.resolution
            warning.revision_id = body.revision_id
            warning.closed_at = _now()
        elif event_type == "reopen":
            warning.resolution = None
            warning.revision_id = None
            warning.closed_at = None
        if event_type == "false_positive" and warning.risk_finding_id is not None:
            finding = session.scalar(
                select(RiskFinding)
                .where(
                    RiskFinding.organization_id == actor.organization_id,
                    RiskFinding.id == warning.risk_finding_id,
                )
                .with_for_update()
            )
            if finding is not None:
                finding.status = "false_positive"
                finding.version += 1
        warning.version += 1
        metadata: dict[str, Any] = {}
        if body.assignee_id is not None:
            metadata["assignee_id"] = str(body.assignee_id)
        if body.due_at is not None:
            metadata["due_at"] = body.due_at.isoformat()
        if body.revision_id is not None:
            metadata["revision_id"] = str(body.revision_id)
        event = WarningEvent(
            organization_id=actor.organization_id,
            warning_id=warning.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.user_id,
            note=body.note or body.resolution,
            metadata_json=metadata,
        )
        session.add(event)
        append_audit_log(
            session,
            actor=actor,
            action=f"warning.{event_type}",
            resource_type="warning",
            resource_id=warning.id,
            request_id=request_id,
            before={
                "status": from_status,
                "assignee_id": str(warning.assignee_id) if warning.assignee_id else None,
            },
            after={
                "status": to_status,
                "assignee_id": str(warning.assignee_id) if warning.assignee_id else None,
            },
        )
        unit_of_work.commit()
    return {
        "event_id": event.id,
        "event_type": event.event_type,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "actor_id": event.actor_id,
        "note": event.note,
        "assignee_id": warning.assignee_id,
        "due_at": warning.due_at,
        "created_at": event.created_at,
    }


def list_notifications(
    session: Session, *, user_id: UUID, query: NotificationListQuery
) -> dict[str, Any]:
    statement = select(Notification).where(Notification.user_id == user_id)
    if query.status == "unread":
        statement = statement.where(Notification.read_at.is_(None))
    elif query.status == "read":
        statement = statement.where(Notification.read_at.is_not(None))
    if query.warning_id is not None:
        statement = statement.where(Notification.warning_id == query.warning_id)
    if query.cursor is not None:
        value, cursor_id = _decode_warning_cursor(query.cursor, "created_at")
        created_at = _cursor_datetime(value)
        statement = statement.where(
            or_(
                Notification.created_at < created_at,
                and_(Notification.created_at == created_at, Notification.id < cursor_id),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(desc(Notification.created_at), desc(Notification.id)).limit(
                query.limit + 1
            )
        )
    )
    items = rows[: query.limit]
    return {
        "items": [
            {
                "id": item.id,
                "warning_id": item.warning_id,
                "channel": item.channel,
                "status": "read" if item.read_at else "unread",
                "title": item.title,
                "body": item.body,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "next_cursor": _safe_cursor_payload(
            "created_at", items[-1].created_at.isoformat(), items[-1].id
        )
        if len(rows) > query.limit and items
        else None,
        "has_more": len(rows) > query.limit,
    }


def mark_notification_read(
    session: Session, *, user_id: UUID, notification_id: UUID
) -> dict[str, Any]:
    with UnitOfWork(session) as unit_of_work:
        notification = session.scalar(
            select(Notification)
            .where(Notification.user_id == user_id, Notification.id == notification_id)
            .with_for_update()
        )
        if notification is None:
            raise ApplicationError(
                status_code=404, code="NOTIFICATION_NOT_FOUND", message="通知不存在。"
            )
        notification.read_at = notification.read_at or _now()
        unit_of_work.commit()
    return {"id": notification.id, "status": "read", "read_at": notification.read_at}


def unread_count(session: Session, *, user_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )


__all__ = [
    "create_warning_event",
    "generate_warnings",
    "get_warning",
    "list_notifications",
    "list_warnings",
    "mark_notification_read",
    "unread_count",
]
