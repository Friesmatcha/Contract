from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.contracts.models import Contract, ContractFile, FileObject
from backend.app.modules.documents.models import DocumentPage, DocumentVersion
from backend.app.modules.identity.models import Organization
from backend.app.modules.reports.models import Report
from backend.app.modules.retention.models import FileCleanupOperation
from backend.app.modules.reviews.models import ACTIVE_REVIEW_STATUSES, ReviewTask
from backend.app.modules.warnings.models import Notification, Warning
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork

FILE_WRITE_JOURNAL_GRACE_SECONDS = 300
CLEANUP_LEASE_SECONDS = 300
CLEANUP_MAX_ATTEMPTS = 5
CLEANUP_RETRY_DELAYS_SECONDS = (60, 300, 1800, 7200)


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(
    session: Session,
    *,
    organization_id: UUID,
    operation_id: UUID,
    action: str,
    operation_type: str,
    status: str,
    attempts: int,
    error_code: str | None = None,
) -> None:
    append_audit_log(
        session,
        actor=None,
        organization_id=organization_id,
        action=action,
        resource_type="file_cleanup_operation",
        resource_id=operation_id,
        request_id="retention-worker",
        after={
            "operation_type": operation_type,
            "status": status,
            "attempts": attempts,
            "error_code": error_code,
        },
    )


def _durable_bind(session: Session) -> Any:
    bind = session.get_bind()
    return getattr(bind, "engine", bind)


def create_file_write_journal(
    session: Session, *, organization_id: UUID, storage_key: str
) -> UUID:
    """Commit a write fact before a worker or request writes FileStore content."""
    operation_id = uuid4()
    with Session(bind=_durable_bind(session), expire_on_commit=False) as journal_session:
        journal_session.add(
            FileCleanupOperation(
                id=operation_id,
                organization_id=organization_id,
                storage_key=storage_key,
                operation_type="write",
                status="pending",
            )
        )
        journal_session.commit()
    return operation_id


def finalize_file_write_journal(
    session: Session, *, operation_id: UUID, file_object_id: UUID
) -> None:
    operation = session.scalar(
        select(FileCleanupOperation)
        .where(
            FileCleanupOperation.id == operation_id,
            FileCleanupOperation.operation_type == "write",
        )
        .with_for_update()
    )
    if operation is None:
        raise RuntimeError("file write journal is missing")
    operation.file_object_id = file_object_id
    operation.status = "finalized"
    operation.finished_at = _now()
    operation.lease_owner = None
    operation.lease_expires_at = None


def _report_for_file(session: Session, file_object_id: UUID) -> Report | None:
    return session.scalar(
        select(Report).where(
            Report.file_object_id == file_object_id,
        )
    )


def _candidate_file_objects(
    session: Session, *, now: datetime, limit: int
) -> list[FileObject]:
    rows = session.execute(
        select(FileObject, Organization.retention_days)
        .join(Organization, Organization.id == FileObject.organization_id)
        .where(FileObject.storage_status == "stored")
        .order_by(FileObject.created_at, FileObject.id)
        .limit(max(limit * 10, limit))
    ).all()
    candidates: list[FileObject] = []
    for file_object, retention_days in rows:
        report = _report_for_file(session, file_object.id)
        if report is not None:
            if report.expires_at is not None and report.expires_at <= now:
                candidates.append(file_object)
            continue
        if file_object.created_at + timedelta(days=int(retention_days)) <= now:
            candidates.append(file_object)
        if len(candidates) >= limit:
            break
    return candidates


def _contract_ids_for_file(session: Session, file_object_id: UUID) -> set[UUID]:
    contract_ids = set(
        session.scalars(
            select(ContractFile.contract_id).where(ContractFile.file_object_id == file_object_id)
        )
    )
    contract_ids.update(
        session.scalars(
            select(ContractFile.contract_id)
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.organization_id == ContractFile.organization_id,
                    DocumentVersion.contract_file_id == ContractFile.id,
                ),
            )
            .join(
                DocumentPage,
                and_(
                    DocumentPage.organization_id == DocumentVersion.organization_id,
                    DocumentPage.document_version_id == DocumentVersion.id,
                    DocumentPage.image_file_id == file_object_id,
                ),
            )
        )
    )
    contract_ids.update(
        session.scalars(
            select(ReviewTask.contract_id)
            .join(Report, Report.review_task_id == ReviewTask.id)
            .where(Report.file_object_id == file_object_id)
        )
    )
    return contract_ids


def _lock_related_contracts(session: Session, file_object_id: UUID) -> set[UUID]:
    contract_ids = _contract_ids_for_file(session, file_object_id)
    if contract_ids:
        list(
            session.scalars(
                select(Contract)
                .where(Contract.id.in_(contract_ids))
                .order_by(Contract.id)
                .with_for_update()
            )
        )
    return contract_ids


def _has_cleanup_blocker(
    session: Session, *, file_object_id: UUID, contract_ids: set[UUID]
) -> bool:
    contract_file_ids = select(ContractFile.id).where(ContractFile.file_object_id == file_object_id)
    document_ids = (
        select(DocumentVersion.id)
        .join(
            DocumentPage,
            and_(
                DocumentPage.organization_id == DocumentVersion.organization_id,
                DocumentPage.document_version_id == DocumentVersion.id,
                DocumentPage.image_file_id == file_object_id,
            ),
        )
        .scalar_subquery()
    )
    active_task = session.scalar(
        select(ReviewTask.id).where(
            ReviewTask.status.in_(ACTIVE_REVIEW_STATUSES),
            or_(
                ReviewTask.contract_file_id.in_(contract_file_ids),
                ReviewTask.document_version_id.in_(document_ids),
            ),
        )
    )
    if active_task is not None:
        return True
    if contract_ids:
        generating_report = session.scalar(
            select(Report.id)
            .join(ReviewTask, Report.review_task_id == ReviewTask.id)
            .where(
                Report.status == "generating",
                ReviewTask.contract_id.in_(contract_ids),
            )
        )
        if generating_report is not None:
            return True
        failed_notification = session.scalar(
            select(Notification.id)
            .join(Warning, Warning.id == Notification.warning_id)
            .where(
                Warning.contract_id.in_(contract_ids),
                Notification.delivery_status == "failed",
                Notification.attempts < 3,
            )
        )
        if failed_notification is not None:
            return True
    return False


def schedule_cleanup(
    session: Session, *, now: datetime | None = None, limit: int = 100
) -> list[UUID]:
    now = now or _now()
    scheduled: list[UUID] = []
    with UnitOfWork(session) as unit_of_work:
        for file_object in _candidate_file_objects(session, now=now, limit=limit):
            contract_ids = _lock_related_contracts(session, file_object.id)
            locked_file_object = session.scalar(
                select(FileObject)
                .where(FileObject.id == file_object.id)
                .with_for_update()
            )
            if locked_file_object is None or locked_file_object.storage_status != "stored":
                continue
            file_object = locked_file_object
            operation = session.scalar(
                select(FileCleanupOperation)
                .where(
                    FileCleanupOperation.operation_type == "cleanup",
                    FileCleanupOperation.storage_key == file_object.storage_key,
                )
                .with_for_update()
            )
            if _has_cleanup_blocker(
                session,
                file_object_id=file_object.id,
                contract_ids=contract_ids,
            ):
                if operation is None:
                    operation = FileCleanupOperation(
                        organization_id=file_object.organization_id,
                        file_object_id=file_object.id,
                        storage_key=file_object.storage_key,
                        operation_type="cleanup",
                        status="skipped",
                        error_code="ACTIVE_REFERENCE",
                        finished_at=now,
                    )
                    session.add(operation)
                    session.flush()
                elif operation.status in {"pending", "retryable", "skipped"}:
                    operation.status = "skipped"
                    operation.next_attempt_at = None
                    operation.error_code = "ACTIVE_REFERENCE"
                    operation.finished_at = now
                else:
                    continue
                _audit(
                    session,
                    organization_id=file_object.organization_id,
                    operation_id=operation.id,
                    action="file.cleanup_skipped",
                    operation_type="cleanup",
                    status="skipped",
                    attempts=operation.attempts,
                    error_code="ACTIVE_REFERENCE",
                )
                continue
            if operation is None:
                operation = FileCleanupOperation(
                    organization_id=file_object.organization_id,
                    file_object_id=file_object.id,
                    storage_key=file_object.storage_key,
                    operation_type="cleanup",
                    status="pending",
                )
                session.add(operation)
                session.flush()
            elif operation.status in {"pending", "claimed", "file_deleted", "finalized"} or (
                operation.status == "retryable"
                and operation.next_attempt_at is not None
                and operation.next_attempt_at > now
            ):
                continue
            else:
                operation.status = "pending"
                operation.next_attempt_at = None
                operation.error_code = None
                operation.finished_at = None
            file_object.storage_status = "deleting"
            scheduled.append(operation.id)
            _audit(
                session,
                organization_id=file_object.organization_id,
                operation_id=operation.id,
                action="file.cleanup_scheduled",
                operation_type="cleanup",
                status="pending",
                attempts=operation.attempts,
            )
        unit_of_work.commit()
    return scheduled


def _claim_cleanup_operations(
    session: Session, *, now: datetime, limit: int
) -> list[tuple[UUID, str, str]]:
    claimed: list[tuple[UUID, str, str]] = []
    with UnitOfWork(session) as unit_of_work:
        operations = list(
            session.scalars(
                select(FileCleanupOperation)
                .where(
                    FileCleanupOperation.operation_type == "cleanup",
                    or_(
                        and_(
                            FileCleanupOperation.status.in_(("pending", "retryable")),
                            or_(
                                FileCleanupOperation.next_attempt_at.is_(None),
                                FileCleanupOperation.next_attempt_at <= now,
                            ),
                        ),
                        and_(
                            FileCleanupOperation.status == "claimed",
                            FileCleanupOperation.lease_expires_at <= now,
                        ),
                    ),
                )
                .order_by(FileCleanupOperation.created_at, FileCleanupOperation.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for operation in operations:
            file_object = session.scalar(
                select(FileObject).where(
                    FileObject.organization_id == operation.organization_id,
                    FileObject.id == operation.file_object_id,
                )
            )
            if file_object is None:
                operation.status = "finalized"
                operation.finished_at = now
                continue
            contract_ids = _lock_related_contracts(session, file_object.id)
            file_object = session.scalar(
                select(FileObject)
                .where(
                    FileObject.organization_id == operation.organization_id,
                    FileObject.id == operation.file_object_id,
                )
                .with_for_update()
            )
            if file_object is None:
                operation.status = "finalized"
                operation.finished_at = now
                continue
            if _has_cleanup_blocker(
                session,
                file_object_id=file_object.id,
                contract_ids=contract_ids,
            ):
                operation.status = "skipped"
                operation.next_attempt_at = None
                operation.lease_owner = None
                operation.lease_expires_at = None
                operation.finished_at = now
                file_object.storage_status = "stored"
                _audit(
                    session,
                    organization_id=operation.organization_id,
                    operation_id=operation.id,
                    action="file.cleanup_skipped",
                    operation_type="cleanup",
                    status="skipped",
                    attempts=operation.attempts,
                    error_code="ACTIVE_REFERENCE",
                )
                continue
            owner = f"retention-{uuid4()}"
            recovering = operation.status == "claimed"
            operation.status = "claimed"
            operation.lease_owner = owner
            operation.lease_expires_at = now + timedelta(seconds=CLEANUP_LEASE_SECONDS)
            operation.finished_at = None
            if not recovering:
                operation.attempts += 1
            claimed.append((operation.id, operation.storage_key, owner))
            _audit(
                session,
                organization_id=operation.organization_id,
                operation_id=operation.id,
                action="file.cleanup_recovered" if recovering else "file.cleanup_claimed",
                operation_type="cleanup",
                status="claimed",
                attempts=operation.attempts,
            )
        unit_of_work.commit()
    return claimed


def _retry_delay(attempts: int) -> int:
    index = min(max(attempts - 1, 0), len(CLEANUP_RETRY_DELAYS_SECONDS) - 1)
    return CLEANUP_RETRY_DELAYS_SECONDS[index]


def _record_cleanup_failure(
    session: Session, *, operation_id: UUID, owner: str, error_code: str, now: datetime
) -> None:
    with UnitOfWork(session) as unit_of_work:
        operation = session.scalar(
            select(FileCleanupOperation)
            .where(
                FileCleanupOperation.id == operation_id,
                FileCleanupOperation.lease_owner == owner,
            )
            .with_for_update()
        )
        if operation is None:
            unit_of_work.commit()
            return
        file_object = session.scalar(
            select(FileObject)
            .where(
                FileObject.organization_id == operation.organization_id,
                FileObject.id == operation.file_object_id,
            )
            .with_for_update()
        )
        if operation.attempts >= CLEANUP_MAX_ATTEMPTS:
            operation.status = "final_failed"
            operation.finished_at = now
            operation.next_attempt_at = None
            if file_object is not None:
                file_object.storage_status = "failed"
            action = "file.cleanup_final_failed"
        else:
            operation.status = "retryable"
            operation.next_attempt_at = now + timedelta(seconds=_retry_delay(operation.attempts))
            if file_object is not None:
                file_object.storage_status = "stored"
            action = "file.cleanup_retryable"
        operation.error_code = error_code
        operation.lease_owner = None
        operation.lease_expires_at = None
        _audit(
            session,
            organization_id=operation.organization_id,
            operation_id=operation.id,
            action=action,
            operation_type="cleanup",
            status=operation.status,
            attempts=operation.attempts,
            error_code=error_code,
        )
        unit_of_work.commit()


def _record_file_deleted(
    session: Session, *, operation_id: UUID, owner: str, now: datetime
) -> None:
    with UnitOfWork(session) as unit_of_work:
        operation = session.scalar(
            select(FileCleanupOperation)
            .where(
                FileCleanupOperation.id == operation_id,
                FileCleanupOperation.lease_owner == owner,
            )
            .with_for_update()
        )
        if operation is None:
            unit_of_work.commit()
            return
        file_object = session.scalar(
            select(FileObject)
            .where(
                FileObject.organization_id == operation.organization_id,
                FileObject.id == operation.file_object_id,
            )
            .with_for_update()
        )
        operation.status = "file_deleted"
        operation.lease_owner = None
        operation.lease_expires_at = None
        operation.error_code = None
        if file_object is not None:
            file_object.storage_status = "deleted"
        _audit(
            session,
            organization_id=operation.organization_id,
            operation_id=operation.id,
            action="file.cleanup_file_deleted",
            operation_type="cleanup",
            status="file_deleted",
            attempts=operation.attempts,
        )
        unit_of_work.commit()


def _finalize_file_deleted(session: Session, *, now: datetime, limit: int) -> list[UUID]:
    finalized: list[UUID] = []
    with UnitOfWork(session) as unit_of_work:
        operations = list(
            session.scalars(
                select(FileCleanupOperation)
                .where(
                    FileCleanupOperation.operation_type == "cleanup",
                    FileCleanupOperation.status == "file_deleted",
                )
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for operation in operations:
            operation.status = "finalized"
            operation.finished_at = now
            finalized.append(operation.id)
            _audit(
                session,
                organization_id=operation.organization_id,
                operation_id=operation.id,
                action="file.cleanup_finalized",
                operation_type="cleanup",
                status="finalized",
                attempts=operation.attempts,
            )
        unit_of_work.commit()
    return finalized


def _claim_write_journals(
    session: Session, *, now: datetime, limit: int
) -> list[tuple[UUID, str, str]]:
    claimed: list[tuple[UUID, str, str]] = []
    cutoff = now - timedelta(seconds=FILE_WRITE_JOURNAL_GRACE_SECONDS)
    with UnitOfWork(session) as unit_of_work:
        operations = list(
            session.scalars(
                select(FileCleanupOperation)
                .where(
                    FileCleanupOperation.operation_type == "write",
                    or_(
                        and_(
                            FileCleanupOperation.status.in_(("pending", "retryable")),
                            or_(
                                FileCleanupOperation.status == "retryable",
                                FileCleanupOperation.created_at <= cutoff,
                            ),
                            or_(
                                FileCleanupOperation.next_attempt_at.is_(None),
                                FileCleanupOperation.next_attempt_at <= now,
                            ),
                        ),
                        and_(
                            FileCleanupOperation.status == "claimed",
                            FileCleanupOperation.lease_expires_at <= now,
                        ),
                    ),
                )
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for operation in operations:
            owner = f"write-recovery-{uuid4()}"
            recovering = operation.status == "claimed"
            operation.status = "claimed"
            operation.lease_owner = owner
            operation.lease_expires_at = now + timedelta(seconds=CLEANUP_LEASE_SECONDS)
            if not recovering:
                operation.attempts += 1
            claimed.append((operation.id, operation.storage_key, owner))
        unit_of_work.commit()
    return claimed


def _finish_write_recovery(
    session: Session,
    *,
    operation_id: UUID,
    owner: str,
    now: datetime,
    error_code: str | None = None,
) -> None:
    with UnitOfWork(session) as unit_of_work:
        operation = session.scalar(
            select(FileCleanupOperation)
            .where(
                FileCleanupOperation.id == operation_id,
                FileCleanupOperation.lease_owner == owner,
            )
            .with_for_update()
        )
        if operation is None:
            unit_of_work.commit()
            return
        if error_code is None:
            operation.status = "finalized"
            operation.finished_at = now
            operation.error_code = None
            action = "file.write_recovered"
        elif operation.attempts >= CLEANUP_MAX_ATTEMPTS:
            operation.status = "final_failed"
            operation.finished_at = now
            operation.next_attempt_at = None
            operation.error_code = error_code
            action = "file.write_recovery_final_failed"
        else:
            operation.status = "retryable"
            operation.next_attempt_at = now + timedelta(seconds=_retry_delay(operation.attempts))
            operation.error_code = error_code
            action = "file.write_recovery_retryable"
        operation.lease_owner = None
        operation.lease_expires_at = None
        _audit(
            session,
            organization_id=operation.organization_id,
            operation_id=operation.id,
            action=action,
            operation_type="write",
            status=operation.status,
            attempts=operation.attempts,
            error_code=error_code,
        )
        unit_of_work.commit()


def recover_file_write_journals(
    session: Session, *, file_store: LocalFileStore, now: datetime | None = None, limit: int = 100
) -> list[UUID]:
    now = now or _now()
    recovered: list[UUID] = []
    for operation_id, storage_key, owner in _claim_write_journals(
        session, now=now, limit=limit
    ):
        try:
            file_store.delete(storage_key)
        except Exception:
            _finish_write_recovery(
                session,
                operation_id=operation_id,
                owner=owner,
                now=now,
                error_code="FILESTORE_DELETE_FAILED",
            )
            continue
        _finish_write_recovery(session, operation_id=operation_id, owner=owner, now=now)
        recovered.append(operation_id)
    return recovered


def run_retention_cleanup(
    session: Session,
    *,
    file_store: LocalFileStore,
    now: datetime | None = None,
    limit: int = 100,
) -> list[UUID]:
    now = now or _now()
    recover_file_write_journals(session, file_store=file_store, now=now, limit=limit)
    schedule_cleanup(session, now=now, limit=limit)
    finalized = _finalize_file_deleted(session, now=now, limit=limit)
    for operation_id, storage_key, owner in _claim_cleanup_operations(
        session, now=now, limit=limit
    ):
        try:
            file_store.delete(storage_key)
            _record_file_deleted(session, operation_id=operation_id, owner=owner, now=now)
        except Exception:
            _record_cleanup_failure(
                session,
                operation_id=operation_id,
                owner=owner,
                error_code="FILESTORE_DELETE_FAILED",
                now=now,
            )
    finalized.extend(_finalize_file_deleted(session, now=now, limit=limit))
    return finalized


__all__ = [
    "CLEANUP_LEASE_SECONDS",
    "CLEANUP_MAX_ATTEMPTS",
    "CLEANUP_RETRY_DELAYS_SECONDS",
    "FILE_WRITE_JOURNAL_GRACE_SECONDS",
    "create_file_write_journal",
    "finalize_file_write_journal",
    "recover_file_write_journals",
    "run_retention_cleanup",
    "schedule_cleanup",
]
