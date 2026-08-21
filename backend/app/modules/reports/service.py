from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.contracts.models import Contract, ContractFile, FileObject
from backend.app.modules.feedback.models import Feedback
from backend.app.modules.identity.models import Organization
from backend.app.modules.identity.organization import organization_settings
from backend.app.modules.reports.models import Report
from backend.app.modules.reports.renderer import (
    TEMPLATE_VERSION,
    ReportRenderer,
    ReportRendererError,
    render_html,
)
from backend.app.modules.retention.service import (
    create_file_write_journal,
    finalize_file_write_journal,
)
from backend.app.modules.reviews.models import ReviewTask
from backend.app.modules.reviews.results.service import get_review_results
from backend.app.modules.reviews.revisions.models import ResultRevision
from backend.app.observability.metrics import observe_report_outcome
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

logger = logging.getLogger(__name__)
REPORT_LEASE_SECONDS = 120
REPORT_TEMPLATE_VERSION = TEMPLATE_VERSION


def _now() -> datetime:
    return datetime.now(UTC)


def _error(code: str, message: str, *, status_code: int = 409) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message)


def _report_not_found() -> ApplicationError:
    return _error("REPORT_NOT_FOUND", "报告不存在。", status_code=404)


def _report_from_access(
    session: Session,
    *,
    organization_id: UUID,
    report_id: UUID,
    viewer_user_id: UUID | None,
    for_update: bool = False,
) -> Report:
    statement = (
        select(Report)
        .join(
            ReviewTask,
            and_(
                ReviewTask.organization_id == Report.organization_id,
                ReviewTask.id == Report.review_task_id,
            ),
        )
        .where(Report.organization_id == organization_id, Report.id == report_id)
    )
    if viewer_user_id is not None:
        from backend.app.modules.contracts.models import ContractAccessGrant

        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == ReviewTask.organization_id,
                ContractAccessGrant.contract_id == ReviewTask.contract_id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    if for_update:
        statement = statement.with_for_update()
    report = session.scalar(statement)
    if report is None:
        raise _report_not_found()
    return report


def _next_display_no(session: Session) -> str:
    value = session.execute(text("SELECT nextval('report_display_no_seq')")).scalar_one()
    return f"RPT-{_now().strftime('%Y%m%d')}-{int(value):06d}"


def _snapshot_rows(
    session: Session, *, organization_id: UUID, task_id: UUID
) -> dict[str, list[dict[str, Any]]]:
    revisions = list(
        session.scalars(
            select(ResultRevision)
            .where(
                ResultRevision.organization_id == organization_id,
                ResultRevision.review_task_id == task_id,
            )
            .order_by(ResultRevision.created_at, ResultRevision.id)
        )
    )
    feedback = list(
        session.scalars(
            select(Feedback)
            .where(Feedback.organization_id == organization_id, Feedback.review_task_id == task_id)
            .order_by(Feedback.created_at, Feedback.id)
        )
    )
    return {
        "revisions": [
            {
                "id": row.id,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "before_json": row.before_json,
                "after_json": row.after_json,
                "version_before": row.version_before,
                "version_after": row.version_after,
                "reason": row.reason,
                "actor_id": row.actor_id,
                "created_at": row.created_at,
            }
            for row in revisions
        ],
        "feedback": [
            {
                "id": row.id,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "label": row.label,
                "corrected_value": row.corrected_value,
                "note": row.note,
                "created_by": row.created_by,
                "created_at": row.created_at,
            }
            for row in feedback
        ],
    }


def _build_snapshot(
    session: Session,
    *,
    organization: Organization,
    task: ReviewTask,
    report_id: UUID,
    display_no: str,
    report_format: str,
) -> dict[str, Any]:
    contract = session.scalar(
        select(Contract).where(
            Contract.organization_id == organization.id,
            Contract.id == task.contract_id,
        )
    )
    file_row = session.execute(
        select(ContractFile, FileObject)
        .join(
            FileObject,
            and_(
                FileObject.organization_id == ContractFile.organization_id,
                FileObject.id == ContractFile.file_object_id,
            ),
        )
        .where(
            ContractFile.organization_id == organization.id,
            ContractFile.id == task.contract_file_id,
        )
    ).one_or_none()
    document = None
    if task.document_version_id is not None:
        from backend.app.modules.documents.models import DocumentVersion

        document = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == organization.id,
                DocumentVersion.id == task.document_version_id,
            )
        )
    if contract is None or file_row is None or document is None:
        raise _error("REPORT_TASK_INPUT_NOT_READY", "报告所需的审核输入尚未准备完成。")
    contract_file, file_object = file_row
    results = get_review_results(
        session,
        organization_id=organization.id,
        task_id=task.id,
        viewer_user_id=None,
        include_evidence=True,
    )
    settings = organization_settings(organization)
    snapshot: dict[str, Any] = {
        "snapshot_version": "report-snapshot-v1",
        "captured_at": _now(),
        "report": {
            "id": report_id,
            "display_no": display_no,
            "format": report_format,
            "template_version": REPORT_TEMPLATE_VERSION,
        },
        "organization": {
            "id": organization.id,
            "name": organization.name,
            "report_watermark": settings["report_watermark"],
            "retention_days": organization.retention_days,
        },
        "contract": {
            "id": contract.id,
            "display_no": contract.display_no,
            "title": contract.title,
            "declared_type": contract.declared_type,
        },
        "file": {
            "id": file_object.id,
            "original_name": file_object.original_name,
            "media_type": file_object.media_type,
            "size_bytes": file_object.size_bytes,
            "sha256": file_object.sha256,
            "version_no": contract_file.version_no,
        },
        "document": {
            "id": document.id,
            "parser_name": document.parser_name,
            "parser_version": document.parser_version,
            "page_count": document.page_count,
            "text_sha256": document.text_sha256,
        },
        "review_task": {
            "id": task.id,
            "display_no": task.display_no,
            "status": task.status,
            "business_scenario": task.business_scenario,
            "rule_bundle_version_id": task.rule_bundle_version_id,
            "clause_template_version_id": task.clause_template_version_id,
            "completed_by": task.completed_by,
            "completed_at": task.completed_at,
        },
        "results": results,
        "human_review": _snapshot_rows(
            session, organization_id=organization.id, task_id=task.id
        ),
        "disclaimer": (
            "本报告由智能分析引擎生成，旨在辅助专业人员进行风险识别，不能替代独立法律意见。"
            "请结合实际业务场景与人工复核进行最终决策。"
        ),
    }
    return cast(dict[str, Any], jsonable_encoder(snapshot))


def report_payload(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "display_no": report.display_no,
        "review_task_id": report.review_task_id,
        "format": report.format,
        "status": report.status,
        "template_version": report.template_version,
        "created_at": report.created_at,
        "generated_at": report.generated_at,
        "expires_at": report.expires_at,
        "download_available": report.status == "ready" and report.file_object_id is not None,
        "error_code": report.error_code,
    }


def create_report(
    session: Session,
    *,
    actor: TenantContext,
    task_id: UUID,
    report_format: str,
    idempotency_key: str,
    request_id: str,
    renderer: ReportRenderer,
) -> tuple[Report, bool]:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/review-tasks/{review_task_id}/reports",
        path={"review_task_id": task_id},
        body={"format": report_format},
    )
    created: Report | None = None
    replayed = False
    with UnitOfWork(session) as unit_of_work:
        def operation() -> IdempotencyResult:
            nonlocal created
            if not renderer.available(report_format):
                raise ApplicationError(
                    status_code=503,
                    code="REPORT_RENDERER_UNAVAILABLE",
                    message="报告渲染服务暂时不可用。",
                )
            organization = session.scalar(
                select(Organization)
                .where(Organization.id == actor.organization_id, Organization.status == "active")
                .with_for_update()
            )
            task = session.scalar(
                select(ReviewTask)
                .where(
                    ReviewTask.organization_id == actor.organization_id,
                    ReviewTask.id == task_id,
                )
                .with_for_update()
            )
            if organization is None or task is None:
                raise _error("REVIEW_TASK_NOT_FOUND", "审核任务不存在。", status_code=404)
            if task.status not in {"pending_review", "completed"}:
                raise _error("REVIEW_TASK_NOT_READY", "当前审核任务尚不能生成报告。")
            generating = session.scalar(
                select(Report.id).where(
                    Report.organization_id == actor.organization_id,
                    Report.review_task_id == task.id,
                    Report.format == report_format,
                    Report.status == "generating",
                )
            )
            if generating is not None:
                raise _error("REPORT_ALREADY_GENERATING", "该格式的报告正在生成。")
            limit = int(organization_settings(organization)["concurrent_review_limit"])
            active_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(Report)
                    .where(
                        Report.organization_id == actor.organization_id,
                        Report.status == "generating",
                    )
                )
                or 0
            )
            if active_count >= limit:
                raise ApplicationError(
                    status_code=429,
                    code="CONCURRENCY_LIMIT_EXCEEDED",
                    message="报告生成并发数已达到组织上限。",
                )
            report_id = uuid4()
            display_no = _next_display_no(session)
            report = Report(
                id=report_id,
                organization_id=actor.organization_id,
                review_task_id=task.id,
                display_no=display_no,
                format=report_format,
                status="generating",
                snapshot_json=_build_snapshot(
                    session,
                    organization=organization,
                    task=task,
                    report_id=report_id,
                    display_no=display_no,
                    report_format=report_format,
                ),
                template_version=REPORT_TEMPLATE_VERSION,
            )
            session.add(report)
            session.flush()
            append_audit_log(
                session,
                actor=actor,
                action="report.created",
                resource_type="report",
                resource_id=report.id,
                request_id=request_id,
                after={
                    "review_task_id": str(task.id),
                    "format": report.format,
                    "status": report.status,
                    "template_version": report.template_version,
                },
            )
            created = report
            return IdempotencyResult(202, "report", report.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/review-tasks/{review_task_id}/reports",
            fingerprint=fingerprint,
            operation=operation,
        )
        replayed = result.replayed
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("report idempotency record has no resource")
            created = session.scalar(
                select(Report).where(
                    Report.organization_id == actor.organization_id,
                    Report.id == result.resource_id,
                )
            )
            if created is None:
                raise _report_not_found()
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("report creation returned no resource")
    if not replayed:
        _enqueue_report(created.id)
    return created, replayed


def _enqueue_report(report_id: UUID) -> None:
    try:
        from backend.app.worker.reports import run_report

        run_report.delay(str(report_id))
    except Exception as exc:  # Redis is a broker; lease recovery keeps the fact visible.
        logger.warning(
            "report_enqueue_failed",
            extra={"report_id": str(report_id), "error_class": type(exc).__name__},
        )


def get_report(
    session: Session,
    *,
    organization_id: UUID,
    report_id: UUID,
    viewer_user_id: UUID | None,
) -> dict[str, Any]:
    with UnitOfWork(session) as unit_of_work:
        report = _report_from_access(
            session,
            organization_id=organization_id,
            report_id=report_id,
            viewer_user_id=viewer_user_id,
            for_update=True,
        )
        if (
            report.status == "ready"
            and report.expires_at is not None
            and _now() >= report.expires_at
        ):
            report.status = "expired"
            report.finished_at = _now()
        unit_of_work.commit()
    return report_payload(report)


def get_report_download(
    session: Session,
    *,
    organization_id: UUID,
    report_id: UUID,
    viewer_user_id: UUID | None,
    file_store: LocalFileStore,
) -> tuple[Report, FileObject]:
    expired = False
    with UnitOfWork(session) as unit_of_work:
        report = _report_from_access(
            session,
            organization_id=organization_id,
            report_id=report_id,
            viewer_user_id=viewer_user_id,
            for_update=True,
        )
        if (
            report.status == "ready"
            and report.expires_at is not None
            and _now() >= report.expires_at
        ):
            report.status = "expired"
            report.finished_at = _now()
            expired = True
        elif report.status == "expired":
            expired = True
        if not expired and report.status != "ready":
            raise _error("REPORT_NOT_READY", "报告尚未准备好下载。")
        file_object = None
        if not expired and report.file_object_id is not None:
            file_object = session.scalar(
                select(FileObject).where(
                    FileObject.organization_id == organization_id,
                    FileObject.id == report.file_object_id,
                )
            )
        if not expired and (file_object is None or file_object.storage_status != "stored"):
            raise _error("REPORT_NOT_READY", "报告尚未准备好下载。")
        unit_of_work.commit()
    if expired:
        raise ApplicationError(
            status_code=410, code="REPORT_EXPIRED", message="报告已过期，请重新生成。"
        )
    if file_object is None:
        raise _error("REPORT_NOT_READY", "报告尚未准备好下载。")
    if not file_store.exists(file_object.storage_key):
        raise _error("REPORT_NOT_READY", "报告尚未准备好下载。")
    return report, file_object


def _report_storage_key(*, organization_id: UUID, report_id: UUID, report_format: str) -> str:
    return f"reports/{organization_id}/{report_id}/{secrets.token_urlsafe(32)}.{report_format}"


def _claim_report(
    session: Session, report_id: UUID
) -> tuple[UUID, str, dict[str, Any], str] | None:
    owner = f"report-worker-{uuid4()}"
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        report = session.scalar(select(Report).where(Report.id == report_id).with_for_update())
        if report is None or report.status != "generating":
            return None
        if report.lease_expires_at is not None and report.lease_expires_at > now:
            return None
        report.lease_owner = owner
        report.lease_expires_at = now + timedelta(seconds=REPORT_LEASE_SECONDS)
        report.heartbeat_at = now
        report.started_at = report.started_at or now
        unit_of_work.commit()
        return report.organization_id, report.format, report.snapshot_json, owner


def _fail_report(session: Session, report_id: UUID, owner: str, code: str) -> None:
    with UnitOfWork(session) as unit_of_work:
        report = session.scalar(
            select(Report)
            .where(Report.id == report_id, Report.lease_owner == owner)
            .with_for_update()
        )
        if report is not None and report.status == "generating":
            report.status = "failed"
            observe_report_outcome("failed")
            report.error_code = code
            report.error_message = "报告生成失败，请使用新的幂等键重新生成。"
            report.finished_at = _now()
            report.lease_owner = None
            report.lease_expires_at = None
            report.heartbeat_at = None
        unit_of_work.commit()


def process_report(
    session: Session,
    *,
    report_id: UUID,
    file_store: LocalFileStore,
    renderer: ReportRenderer,
) -> None:
    claim = _claim_report(session, report_id)
    if claim is None:
        return
    organization_id, report_format, snapshot, owner = claim
    storage_key: str | None = None
    committed = False
    try:
        html = render_html(snapshot)
        content = html.encode("utf-8")
        if report_format == "pdf":
            content = renderer.render_pdf(html)
        storage_key = _report_storage_key(
            organization_id=organization_id,
            report_id=report_id,
            report_format=report_format,
        )
        write_operation_id = create_file_write_journal(
            session,
            organization_id=organization_id,
            storage_key=storage_key,
        )
        size_bytes, sha256 = file_store.put(BytesIO(content), storage_key)
        with UnitOfWork(session) as unit_of_work:
            report = session.scalar(
                select(Report)
                .where(Report.id == report_id, Report.lease_owner == owner)
                .with_for_update()
            )
            if report is None or report.status != "generating":
                unit_of_work.rollback()
            else:
                now = _now()
                retention_days = int(snapshot["organization"]["retention_days"])
                file_object = FileObject(
                    id=uuid4(),
                    organization_id=organization_id,
                    storage_key=storage_key,
                    original_name=f"{report.display_no}.{report_format}",
                    media_type="text/html; charset=utf-8"
                    if report_format == "html"
                    else "application/pdf",
                    size_bytes=size_bytes,
                    sha256=sha256,
                    scan_status="clean",
                    storage_status="stored",
                )
                session.add(file_object)
                session.flush()
                finalize_file_write_journal(
                    session,
                    operation_id=write_operation_id,
                    file_object_id=file_object.id,
                )
                report.file_object_id = file_object.id
                report.status = "ready"
                observe_report_outcome("ready")
                report.generated_at = now
                report.expires_at = now + timedelta(days=retention_days)
                report.finished_at = now
                report.error_code = None
                report.error_message = None
                report.lease_owner = None
                report.lease_expires_at = None
                report.heartbeat_at = None
                unit_of_work.commit()
                committed = True
    except ReportRendererError as exc:
        _fail_report(session, report_id, owner, exc.code)
    except Exception:
        logger.exception(
            "report_processing_failed",
            extra={"report_id": str(report_id), "error_class": "unexpected"},
        )
        _fail_report(session, report_id, owner, "REPORT_RENDER_FAILED")
    finally:
        if storage_key is not None and not committed:
            file_store.delete(storage_key)


def recover_expired_report_leases(session: Session) -> list[UUID]:
    now = _now()
    cutoff = now - timedelta(seconds=REPORT_LEASE_SECONDS)
    recovered: list[UUID] = []
    with UnitOfWork(session) as unit_of_work:
        reports = list(
            session.scalars(
                select(Report)
                .where(
                    Report.status == "generating",
                    or_(
                        Report.lease_expires_at <= now,
                        and_(Report.lease_expires_at.is_(None), Report.created_at <= cutoff),
                    ),
                )
                .with_for_update(skip_locked=True)
            )
        )
        for report in reports:
            report.status = "failed"
            report.error_code = "REPORT_WORKER_LEASE_EXPIRED"
            report.error_message = "报告生成任务未完成，请使用新的幂等键重新生成。"
            report.finished_at = now
            report.lease_owner = None
            report.lease_expires_at = None
            report.heartbeat_at = None
            recovered.append(report.id)
        unit_of_work.commit()
    return recovered


__all__ = [
    "REPORT_LEASE_SECONDS",
    "create_report",
    "get_report",
    "get_report_download",
    "process_report",
    "recover_expired_report_leases",
    "report_payload",
]
