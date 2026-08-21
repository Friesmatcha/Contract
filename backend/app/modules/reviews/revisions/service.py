from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.modules.documents.models import SourceSpan
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
from backend.app.modules.reviews.revisions.models import ResultRevision
from backend.app.modules.reviews.revisions.schemas import (
    ClauseComparisonRevisionRequest,
    ContractClassificationRevisionRequest,
    ExtractedFieldRevisionRequest,
    RiskFindingRevisionRequest,
)
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
from backend.app.shared.tenant import TenantContext

SUBJECT_TYPES = ("classification", "extracted_field", "risk_finding", "clause_comparison")


def _error(
    code: str, message: str, *, status_code: int = 422, details: dict[str, Any] | None = None
) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message, details=details)


def _now() -> datetime:
    return datetime.now(UTC)


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(
        left, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) == json.dumps(right, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _subject_row(
    session: Session, *, organization_id: UUID, subject_type: str, subject_id: UUID
) -> Any:
    subject_model: type[Any] = {
        "classification": ContractClassification,
        "extracted_field": ExtractedField,
        "risk_finding": RiskFinding,
        "clause_comparison": ClauseComparison,
    }.get(subject_type, ContractClassification)
    row = session.scalar(
        select(subject_model)
        .where(subject_model.organization_id == organization_id, subject_model.id == subject_id)
        .with_for_update()
    )
    if row is None:
        raise _error("RESULT_NOT_FOUND", "审核结果不存在。", status_code=404)
    return row


def _task_for_subject(session: Session, *, organization_id: UUID, row: Any) -> ReviewTask:
    task = session.scalar(
        select(ReviewTask)
        .where(
            ReviewTask.organization_id == organization_id,
            ReviewTask.id == row.review_task_id,
        )
        .with_for_update()
    )
    if task is None:
        raise _error("RESULT_NOT_FOUND", "审核结果不存在。", status_code=404)
    if task.status != "pending_review":
        raise _error(
            "INVALID_STATE_TRANSITION", "仅等待人工复核的任务可以修订结果。", status_code=409
        )
    return task


def _evidence_ids(
    session: Session, *, organization_id: UUID, subject_type: str, subject_id: UUID
) -> list[UUID]:
    association_model: type[Any] = {
        "classification": ContractClassificationEvidence,
        "extracted_field": ExtractedFieldEvidence,
        "risk_finding": RiskFindingEvidence,
        "clause_comparison": ClauseComparisonEvidence,
    }[subject_type]
    subject_column = {
        "classification": ContractClassificationEvidence.classification_id,
        "extracted_field": ExtractedFieldEvidence.extracted_field_id,
        "risk_finding": RiskFindingEvidence.finding_id,
        "clause_comparison": ClauseComparisonEvidence.comparison_id,
    }[subject_type]
    return list(
        session.scalars(
            select(association_model.source_span_id)
            .where(
                association_model.organization_id == organization_id,
                subject_column == subject_id,
            )
            .order_by(association_model.position_no)
        )
    )


def _snapshot(
    session: Session, *, organization_id: UUID, subject_type: str, row: Any
) -> dict[str, Any]:
    evidence = [
        str(value)
        for value in _evidence_ids(
            session, organization_id=organization_id, subject_type=subject_type, subject_id=row.id
        )
    ]
    if subject_type == "classification":
        return {
            "id": str(row.id),
            "model_value": row.model_value,
            "current_value": row.current_value,
            "status": row.status,
            "version": row.version,
            "evidence_span_ids": evidence,
        }
    if subject_type == "extracted_field":
        return {
            "id": str(row.id),
            "field_key": row.field_key,
            "model_value": row.model_value_json,
            "current_value": row.current_value_json,
            "status": row.status,
            "version": row.version,
            "evidence_span_ids": evidence,
        }
    if subject_type == "risk_finding":
        return {
            "id": str(row.id),
            "risk_type": row.risk_type,
            "severity": row.severity,
            "title": row.title,
            "description": row.description,
            "basis": row.basis,
            "suggestion": row.suggestion,
            "confidence": row.confidence,
            "source": row.source,
            "status": row.status,
            "version": row.version,
            "evidence_span_ids": evidence,
        }
    return {
        "id": str(row.id),
        "clause_key": row.clause_key,
        "status": row.status,
        "contract_text": row.contract_text,
        "difference_summary": row.difference_summary,
        "severity": row.severity,
        "suggestion": row.suggestion,
        "version": row.version,
        "evidence_span_ids": evidence,
    }


def _validate_field_value(field_key: str, value: Any) -> None:
    if value is None:
        return
    valid = True
    if field_key == "parties":
        valid = (
            isinstance(value, Mapping)
            and isinstance(value.get("party_a"), str)
            and isinstance(value.get("party_b"), str)
        )
    elif field_key == "signing_date":
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
            except ValueError:
                valid = False
        else:
            valid = False
    elif field_key == "contract_amount":
        valid = (
            isinstance(value, Mapping)
            and isinstance(value.get("amount"), (str, int, float))
            and isinstance(value.get("currency"), str)
            and isinstance(value.get("tax_included"), bool)
        )
    elif field_key in {"performance_period", "dispute_resolution", "payment_terms"}:
        valid = isinstance(value, Mapping) and isinstance(value.get("value"), str)
    elif field_key == "auto_renewal":
        valid = isinstance(value, Mapping) and isinstance(value.get("value"), bool)
    if not valid:
        raise _error("FIELD_SCHEMA_INVALID", "字段值不符合该字段的 JSON Schema。")


def _validate_version(row: Any, requested: int) -> None:
    if row.version != requested:
        raise _error(
            "RESOURCE_VERSION_CONFLICT",
            "资源已被更新，请刷新后重试。",
            status_code=409,
            details={"current_version": row.version},
        )


def _validate_evidence_for_status(
    session: Session, *, task: ReviewTask, subject_type: str, row: Any, status: str
) -> None:
    evidence_ids = _valid_evidence_ids(
        session, task=task, subject_type=subject_type, subject_id=row.id
    )
    if subject_type == "risk_finding" and status == "confirmed" and not evidence_ids:
        raise _error("EVIDENCE_REQUIRED", "确认风险必须有合法证据。")
    if (
        subject_type == "clause_comparison"
        and status in {"matched", "deviated"}
        and not evidence_ids
    ):
        raise _error("EVIDENCE_REQUIRED", "匹配或偏离的条款结果必须有合法证据。")


def _valid_evidence_ids(
    session: Session, *, task: ReviewTask, subject_type: str, subject_id: UUID
) -> list[UUID]:
    association_model: type[Any] = {
        "classification": ContractClassificationEvidence,
        "extracted_field": ExtractedFieldEvidence,
        "risk_finding": RiskFindingEvidence,
        "clause_comparison": ClauseComparisonEvidence,
    }[subject_type]
    subject_column = {
        "classification": ContractClassificationEvidence.classification_id,
        "extracted_field": ExtractedFieldEvidence.extracted_field_id,
        "risk_finding": RiskFindingEvidence.finding_id,
        "clause_comparison": ClauseComparisonEvidence.comparison_id,
    }[subject_type]
    if task.document_version_id is None:
        return []
    return list(
        session.scalars(
            select(association_model.source_span_id)
            .join(
                SourceSpan,
                and_(
                    SourceSpan.organization_id == association_model.organization_id,
                    SourceSpan.id == association_model.source_span_id,
                    SourceSpan.document_version_id == task.document_version_id,
                ),
            )
            .where(
                association_model.organization_id == task.organization_id,
                association_model.document_version_id == task.document_version_id,
                subject_column == subject_id,
            )
            .order_by(association_model.position_no)
        )
    )


def _result_payload(
    session: Session,
    *,
    organization_id: UUID,
    task_id: UUID,
    subject_type: str,
    subject_id: UUID,
    revision_id: UUID,
) -> dict[str, Any]:
    from backend.app.modules.reviews.results.service import get_review_results

    payload = get_review_results(
        session,
        organization_id=organization_id,
        task_id=task_id,
        viewer_user_id=None,
        include_evidence=True,
    )
    key = {
        "classification": "classification",
        "extracted_field": "extracted_fields",
        "risk_finding": "risk_findings",
        "clause_comparison": "clause_comparisons",
    }[subject_type]
    collection = payload[key]
    if isinstance(collection, list):
        result = next(item for item in collection if item["id"] == subject_id)
    else:
        result = collection
    result["revision_id"] = revision_id
    return cast(dict[str, Any], result)


def _apply_revision(
    session: Session,
    *,
    actor: TenantContext,
    subject_type: str,
    subject_id: UUID,
    body: Any,
    request_id: str,
) -> dict[str, Any]:
    with UnitOfWork(session) as unit_of_work:
        row = _subject_row(
            session,
            organization_id=actor.organization_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        task = _task_for_subject(session, organization_id=actor.organization_id, row=row)
        _validate_version(row, body.version)
        before = _snapshot(
            session, organization_id=actor.organization_id, subject_type=subject_type, row=row
        )

        if subject_type == "classification":
            same_as_model = body.current_value == row.model_value
            if body.status == "confirmed" and not same_as_model:
                raise _error(
                    "RESULT_STATUS_INVALID", "当前分类不同于模型值时必须标记为 corrected。"
                )
            if body.status == "corrected" and same_as_model:
                raise _error("RESULT_STATUS_INVALID", "当前分类等于模型值时不能标记为 corrected。")
            row.current_value = body.current_value
        elif subject_type == "extracted_field":
            _validate_field_value(row.field_key, body.current_value)
            same_as_model = _json_equal(body.current_value, row.model_value_json)
            if body.status == "not_found" and body.current_value is not None:
                raise _error("RESULT_STATUS_INVALID", "not_found 必须使用 JSON null。")
            if body.status == "confirmed" and not same_as_model:
                raise _error(
                    "RESULT_STATUS_INVALID", "当前字段值不同于模型值时必须标记为 corrected。"
                )
            if body.status == "corrected" and same_as_model:
                raise _error(
                    "RESULT_STATUS_INVALID", "当前字段值等于模型值时不能标记为 corrected。"
                )
            row.current_value_json = body.current_value
        elif subject_type == "risk_finding":
            _validate_evidence_for_status(
                session, task=task, subject_type=subject_type, row=row, status=body.status
            )
            for attribute in ("title", "description", "suggestion"):
                if attribute in body.model_fields_set:
                    value = getattr(body, attribute)
                    if value is None or not value.strip():
                        raise _error("RESULT_FIELD_INVALID", "风险文本不能为空。")
                    setattr(row, attribute, value.strip())
        else:
            _validate_evidence_for_status(
                session, task=task, subject_type=subject_type, row=row, status=body.status
            )
            if "difference_summary" in body.model_fields_set:
                row.difference_summary = (
                    body.difference_summary.strip() if body.difference_summary else None
                )
            if "suggestion" in body.model_fields_set:
                if body.suggestion is None or not body.suggestion.strip():
                    raise _error("RESULT_FIELD_INVALID", "条款建议不能为空。")
                row.suggestion = body.suggestion.strip()

        row.status = body.status
        row.version += 1
        now = _now()
        row.edited_by = actor.user_id
        row.edited_at = now
        session.flush()
        after = _snapshot(
            session, organization_id=actor.organization_id, subject_type=subject_type, row=row
        )
        revision = ResultRevision(
            organization_id=actor.organization_id,
            review_task_id=task.id,
            subject_type=subject_type,
            subject_id=row.id,
            before_json=before,
            after_json=after,
            version_before=body.version,
            version_after=row.version,
            reason=body.reason.strip() if body.reason else None,
            actor_id=actor.user_id,
            created_at=now,
        )
        session.add(revision)
        session.flush()
        append_audit_log(
            session,
            actor=actor,
            action="review_result.revised",
            resource_type=subject_type,
            resource_id=row.id,
            request_id=request_id,
            after={
                "review_task_id": str(task.id),
                "subject_type": subject_type,
                "version": row.version,
                "status": row.status,
                "revision_id": str(revision.id),
            },
        )
        unit_of_work.commit()
    return _result_payload(
        session,
        organization_id=actor.organization_id,
        task_id=task.id,
        subject_type=subject_type,
        subject_id=row.id,
        revision_id=revision.id,
    )


def revise_classification(
    session: Session,
    *,
    actor: TenantContext,
    subject_id: UUID,
    body: ContractClassificationRevisionRequest,
    request_id: str,
) -> dict[str, Any]:
    return _apply_revision(
        session,
        actor=actor,
        subject_type="classification",
        subject_id=subject_id,
        body=body,
        request_id=request_id,
    )


def revise_extracted_field(
    session: Session,
    *,
    actor: TenantContext,
    subject_id: UUID,
    body: ExtractedFieldRevisionRequest,
    request_id: str,
) -> dict[str, Any]:
    return _apply_revision(
        session,
        actor=actor,
        subject_type="extracted_field",
        subject_id=subject_id,
        body=body,
        request_id=request_id,
    )


def revise_risk_finding(
    session: Session,
    *,
    actor: TenantContext,
    subject_id: UUID,
    body: RiskFindingRevisionRequest,
    request_id: str,
) -> dict[str, Any]:
    return _apply_revision(
        session,
        actor=actor,
        subject_type="risk_finding",
        subject_id=subject_id,
        body=body,
        request_id=request_id,
    )


def revise_clause_comparison(
    session: Session,
    *,
    actor: TenantContext,
    subject_id: UUID,
    body: ClauseComparisonRevisionRequest,
    request_id: str,
) -> dict[str, Any]:
    return _apply_revision(
        session,
        actor=actor,
        subject_type="clause_comparison",
        subject_id=subject_id,
        body=body,
        request_id=request_id,
    )


def completion_blockers(
    session: Session, *, organization_id: UUID, task_id: UUID
) -> list[dict[str, Any]]:
    task = session.scalar(
        select(ReviewTask).where(
            ReviewTask.organization_id == organization_id,
            ReviewTask.id == task_id,
        )
    )
    if task is None:
        raise _error("REVIEW_TASK_NOT_FOUND", "审核任务不存在。", status_code=404)
    blockers: list[dict[str, Any]] = []
    classification = session.scalar(
        select(ContractClassification).where(
            ContractClassification.organization_id == organization_id,
            ContractClassification.review_task_id == task_id,
        )
    )
    if classification is not None and classification.status == "needs_confirmation":
        blockers.append(
            {
                "subject_type": "classification",
                "subject_id": classification.id,
                "code": "CLASSIFICATION_NEEDS_CONFIRMATION",
                "status": classification.status,
                "version": classification.version,
            }
        )
    fields = session.scalars(
        select(ExtractedField).where(
            ExtractedField.organization_id == organization_id,
            ExtractedField.review_task_id == task_id,
            ExtractedField.status == "needs_confirmation",
        )
    )
    blockers.extend(
        {
            "subject_type": "extracted_field",
            "subject_id": row.id,
            "code": "FIELD_NEEDS_CONFIRMATION",
            "status": row.status,
            "version": row.version,
        }
        for row in fields
    )
    risk_rows = list(
        session.scalars(
            select(RiskFinding).where(
                RiskFinding.organization_id == organization_id,
                RiskFinding.review_task_id == task_id,
            )
        )
    )
    for row in risk_rows:
        evidence_count = _valid_evidence_ids(
            session, task=task, subject_type="risk_finding", subject_id=row.id
        )
        if row.status == "pending_review":
            blockers.append(
                {
                    "subject_type": "risk_finding",
                    "subject_id": row.id,
                    "code": "RISK_PENDING_REVIEW",
                    "status": row.status,
                    "version": row.version,
                }
            )
        if not evidence_count:
            blockers.append(
                {
                    "subject_type": "risk_finding",
                    "subject_id": row.id,
                    "code": "RISK_EVIDENCE_REQUIRED",
                    "status": row.status,
                    "version": row.version,
                }
            )
    clause_rows = session.scalars(
        select(ClauseComparison).where(
            ClauseComparison.organization_id == organization_id,
            ClauseComparison.review_task_id == task_id,
            ClauseComparison.status == "uncertain",
        )
    )
    blockers.extend(
        {
            "subject_type": "clause_comparison",
            "subject_id": row.id,
            "code": "CLAUSE_UNCERTAIN",
            "status": row.status,
            "version": row.version,
        }
        for row in clause_rows
    )
    return blockers


__all__ = [
    "completion_blockers",
    "revise_classification",
    "revise_clause_comparison",
    "revise_extracted_field",
    "revise_risk_finding",
]
