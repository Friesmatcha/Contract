from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.modules.contracts.models import Contract
from backend.app.modules.feedback.models import Feedback
from backend.app.modules.feedback.schemas import FeedbackCreateRequest
from backend.app.modules.reviews.models import ReviewTask
from backend.app.modules.reviews.results.models import (
    ClauseComparison,
    ContractClassification,
    ExtractedField,
    RiskFinding,
)
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
from backend.app.shared.idempotency import (
    IdempotencyResult,
    execute_idempotent,
    organization_scope,
    request_fingerprint,
)
from backend.app.shared.tenant import TenantContext


def _error(
    code: str, message: str, *, status_code: int = 422, details: dict[str, Any] | None = None
) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message, details=details)


def _subject_model(subject_type: str) -> type[Any]:
    return {
        "classification": ContractClassification,
        "extracted_field": ExtractedField,
        "risk_finding": RiskFinding,
        "clause_comparison": ClauseComparison,
    }[subject_type]


def _validate_corrected_value(
    session: Session, *, organization_id: UUID, subject_type: str, subject_id: UUID, value: Any
) -> None:
    if value is None:
        return
    if subject_type == "classification":
        if value not in {"purchase", "sales", "nda", "outsourcing", "employment", "other"}:
            raise _error("FEEDBACK_SCHEMA_INVALID", "反馈分类值无效。")
        return
    if subject_type == "extracted_field":
        from backend.app.modules.reviews.revisions.service import _validate_field_value

        row = session.scalar(
            select(ExtractedField).where(
                ExtractedField.organization_id == organization_id,
                ExtractedField.id == subject_id,
            )
        )
        if row is None:
            raise _error("SUBJECT_NOT_FOUND", "反馈对象不存在。", status_code=404)
        _validate_field_value(row.field_key, value)
        return
    if not isinstance(value, dict):
        raise _error("FEEDBACK_SCHEMA_INVALID", "反馈修订值必须是 JSON object。")


def create_feedback(
    session: Session,
    *,
    actor: TenantContext,
    body: FeedbackCreateRequest,
    idempotency_key: str,
    request_id: str,
) -> Feedback:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/feedback",
        body=body.model_dump(mode="json"),
    )
    created: Feedback | None = None
    with UnitOfWork(session) as unit_of_work:

        def operation() -> IdempotencyResult:
            nonlocal created
            task = session.scalar(
                select(ReviewTask)
                .where(
                    ReviewTask.organization_id == actor.organization_id,
                    ReviewTask.id == body.review_task_id,
                )
                .with_for_update()
            )
            if task is None:
                raise _error("REVIEW_TASK_NOT_FOUND", "审核任务不存在。", status_code=404)
            subject_model = _subject_model(body.subject_type)
            subject = session.scalar(
                select(subject_model).where(subject_model.id == body.subject_id).with_for_update()
            )
            if subject is None:
                raise _error("SUBJECT_NOT_FOUND", "反馈对象不存在。", status_code=404)
            if (
                subject.organization_id != actor.organization_id
                or subject.review_task_id != task.id
            ):
                raise _error(
                    "SUBJECT_ORGANIZATION_MISMATCH",
                    "反馈对象不属于当前审核任务或组织。",
                    status_code=409,
                )
            has_corrected_value = "corrected_value" in body.model_fields_set
            if body.label == "modified":
                if not has_corrected_value:
                    raise _error(
                        "FEEDBACK_SCHEMA_INVALID", "modified 反馈必须提供 corrected_value。"
                    )
                _validate_corrected_value(
                    session,
                    organization_id=actor.organization_id,
                    subject_type=body.subject_type,
                    subject_id=body.subject_id,
                    value=body.corrected_value,
                )
            elif has_corrected_value:
                raise _error(
                    "FEEDBACK_SCHEMA_INVALID", "只有 modified 反馈可以提供 corrected_value。"
                )
            note = body.note.strip() if body.note else None
            now = datetime.now(UTC)
            created = Feedback(
                organization_id=actor.organization_id,
                review_task_id=task.id,
                subject_type=body.subject_type,
                subject_id=body.subject_id,
                label=body.label,
                corrected_value=body.corrected_value if has_corrected_value else None,
                note=note,
                created_by=actor.user_id,
                created_at=now,
            )
            session.add(created)
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="feedback.created",
                resource_type="feedback",
                resource_id=created.id,
                request_id=request_id,
                after={
                    "review_task_id": str(task.id),
                    "subject_type": body.subject_type,
                    "subject_id": str(body.subject_id),
                    "label": body.label,
                    "has_corrected_value": has_corrected_value,
                },
            )
            return IdempotencyResult(201, "feedback", created.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/feedback",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("feedback idempotency record has no resource")
            created = session.scalar(select(Feedback).where(Feedback.id == result.resource_id))
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("feedback creation returned no resource")
    return created


def feedback_summary(
    session: Session,
    *,
    organization_id: UUID,
    contract_type: str | None,
    rule_bundle_version_id: UUID | None,
    model_version: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> dict[str, Any]:
    if created_from is not None and created_to is not None and created_from > created_to:
        raise _error("INVALID_FILTER", "created_from 不能晚于 created_to。")
    statement = (
        select(Feedback, ReviewTask, Contract)
        .join(
            ReviewTask,
            (ReviewTask.organization_id == Feedback.organization_id)
            & (ReviewTask.id == Feedback.review_task_id),
        )
        .join(
            Contract,
            (Contract.organization_id == ReviewTask.organization_id)
            & (Contract.id == ReviewTask.contract_id),
        )
        .where(Feedback.organization_id == organization_id)
    )
    if created_from is not None:
        statement = statement.where(Feedback.created_at >= created_from)
    if created_to is not None:
        statement = statement.where(Feedback.created_at <= created_to)
    rows = list(session.execute(statement))
    filtered: list[tuple[Feedback, ReviewTask, Contract]] = []
    for feedback, task, contract in rows:
        if contract_type is not None and contract.declared_type != contract_type:
            continue
        if (
            rule_bundle_version_id is not None
            and task.rule_bundle_version_id != rule_bundle_version_id
        ):
            continue
        task_model_version = task.model_config_json.get("model")
        if model_version is not None and task_model_version != model_version:
            continue
        filtered.append((feedback, task, contract))

    counts = Counter(feedback.label for feedback, _, _ in filtered)
    by_risk: dict[str, Counter[str]] = defaultdict(Counter)
    risk_ids = [
        feedback.subject_id
        for feedback, _, _ in filtered
        if feedback.subject_type == "risk_finding"
    ]
    risk_types = (
        {
            row.id: row.risk_type
            for row in session.scalars(
                select(RiskFinding).where(
                    RiskFinding.organization_id == organization_id,
                    RiskFinding.id.in_(risk_ids),
                )
            )
        }
        if risk_ids
        else {}
    )
    for feedback, _, _ in filtered:
        if feedback.subject_type == "risk_finding":
            by_risk[risk_types.get(feedback.subject_id, "unknown")][feedback.label] += 1
    labels = ("correct", "incorrect", "modified", "ignored")
    return {
        "filters": {
            "contract_type": contract_type,
            "rule_bundle_version_id": rule_bundle_version_id,
            "model_version": model_version,
            "created_from": created_from,
            "created_to": created_to,
        },
        "counts": {label: counts.get(label, 0) for label in labels},
        "by_risk_type": [
            {"risk_type": risk_type, **{label: values.get(label, 0) for label in labels}}
            for risk_type, values in sorted(by_risk.items())
        ],
    }


__all__ = ["create_feedback", "feedback_summary"]
