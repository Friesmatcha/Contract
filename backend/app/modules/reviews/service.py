import hashlib
import json
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.integrations.model.schemas import (
    DEFAULT_PROMPT_VERSION,
    DEFAULT_SANITIZATION_POLICY_VERSION,
    DEFAULT_SCHEMA_VERSION,
)
from backend.app.modules.clauses.templates.models import ClauseTemplate, ClauseTemplateVersion
from backend.app.modules.contracts.models import Contract, ContractFile, FileObject
from backend.app.modules.documents.models import DocumentVersion
from backend.app.modules.identity.models import Organization, PlatformModelConfiguration
from backend.app.modules.identity.organization import organization_settings
from backend.app.modules.reviews.models import (
    ACTIVE_REVIEW_STATUSES,
    REVIEW_STAGES,
    WORKER_REQUEUE_STATUSES,
    ReviewStageRun,
    ReviewTask,
)
from backend.app.modules.reviews.schemas import CreateReviewTaskRequest, RetryReviewTaskRequest
from backend.app.modules.risks.rules.models import RiskRuleBundle, RiskRuleBundleVersion
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
LEASE_SECONDS = 60
REVIEW_TASK_MAX_RETRIES = 3
PROMPT_BUNDLE_VERSION = DEFAULT_PROMPT_VERSION
_STAGE_ERROR_CODE = "STAGE_EXECUTION_FAILED"


class StageExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class StageExecutor(Protocol):
    def execute(self, stage: str, heartbeat: Callable[[], None]) -> None: ...

    def compensate(self, stage: str) -> None: ...


class FakeStageExecutor:
    """Deterministic orchestration executor; it never calls a model integration."""

    def __init__(self, *, failing_stages: Iterable[str] = ()) -> None:
        self.failing_stages = set(failing_stages)
        self.executed_stages: list[str] = []
        self.compensated_stages: list[str] = []

    def execute(self, stage: str, heartbeat: Callable[[], None]) -> None:
        heartbeat()
        self.executed_stages.append(stage)
        if stage in self.failing_stages:
            raise StageExecutionError(_STAGE_ERROR_CODE, "阶段执行失败，请重试。")

    def compensate(self, stage: str) -> None:
        self.compensated_stages.append(stage)


def _now() -> datetime:
    return datetime.now(UTC)


def _error(code: str, message: str, *, status_code: int = 409) -> ApplicationError:
    return ApplicationError(status_code=status_code, code=code, message=message)


def _task_or_not_found(
    session: Session, *, organization_id: UUID, task_id: UUID, for_update: bool = False
) -> ReviewTask:
    statement = select(ReviewTask).where(
        ReviewTask.organization_id == organization_id,
        ReviewTask.id == task_id,
    )
    if for_update:
        statement = statement.with_for_update()
    task = session.scalar(statement)
    if task is None:
        raise _error("REVIEW_TASK_NOT_FOUND", "审核任务不存在。", status_code=404)
    return task


def _stage_order(stage: str) -> int:
    return REVIEW_STAGES.index(stage)


def _latest_stage_runs(session: Session, task: ReviewTask) -> list[ReviewStageRun]:
    return list(
        session.scalars(
            select(ReviewStageRun)
            .where(
                ReviewStageRun.organization_id == task.organization_id,
                ReviewStageRun.review_task_id == task.id,
            )
            .order_by(ReviewStageRun.created_at, ReviewStageRun.stage, ReviewStageRun.attempt_no)
        )
    )


def _latest_run_by_stage(session: Session, task: ReviewTask) -> dict[str, ReviewStageRun]:
    latest: dict[str, ReviewStageRun] = {}
    for run in _latest_stage_runs(session, task):
        previous = latest.get(run.stage)
        if previous is None or run.attempt_no > previous.attempt_no:
            latest[run.stage] = run
    return latest


def _stage_fingerprint(task: ReviewTask, stage: str) -> str:
    return hashlib.sha256(f"{task.input_fingerprint}:{stage}".encode()).hexdigest()


def _next_attempt(latest: dict[str, ReviewStageRun], stage: str) -> int:
    run = latest.get(stage)
    return 1 if run is None else run.attempt_no + 1


def _next_display_no(session: Session) -> str:
    sequence_value = session.execute(text("SELECT nextval('review_display_no_seq')")).scalar_one()
    return f"REV-{_now().strftime('%Y%m%d')}-{int(sequence_value):06d}"


def _normalize_scenario(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized or "standard"


def _published_rule_version(
    session: Session,
    *,
    organization_id: UUID,
    requested_id: UUID | None,
) -> RiskRuleBundleVersion:
    if requested_id is not None:
        version = session.scalar(
            select(RiskRuleBundleVersion).where(
                RiskRuleBundleVersion.organization_id == organization_id,
                RiskRuleBundleVersion.id == requested_id,
            )
        )
        if version is None or version.status != "published":
            raise _error("VERSION_NOT_PUBLISHED", "所选风险规则版本未发布。")
        bundle = session.scalar(
            select(RiskRuleBundle).where(
                RiskRuleBundle.organization_id == organization_id,
                RiskRuleBundle.id == version.bundle_id,
            )
        )
        if bundle is None or bundle.status != "active":
            raise _error("VERSION_NOT_PUBLISHED", "所选风险规则版本当前不可用。")
        return version

    bundle = session.scalar(
        select(RiskRuleBundle)
        .where(
            RiskRuleBundle.organization_id == organization_id,
            RiskRuleBundle.is_default.is_(True),
            RiskRuleBundle.status == "active",
        )
        .with_for_update()
    )
    if bundle is None or bundle.current_published_version_id is None:
        raise _error(
            "DEFAULT_RISK_RULE_BUNDLE_NOT_CONFIGURED", "当前组织尚未配置默认风险规则版本。"
        )
    version = session.scalar(
        select(RiskRuleBundleVersion).where(
            RiskRuleBundleVersion.organization_id == organization_id,
            RiskRuleBundleVersion.id == bundle.current_published_version_id,
            RiskRuleBundleVersion.status == "published",
        )
    )
    if version is None:
        raise _error(
            "DEFAULT_RISK_RULE_BUNDLE_NOT_CONFIGURED", "当前组织尚未配置默认风险规则版本。"
        )
    return version


def _published_clause_version(
    session: Session,
    *,
    organization_id: UUID,
    contract_type: str | None,
    business_scenario: str,
    requested_id: UUID | None,
) -> ClauseTemplateVersion:
    if contract_type not in {"purchase", "sales", "nda", "outsourcing", "employment"}:
        raise _error("DEFAULT_VERSION_NOT_APPLICABLE", "当前合同类型没有适用的条款模板版本。")
    if requested_id is not None:
        version = session.scalar(
            select(ClauseTemplateVersion).where(
                ClauseTemplateVersion.organization_id == organization_id,
                ClauseTemplateVersion.id == requested_id,
            )
        )
        if version is None or version.status != "published":
            raise _error("VERSION_NOT_PUBLISHED", "所选条款模板版本未发布。")
        template = session.scalar(
            select(ClauseTemplate).where(
                ClauseTemplate.organization_id == organization_id,
                ClauseTemplate.id == version.template_id,
            )
        )
        if (
            template is None
            or template.status != "active"
            or template.contract_type != contract_type
            or template.business_scenario != business_scenario
        ):
            raise _error("DEFAULT_VERSION_NOT_APPLICABLE", "所选条款模板版本不适用于当前合同。")
        return version

    template = session.scalar(
        select(ClauseTemplate)
        .where(
            ClauseTemplate.organization_id == organization_id,
            ClauseTemplate.contract_type == contract_type,
            ClauseTemplate.business_scenario == business_scenario,
            ClauseTemplate.is_default.is_(True),
            ClauseTemplate.status == "active",
        )
        .with_for_update()
    )
    if template is None or template.current_published_version_id is None:
        raise _error(
            "DEFAULT_CLAUSE_TEMPLATE_NOT_CONFIGURED", "当前合同类型和场景尚未配置默认条款模板。"
        )
    version = session.scalar(
        select(ClauseTemplateVersion).where(
            ClauseTemplateVersion.organization_id == organization_id,
            ClauseTemplateVersion.id == template.current_published_version_id,
            ClauseTemplateVersion.status == "published",
        )
    )
    if version is None:
        raise _error(
            "DEFAULT_CLAUSE_TEMPLATE_NOT_CONFIGURED", "当前合同类型和场景尚未配置默认条款模板。"
        )
    return version


def _select_document(
    session: Session,
    *,
    organization_id: UUID,
    contract_file_id: UUID,
    requested_id: UUID | None,
) -> DocumentVersion | None:
    if requested_id is not None:
        document = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.id == requested_id,
            )
        )
        if document is None or document.contract_file_id != contract_file_id:
            raise _error("DOCUMENT_NOT_FOUND", "文档版本不存在。", status_code=404)
        if document.status != "succeeded":
            raise _error("DOCUMENT_NOT_READY", "文档版本尚未解析完成。")
        return document
    return session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.organization_id == organization_id,
            DocumentVersion.contract_file_id == contract_file_id,
            DocumentVersion.status == "succeeded",
        )
        .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
    )


def _model_config_snapshot(
    session: Session, settings: Settings | None
) -> dict[str, Any]:
    configuration = session.scalar(
        select(PlatformModelConfiguration).where(PlatformModelConfiguration.singleton_key == 1)
    )
    return {
        "provider": settings.model_provider if settings is not None else "qwen",
        "model": settings.model_name if settings is not None else None,
        "model_source": "environment",
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "sanitization_policy_version": DEFAULT_SANITIZATION_POLICY_VERSION,
        "timeout_seconds": configuration.timeout_seconds if configuration else 60,
        "max_retries": configuration.max_retries if configuration else 3,
        "usage_tracking_enabled": configuration.usage_tracking_enabled if configuration else True,
        "organization_overrides_allowed": False,
        "secret_configured": bool(settings and settings.model_api_key is not None),
        "status": configuration.status if configuration else "active",
        "configuration_version": configuration.version if configuration else 0,
    }


def _input_snapshot(
    *,
    contract: Contract,
    contract_file: ContractFile,
    file_object: FileObject,
    document: DocumentVersion | None,
    rule_version: RiskRuleBundleVersion,
    clause_version: ClauseTemplateVersion,
    business_scenario: str,
) -> dict[str, Any]:
    return {
        "contract_id": str(contract.id),
        "contract_version": contract.version,
        "contract_file_id": str(contract_file.id),
        "file_version_no": contract_file.version_no,
        "file_sha256": file_object.sha256,
        "document_version_id": str(document.id) if document else None,
        "document_parse_fingerprint": document.parse_fingerprint if document else None,
        "rule_bundle_version_id": str(rule_version.id),
        "clause_template_version_id": str(clause_version.id),
        "business_scenario": business_scenario,
        "external_model_notice_acknowledged_at": (
            contract_file.external_model_notice_acknowledged_at.isoformat()
        ),
    }


def _fingerprint_snapshot(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def create_review_task(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    body: CreateReviewTaskRequest,
    idempotency_key: str,
    request_id: str,
    settings: Settings | None = None,
) -> ReviewTask:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/contracts/{contract_id}/reviews",
        path={"contract_id": contract_id},
        body=body.model_dump(mode="json"),
    )
    created: ReviewTask | None = None
    with UnitOfWork(session) as unit_of_work:
        def operation() -> IdempotencyResult:
            nonlocal created
            organization = session.scalar(
                select(Organization)
                .where(Organization.id == actor.organization_id)
                .with_for_update()
            )
            if organization is None or organization.status != "active":
                raise _error("ORGANIZATION_NOT_FOUND", "组织不存在。", status_code=404)
            contract = session.scalar(
                select(Contract)
                .where(
                    Contract.organization_id == actor.organization_id,
                    Contract.id == contract_id,
                )
                .with_for_update()
            )
            if contract is None:
                raise _error("CONTRACT_NOT_FOUND", "合同不存在。", status_code=404)
            if contract.status == "archived":
                raise _error("CONTRACT_ARCHIVED", "归档合同不能创建审核任务。")
            active = session.scalar(
                select(ReviewTask).where(
                    ReviewTask.organization_id == actor.organization_id,
                    ReviewTask.contract_id == contract.id,
                    ReviewTask.status.in_(ACTIVE_REVIEW_STATUSES),
                )
            )
            if active is not None:
                raise _error("ACTIVE_REVIEW_EXISTS", "合同已有正在处理的审核任务。")
            active_count = session.scalar(
                select(func.count())
                .select_from(ReviewTask)
                .where(
                    ReviewTask.organization_id == actor.organization_id,
                    ReviewTask.status.in_(ACTIVE_REVIEW_STATUSES),
                )
            )
            limit = int(organization_settings(organization)["concurrent_review_limit"])
            if active_count is not None and active_count >= limit:
                raise _error(
                    "CONCURRENCY_LIMIT_EXCEEDED",
                    "当前组织审核任务已达到并发上限，请稍后重试。",
                    status_code=429,
                )
            contract_file_row = session.execute(
                select(ContractFile, FileObject)
                .join(
                    FileObject,
                    and_(
                        FileObject.organization_id == ContractFile.organization_id,
                        FileObject.id == ContractFile.file_object_id,
                    ),
                )
                .where(
                    ContractFile.organization_id == actor.organization_id,
                    ContractFile.id == body.contract_file_id,
                    ContractFile.contract_id == contract.id,
                )
                .with_for_update()
            ).one_or_none()
            if contract_file_row is None:
                raise _error("CONTRACT_FILE_NOT_FOUND", "合同文件版本不存在。", status_code=404)
            contract_file, file_object = contract_file_row
            if file_object.scan_status != "clean" or file_object.storage_status != "stored":
                raise _error("CONTRACT_FILE_NOT_READY", "合同文件尚未准备好审核。")
            if contract_file.external_model_notice_acknowledged_at is None:
                raise _error(
                    "EXTERNAL_MODEL_NOTICE_NOT_ACKNOWLEDGED",
                    "请先确认外部模型数据使用告知。",
                    status_code=422,
                )
            document = _select_document(
                session,
                organization_id=actor.organization_id,
                contract_file_id=contract_file.id,
                requested_id=body.document_version_id,
            )
            rule_version = _published_rule_version(
                session,
                organization_id=actor.organization_id,
                requested_id=body.rule_bundle_version_id,
            )
            business_scenario = _normalize_scenario(body.business_scenario)
            clause_version = _published_clause_version(
                session,
                organization_id=actor.organization_id,
                contract_type=contract.declared_type,
                business_scenario=business_scenario,
                requested_id=body.clause_template_version_id,
            )
            snapshot = _input_snapshot(
                contract=contract,
                contract_file=contract_file,
                file_object=file_object,
                document=document,
                rule_version=rule_version,
                clause_version=clause_version,
                business_scenario=business_scenario,
            )
            task = ReviewTask(
                id=uuid4(),
                organization_id=actor.organization_id,
                contract_id=contract.id,
                contract_file_id=contract_file.id,
                document_version_id=document.id if document else None,
                rule_bundle_version_id=rule_version.id,
                clause_template_version_id=clause_version.id,
                created_by=actor.user_id,
                display_no=_next_display_no(session),
                business_scenario=business_scenario,
                prompt_bundle_version=PROMPT_BUNDLE_VERSION,
                model_config_json=_model_config_snapshot(session, settings),
                input_snapshot_json=snapshot,
                input_fingerprint=_fingerprint_snapshot(snapshot),
            )
            session.add(task)
            session.flush()
            session.add(
                ReviewStageRun(
                    id=uuid4(),
                    organization_id=actor.organization_id,
                    review_task_id=task.id,
                    stage=REVIEW_STAGES[0],
                    attempt_no=1,
                    status="pending",
                    input_fingerprint=_stage_fingerprint(task, REVIEW_STAGES[0]),
                )
            )
            append_audit_log(
                session,
                actor=actor,
                action="review_task.created",
                resource_type="review_task",
                resource_id=task.id,
                request_id=request_id,
                after={
                    "contract_id": str(task.contract_id),
                    "contract_file_id": str(task.contract_file_id),
                    "document_version_id": str(task.document_version_id)
                    if task.document_version_id
                    else None,
                    "rule_bundle_version_id": str(task.rule_bundle_version_id),
                    "clause_template_version_id": str(task.clause_template_version_id),
                    "status": task.status,
                },
            )
            created = task
            return IdempotencyResult(202, "review_task", task.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/contracts/{contract_id}/reviews",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("review task idempotency record has no resource")
            created = _task_or_not_found(
                session,
                organization_id=actor.organization_id,
                task_id=result.resource_id,
            )
        unit_of_work.commit()
    if created is None:
        raise RuntimeError("review task creation returned no resource")
    _enqueue_review_task(created.id)
    return created


def _enqueue_review_task(task_id: UUID) -> None:
    try:
        from backend.app.worker.review_tasks import run_review_task

        run_review_task.delay(str(task_id))
    except Exception as exc:  # Redis is a broker, so database compensation can retry it.
        logger.warning(
            "review_task_enqueue_failed",
            extra={"task_id": str(task_id), "error_class": type(exc).__name__},
        )


def complete_review_task(
    session: Session,
    *,
    actor: TenantContext,
    task_id: UUID,
    note: str | None,
    idempotency_key: str,
    request_id: str,
) -> ReviewTask:
    from backend.app.modules.reviews.revisions.service import completion_blockers

    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/review-tasks/{review_task_id}/complete",
        path={"review_task_id": task_id},
        body={"note": note},
    )
    completed: ReviewTask | None = None
    with UnitOfWork(session) as unit_of_work:
        def operation() -> IdempotencyResult:
            nonlocal completed
            task = _task_or_not_found(
                session,
                organization_id=actor.organization_id,
                task_id=task_id,
                for_update=True,
            )
            if task.status != "pending_review":
                raise _error(
                    "INVALID_STATE_TRANSITION",
                    "仅等待人工复核的任务可以完成审核。",
                    status_code=409,
                )
            blockers = completion_blockers(
                session,
                organization_id=actor.organization_id,
                task_id=task.id,
            )
            if blockers:
                raise ApplicationError(
                    status_code=409,
                    code="UNRESOLVED_REQUIRED_FINDINGS",
                    message="仍有必须人工处理的审核结果。",
                    details={
                        "blockers": [
                            {
                                **blocker,
                                "subject_id": str(blocker["subject_id"]),
                            }
                            for blocker in blockers
                        ]
                    },
                )
            now = _now()
            task.status = "completed"
            task.completed_by = actor.user_id
            task.completed_at = now
            task.error_code = None
            task.error_message = None
            append_audit_log(
                session,
                actor=actor,
                action="review_task.completed",
                resource_type="review_task",
                resource_id=task.id,
                request_id=request_id,
                after={
                    "status": task.status,
                    "completed_by": str(actor.user_id),
                    "completed_at": now.isoformat(),
                    "has_note": bool(note and note.strip()),
                },
            )
            completed = task
            return IdempotencyResult(200, "review_task", task.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/review-tasks/{review_task_id}/complete",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            if result.resource_id is None:
                raise RuntimeError("review completion idempotency record has no resource")
            completed = _task_or_not_found(
                session,
                organization_id=actor.organization_id,
                task_id=result.resource_id,
            )
        unit_of_work.commit()
    if completed is None:
        raise RuntimeError("review completion returned no resource")
    return completed


def review_task_payload(
    session: Session, task: ReviewTask, *, include_stage_runs: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": task.id,
        "display_no": task.display_no,
        "contract_id": task.contract_id,
        "contract_file_id": task.contract_file_id,
        "document_version_id": task.document_version_id,
        "status": task.status,
        "progress": task.progress,
        "current_stage": task.current_stage,
        "rule_bundle_version_id": task.rule_bundle_version_id,
        "clause_template_version_id": task.clause_template_version_id,
        "business_scenario": task.business_scenario,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "completed_by": task.completed_by,
        "completed_at": task.completed_at,
    }
    if include_stage_runs:
        payload["stage_runs"] = [
            {
                "id": run.id,
                "stage": run.stage,
                "status": run.status,
                "attempt_no": run.attempt_no,
                "heartbeat_at": run.heartbeat_at,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "error_code": run.error_code,
                "error_message": run.error_message,
            }
            for run in _latest_stage_runs(session, task)
        ]
    return payload


def get_review_task(
    session: Session,
    *,
    organization_id: UUID,
    task_id: UUID,
    viewer_user_id: UUID | None,
    include_stage_runs: bool,
) -> dict[str, Any]:
    statement = select(ReviewTask).where(
        ReviewTask.organization_id == organization_id,
        ReviewTask.id == task_id,
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
    task = session.scalar(statement)
    if task is None:
        raise _error("REVIEW_TASK_NOT_FOUND", "审核任务不存在。", status_code=404)
    return review_task_payload(session, task, include_stage_runs=include_stage_runs)


def _verify_locked_inputs(session: Session, task: ReviewTask) -> None:
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
            ContractFile.organization_id == task.organization_id,
            ContractFile.id == task.contract_file_id,
        )
    ).one_or_none()
    snapshot = task.input_snapshot_json
    if file_row is None or file_row[1].sha256 != snapshot.get("file_sha256"):
        raise _error("INPUT_VERSION_CHANGED", "审核输入版本已变化，不能重试。")
    if task.document_version_id is not None:
        document = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == task.organization_id,
                DocumentVersion.id == task.document_version_id,
            )
        )
        if document is None or document.parse_fingerprint != snapshot.get(
            "document_parse_fingerprint"
        ):
            raise _error("INPUT_VERSION_CHANGED", "审核输入版本已变化，不能重试。")
    rule_version = session.scalar(
        select(RiskRuleBundleVersion).where(
            RiskRuleBundleVersion.organization_id == task.organization_id,
            RiskRuleBundleVersion.id == task.rule_bundle_version_id,
            RiskRuleBundleVersion.status == "published",
        )
    )
    if rule_version is None or str(rule_version.id) != snapshot.get("rule_bundle_version_id"):
        raise _error("INPUT_VERSION_CHANGED", "审核输入版本已变化，不能重试。")
    clause_version = session.scalar(
        select(ClauseTemplateVersion).where(
            ClauseTemplateVersion.organization_id == task.organization_id,
            ClauseTemplateVersion.id == task.clause_template_version_id,
            ClauseTemplateVersion.status == "published",
        )
    )
    if clause_version is None or str(clause_version.id) != snapshot.get(
        "clause_template_version_id"
    ):
        raise _error("INPUT_VERSION_CHANGED", "审核输入版本已变化，不能重试。")


def retry_review_task(
    session: Session,
    *,
    actor: TenantContext,
    task_id: UUID,
    body: RetryReviewTaskRequest,
    idempotency_key: str,
    request_id: str,
    settings: Settings | None = None,
) -> tuple[ReviewTask, str]:
    fingerprint = request_fingerprint(
        method="POST",
        operation_key="POST /api/v1/review-tasks/{review_task_id}/retry",
        path={"review_task_id": task_id},
        body=body.model_dump(mode="json"),
    )
    resumed_stage: str | None = None
    with UnitOfWork(session) as unit_of_work:
        organization = session.scalar(
            select(Organization)
            .where(Organization.id == actor.organization_id)
            .with_for_update()
        )
        if organization is None:
            raise _error("ORGANIZATION_NOT_FOUND", "组织不存在。", status_code=404)
        task = _task_or_not_found(
            session,
            organization_id=actor.organization_id,
            task_id=task_id,
            for_update=True,
        )

        def operation() -> IdempotencyResult:
            nonlocal resumed_stage
            if task.status != "failed":
                raise _error("INVALID_STATE_TRANSITION", "只有失败的审核任务可以重试。")
            if task.retry_count >= REVIEW_TASK_MAX_RETRIES:
                raise _error(
                    "RETRY_LIMIT_EXCEEDED",
                    "审核任务已达到最大重试次数。",
                )
            _verify_locked_inputs(session, task)
            latest = _latest_run_by_stage(session, task)
            failed_stages = [
                stage
                for stage in REVIEW_STAGES
                if latest.get(stage) is not None and latest[stage].status == "failed"
            ]
            if not failed_stages:
                raise _error("INVALID_STATE_TRANSITION", "任务没有可重试的失败阶段。")
            resumed_stage = body.from_stage or failed_stages[0]
            if resumed_stage != failed_stages[0]:
                raise _error("INVALID_STATE_TRANSITION", "只能从第一个失败阶段继续重试。")
            active_count = session.scalar(
                select(func.count())
                .select_from(ReviewTask)
                .where(
                    ReviewTask.organization_id == actor.organization_id,
                    ReviewTask.status.in_(ACTIVE_REVIEW_STATUSES),
                )
            )
            limit = int(organization_settings(organization)["concurrent_review_limit"])
            if active_count is not None and active_count >= limit:
                raise _error(
                    "CONCURRENCY_LIMIT_EXCEEDED",
                    "当前组织审核任务已达到并发上限，请稍后重试。",
                    status_code=429,
                )
            task.status = "pending"
            task.current_stage = "queued"
            task.error_code = None
            task.error_message = None
            task.finished_at = None
            task.retry_count += 1
            session.add(
                ReviewStageRun(
                    id=uuid4(),
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage=resumed_stage,
                    attempt_no=_next_attempt(latest, resumed_stage),
                    status="pending",
                    input_fingerprint=_stage_fingerprint(task, resumed_stage),
                )
            )
            append_audit_log(
                session,
                actor=actor,
                action="review_task.retried",
                resource_type="review_task",
                resource_id=task.id,
                request_id=request_id,
                after={"resumed_from_stage": resumed_stage, "retry_count": task.retry_count},
            )
            return IdempotencyResult(202, "review_task", task.id)

        result = execute_idempotent(
            session,
            scope=organization_scope(actor),
            idempotency_key=idempotency_key,
            operation_key="POST /api/v1/review-tasks/{review_task_id}/retry",
            fingerprint=fingerprint,
            operation=operation,
        )
        if result.replayed:
            latest = _latest_run_by_stage(session, task)
            failed_stages = [
                stage
                for stage in REVIEW_STAGES
                if latest.get(stage) is not None and latest[stage].status == "failed"
            ]
            resumed_stage = body.from_stage or (
                failed_stages[0] if failed_stages else REVIEW_STAGES[0]
            )
        unit_of_work.commit()
    _enqueue_review_task(task.id)
    if resumed_stage is None:
        raise RuntimeError("retry did not select a stage")
    return task, resumed_stage


def claim_next_stage(
    session: Session, *, task_id: UUID, lease_owner: str, lease_seconds: int = LEASE_SECONDS
) -> ReviewStageRun | None:
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        task = session.scalar(select(ReviewTask).where(ReviewTask.id == task_id).with_for_update())
        if task is None or task.status in {"failed", "completed", "archived", "pending_review"}:
            unit_of_work.commit()
            return None
        latest = _latest_run_by_stage(session, task)
        target: ReviewStageRun | None = None
        target_stage: str | None = None
        for stage in REVIEW_STAGES:
            run = latest.get(stage)
            if run is not None and run.status == "succeeded":
                continue
            if run is not None and run.status == "running":
                if run.lease_expires_at is None or run.lease_expires_at > now:
                    unit_of_work.commit()
                    return None
                unit_of_work.commit()
                return None
            if run is not None and run.status == "failed":
                task.status = "failed"
                unit_of_work.commit()
                return None
            target_stage = stage
            if run is None or run.status == "retryable":
                target = ReviewStageRun(
                    id=uuid4(),
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage=stage,
                    attempt_no=_next_attempt(latest, stage),
                    status="pending",
                    input_fingerprint=_stage_fingerprint(task, stage),
                )
                session.add(target)
                session.flush()
            else:
                target = run
            break
        if target is None or target_stage is None:
            task.status = "pending_review"
            task.progress = 100
            task.current_stage = REVIEW_STAGES[-1]
            task.finished_at = now
            unit_of_work.commit()
            return None
        target.status = "running"
        target.lease_owner = lease_owner
        target.lease_expires_at = now + timedelta(seconds=lease_seconds)
        target.heartbeat_at = now
        target.started_at = target.started_at or now
        if task.started_at is None:
            task.started_at = now
        task.status = "parsing" if target_stage == "parsing" else "reviewing"
        task.current_stage = target_stage
        unit_of_work.commit()
        return target


def heartbeat_stage(
    session: Session, *, stage_run_id: UUID, lease_owner: str, lease_seconds: int = LEASE_SECONDS
) -> None:
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        run = session.scalar(
            select(ReviewStageRun)
            .where(
                ReviewStageRun.id == stage_run_id,
                ReviewStageRun.lease_owner == lease_owner,
                ReviewStageRun.status == "running",
            )
            .with_for_update()
        )
        if run is None or run.lease_expires_at is None or run.lease_expires_at <= now:
            raise StageExecutionError("LEASE_EXPIRED", "阶段租约已过期，请由补偿任务恢复。")
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        unit_of_work.commit()


def complete_stage(session: Session, *, stage_run_id: UUID, lease_owner: str) -> bool:
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        run = session.scalar(
            select(ReviewStageRun).where(ReviewStageRun.id == stage_run_id).with_for_update()
        )
        if run is None or run.status != "running" or run.lease_owner != lease_owner:
            unit_of_work.commit()
            return False
        if run.lease_expires_at is None or run.lease_expires_at <= now:
            raise StageExecutionError("LEASE_EXPIRED", "阶段租约已过期，请由补偿任务恢复。")
        task = _task_or_not_found(
            session,
            organization_id=run.organization_id,
            task_id=run.review_task_id,
            for_update=True,
        )
        run.status = "succeeded"
        run.finished_at = now
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = now
        progress = int(((_stage_order(run.stage) + 1) / len(REVIEW_STAGES)) * 100)
        task.progress = progress
        if _stage_order(run.stage) == len(REVIEW_STAGES) - 1:
            from backend.app.modules.warnings.service import generate_warnings

            generate_warnings(session, task=task)
            task.status = "pending_review"
            task.current_stage = run.stage
            task.finished_at = now
        else:
            next_stage = REVIEW_STAGES[_stage_order(run.stage) + 1]
            task.status = "parsing" if next_stage == "parsing" else "reviewing"
            task.current_stage = next_stage
        append_audit_log(
            session,
            actor=None,
            organization_id=task.organization_id,
            action="review_stage.succeeded",
            resource_type="review_stage_run",
            resource_id=run.id,
            request_id="worker",
            after={
                "review_task_id": str(task.id),
                "stage": run.stage,
                "attempt_no": run.attempt_no,
            },
        )
        unit_of_work.commit()
        return task.status in ACTIVE_REVIEW_STATUSES


def fail_stage(
    session: Session,
    *,
    stage_run_id: UUID,
    lease_owner: str,
    error_code: str,
    error_message: str,
    error_class: str | None = None,
) -> None:
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        run = session.scalar(
            select(ReviewStageRun).where(ReviewStageRun.id == stage_run_id).with_for_update()
        )
        if run is None or run.status != "running" or run.lease_owner != lease_owner:
            unit_of_work.commit()
            return
        if run.lease_expires_at is None or run.lease_expires_at <= now:
            unit_of_work.commit()
            return
        task = _task_or_not_found(
            session,
            organization_id=run.organization_id,
            task_id=run.review_task_id,
            for_update=True,
        )
        run.status = "failed"
        run.finished_at = now
        run.lease_owner = None
        run.lease_expires_at = None
        run.heartbeat_at = now
        run.error_code = error_code
        run.error_message = error_message
        run.error_class = error_class
        task.status = "failed"
        task.error_code = error_code
        task.error_message = error_message
        task.finished_at = now
        task.current_stage = run.stage
        append_audit_log(
            session,
            actor=None,
            organization_id=task.organization_id,
            action="review_stage.failed",
            resource_type="review_stage_run",
            resource_id=run.id,
            request_id="worker",
            after={"review_task_id": str(task.id), "stage": run.stage, "error_code": error_code},
        )
        unit_of_work.commit()


def process_review_task(
    session: Session, *, task_id: UUID, executor: StageExecutor
) -> None:
    lease_owner = f"worker-{uuid4()}"
    run = claim_next_stage(session, task_id=task_id, lease_owner=lease_owner)
    if run is None:
        return
    try:
        executor.execute(
            run.stage,
            lambda: heartbeat_stage(
                session, stage_run_id=run.id, lease_owner=lease_owner
            ),
        )
        should_enqueue = complete_stage(session, stage_run_id=run.id, lease_owner=lease_owner)
    except StageExecutionError as exc:
        fail_stage(
            session,
            stage_run_id=run.id,
            lease_owner=lease_owner,
            error_code=exc.code,
            error_message=exc.message,
            error_class=type(exc).__name__,
        )
        should_enqueue = False
    except Exception:
        fail_stage(
            session,
            stage_run_id=run.id,
            lease_owner=lease_owner,
            error_code=_STAGE_ERROR_CODE,
            error_message="阶段执行失败，请重试。",
            error_class="UnhandledStageError",
        )
        should_enqueue = False
    if should_enqueue:
        _enqueue_review_task(task_id)


def recover_expired_leases(
    session: Session, *, executor: StageExecutor | None = None
) -> list[UUID]:
    now = _now()
    recovered: list[UUID] = []
    with UnitOfWork(session) as unit_of_work:
        runs = list(
            session.scalars(
                select(ReviewStageRun)
                .where(
                    ReviewStageRun.status == "running",
                    ReviewStageRun.lease_expires_at.is_not(None),
                    ReviewStageRun.lease_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for locked_run in runs:
            task = _task_or_not_found(
                session,
                organization_id=locked_run.organization_id,
                task_id=locked_run.review_task_id,
                for_update=True,
            )
            if executor is not None:
                executor.compensate(locked_run.stage)
            locked_run.status = "retryable"
            locked_run.compensation_attempts += 1
            locked_run.lease_owner = None
            locked_run.lease_expires_at = None
            locked_run.heartbeat_at = now
            task.status = "pending"
            task.current_stage = "queued"
            task.error_code = None
            task.error_message = None
            task.finished_at = None
            recovered.append(task.id)
            append_audit_log(
                session,
                actor=None,
                organization_id=task.organization_id,
                action="review_stage.retryable",
                resource_type="review_stage_run",
                resource_id=locked_run.id,
                request_id="compensation",
                after={"review_task_id": str(task.id), "stage": locked_run.stage},
            )
        unit_of_work.commit()
    for task_id in recovered:
        _enqueue_review_task(task_id)
    return recovered


def requeue_orphaned_tasks(session: Session) -> list[UUID]:
    tasks = list(
        session.scalars(
            select(ReviewTask)
            .where(ReviewTask.status.in_(WORKER_REQUEUE_STATUSES))
            .order_by(ReviewTask.created_at)
        )
    )
    queued: list[UUID] = []
    for task in tasks:
        has_running = session.scalar(
            select(ReviewStageRun.id).where(
                ReviewStageRun.organization_id == task.organization_id,
                ReviewStageRun.review_task_id == task.id,
                ReviewStageRun.status == "running",
                ReviewStageRun.lease_expires_at > _now(),
            )
        )
        if has_running is None:
            queued.append(task.id)
            _enqueue_review_task(task.id)
    return queued


def latest_review_summary(
    session: Session, *, organization_id: UUID, contract_id: UUID
) -> dict[str, Any] | None:
    task = session.scalar(
        select(ReviewTask)
        .where(
            ReviewTask.organization_id == organization_id,
            ReviewTask.contract_id == contract_id,
        )
        .order_by(ReviewTask.created_at.desc(), ReviewTask.id.desc())
    )
    if task is None:
        return None
    return {"id": task.id, "status": task.status}
