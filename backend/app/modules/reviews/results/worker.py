import hashlib
import json
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.model.gateway import ModelGateway
from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.documents.models import DocumentVersion
from backend.app.modules.documents.service import DocumentParseError, parse_contract_file
from backend.app.modules.reviews.models import ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.service import (
    ResultExecutionError,
    execute_classification,
    execute_extraction,
)
from backend.app.modules.reviews.service import FakeStageExecutor, StageExecutionError
from backend.app.shared.db import UnitOfWork


class Phase9CStageExecutor:
    """Worker adapter for parsing, classification and extraction only.

    Later stages retain the Phase 9A orchestration placeholder and do not gain
    any Phase 10 behavior here.
    """

    def __init__(
        self,
        session: Session,
        *,
        task_id: UUID,
        file_store: LocalFileStore,
        gateway: ModelGateway,
        fallback: FakeStageExecutor | None = None,
    ) -> None:
        self.session = session
        self.task_id = task_id
        self.file_store = file_store
        self.gateway = gateway
        self.fallback = fallback or FakeStageExecutor()

    def execute(self, stage: str, heartbeat: Callable[[], None]) -> None:
        task = self.session.scalar(
            select(ReviewTask).where(
                ReviewTask.id == self.task_id,
            )
        )
        if task is None:
            raise StageExecutionError("REVIEW_TASK_NOT_FOUND", "审核任务不存在，请重试。")
        run = self.session.scalar(
            select(ReviewStageRun).where(
                ReviewStageRun.organization_id == task.organization_id,
                ReviewStageRun.review_task_id == task.id,
                ReviewStageRun.stage == stage,
                ReviewStageRun.status == "running",
                ReviewStageRun.lease_owner.is_not(None),
            )
        )
        if run is None:
            raise StageExecutionError("STAGE_NOT_FOUND", "阶段运行记录不存在，请重试。")
        try:
            if stage == "parsing":
                _ensure_document(
                    self.session,
                    task=task,
                    file_store=self.file_store,
                    heartbeat=heartbeat,
                )
            elif stage == "classification":
                execute_classification(
                    self.session,
                    task=task,
                    stage_run=run,
                    gateway=self.gateway,
                    heartbeat=heartbeat,
                )
            elif stage == "extraction":
                execute_extraction(
                    self.session,
                    task=task,
                    stage_run=run,
                    gateway=self.gateway,
                    heartbeat=heartbeat,
                )
            else:
                self.fallback.execute(stage, heartbeat)
        except ResultExecutionError as exc:
            raise StageExecutionError(exc.code, exc.message) from None
        except DocumentParseError as exc:
            raise StageExecutionError(exc.code, exc.message) from None

    def compensate(self, stage: str) -> None:
        self.fallback.compensate(stage)


def _ensure_document(
    session: Session,
    *,
    task: ReviewTask,
    file_store: LocalFileStore,
    heartbeat: Callable[[], None],
) -> None:
    if task.document_version_id is not None:
        document = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.organization_id == task.organization_id,
                DocumentVersion.id == task.document_version_id,
            )
        )
        if document is not None and document.status == "succeeded":
            return
        raise ResultExecutionError("DOCUMENT_NOT_READY", "文档尚未解析完成。")
    heartbeat()
    document = parse_contract_file(
        session,
        organization_id=task.organization_id,
        contract_file_id=task.contract_file_id,
        file_store=file_store,
    )
    if document.status != "succeeded":
        raise ResultExecutionError(
            document.error_code or "DOCUMENT_PARSE_FAILED",
            document.error_message or "文档解析失败，请重试。",
        )
    with UnitOfWork(session) as unit_of_work:
        locked_task = session.scalar(
            select(ReviewTask)
            .where(
                ReviewTask.organization_id == task.organization_id,
                ReviewTask.id == task.id,
            )
            .with_for_update()
        )
        if locked_task is None:
            raise ResultExecutionError("REVIEW_TASK_NOT_FOUND", "审核任务不存在。")
        snapshot = dict(locked_task.input_snapshot_json)
        snapshot["document_version_id"] = str(document.id)
        snapshot["document_parse_fingerprint"] = document.parse_fingerprint
        locked_task.document_version_id = document.id
        locked_task.input_snapshot_json = snapshot
        locked_task.input_fingerprint = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        unit_of_work.commit()
    heartbeat()


__all__ = ["Phase9CStageExecutor"]
