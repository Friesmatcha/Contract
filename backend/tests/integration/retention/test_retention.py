from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.contracts.models import FileObject
from backend.app.modules.identity.models import Organization
from backend.app.modules.notifications.compensation import retry_failed_notifications
from backend.app.modules.retention.models import FileCleanupOperation
from backend.app.modules.retention.service import (
    CLEANUP_MAX_ATTEMPTS,
    create_file_write_journal,
    recover_file_write_journals,
    run_retention_cleanup,
)
from backend.app.modules.warnings.models import Notification
from backend.app.shared.db import UnitOfWork
from backend.tests.integration.classification_extraction.test_results import _seed
from backend.tests.integration.contracts.test_contract_files import _seed_organization
from backend.tests.integration.warnings.test_warnings import (
    _generate_warning,
    _seed_warning_facts,
)


def _expired_file(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> tuple[FileObject, LocalFileStore]:
    organization = _seed_organization(session_factory, f"Retention-{uuid4()}")
    store = LocalFileStore(tmp_path)
    file_id = uuid4()
    storage_key = f"retention/{file_id}"
    size_bytes, sha256 = store.put(BytesIO(b"retention-content"), storage_key)
    created_at = datetime.now(UTC) - timedelta(days=2)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        stored_organization = session.get(type(organization), organization.id)
        assert stored_organization is not None
        stored_organization.retention_days = 0
        file_object = FileObject(
            id=file_id,
            organization_id=organization.id,
            storage_key=storage_key,
            original_name="retention.bin",
            media_type="application/octet-stream",
            size_bytes=size_bytes,
            sha256=sha256,
            scan_status="clean",
            storage_status="stored",
            created_at=created_at,
        )
        session.add(file_object)
        unit_of_work.commit()
    return file_object, store


def test_cleanup_preserves_file_metadata_and_is_idempotent(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    file_object, store = _expired_file(session_factory, tmp_path)

    with session_factory() as session:
        finalized = run_retention_cleanup(session, file_store=store)
        assert finalized
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        stored = session.get(FileObject, file_object.id)
        assert operation is not None and operation.status == "finalized"
        assert stored is not None and stored.storage_status == "deleted"

    assert not store.exists(file_object.storage_key)
    with session_factory() as session:
        assert run_retention_cleanup(session, file_store=store) == []


def test_concurrent_cleanup_schedulers_claim_once(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    file_object, base_store = _expired_file(session_factory, tmp_path)
    calls = 0
    calls_lock = Lock()

    class CountingStore(LocalFileStore):
        def delete(self, storage_key: str) -> None:
            nonlocal calls
            with calls_lock:
                calls += 1
            super().delete(storage_key)

    def run_once() -> None:
        with session_factory() as session:
            run_retention_cleanup(session, file_store=CountingStore(tmp_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: run_once(), range(2)))

    with session_factory() as session:
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        assert operation is not None and operation.status == "finalized"
    assert calls == 1
    assert not base_store.exists(file_object.storage_key)


def test_active_review_reference_is_skipped_and_audited(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    facts = _seed(session_factory)
    with session_factory() as session:
        organization = session.get(Organization, facts["organization_id"])
        assert organization is not None
        organization.retention_days = 0
        session.commit()

    with session_factory() as session:
        run_retention_cleanup(session, file_store=LocalFileStore(tmp_path))
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.operation_type == "cleanup",
                FileCleanupOperation.organization_id == facts["organization_id"],
            )
        )
        file_object = session.scalar(
            select(FileObject).where(FileObject.organization_id == facts["organization_id"])
        )
        assert operation is not None and operation.status == "skipped"
        assert operation.error_code == "ACTIVE_REFERENCE"
        assert file_object is not None and file_object.storage_status == "stored"


def test_cleanup_delete_failure_retries_and_marks_final_failure(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    file_object, store = _expired_file(session_factory, tmp_path)

    class FailingStore(LocalFileStore):
        def delete(self, storage_key: str) -> None:
            raise OSError("injected delete failure")

    failing_store = FailingStore(tmp_path)
    for attempt in range(CLEANUP_MAX_ATTEMPTS):
        with session_factory() as session:
            operation = session.scalar(
                select(FileCleanupOperation).where(
                    FileCleanupOperation.file_object_id == file_object.id,
                    FileCleanupOperation.operation_type == "cleanup",
                )
            )
            if operation is not None:
                operation.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
                session.commit()
            else:
                session.rollback()
            run_retention_cleanup(session, file_store=failing_store)
            if attempt < CLEANUP_MAX_ATTEMPTS - 1:
                assert session.scalar(
                    select(FileCleanupOperation.status).where(
                        FileCleanupOperation.file_object_id == file_object.id,
                        FileCleanupOperation.operation_type == "cleanup",
                    )
                ) == "retryable"

    with session_factory() as session:
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        stored = session.get(FileObject, file_object.id)
        assert operation is not None and operation.status == "final_failed"
        assert stored is not None and stored.storage_status == "failed"
    assert store.exists(file_object.storage_key)


def test_deleted_file_with_failed_status_commit_recovers_idempotently(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    file_object, store = _expired_file(session_factory, tmp_path)

    class DeleteThenRaiseStore(LocalFileStore):
        def delete(self, storage_key: str) -> None:
            super().delete(storage_key)
            raise OSError("injected post-delete failure")

    with session_factory() as session:
        run_retention_cleanup(session, file_store=DeleteThenRaiseStore(tmp_path))
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        assert operation is not None and operation.status == "retryable"
        operation.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    with session_factory() as session:
        run_retention_cleanup(session, file_store=store)
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        stored = session.get(FileObject, file_object.id)
        assert operation is not None and operation.status == "finalized"
        assert stored is not None and stored.storage_status == "deleted"


def test_expired_claim_is_recovered_after_worker_crash(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    file_object, store = _expired_file(session_factory, tmp_path)
    with session_factory() as session:
        run_retention_cleanup(session, file_store=store, limit=1)
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        assert operation is not None
        operation.status = "claimed"
        operation.lease_owner = "crashed-worker"
        operation.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        operation.finished_at = None
        session.get(FileObject, file_object.id).storage_status = "deleting"  # type: ignore[union-attr]
        session.commit()

    with session_factory() as session:
        run_retention_cleanup(session, file_store=store)
        operation = session.scalar(
            select(FileCleanupOperation).where(
                FileCleanupOperation.file_object_id == file_object.id,
                FileCleanupOperation.operation_type == "cleanup",
            )
        )
        assert operation is not None and operation.status == "finalized"


def test_orphan_write_journal_is_recovered(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    organization = _seed_organization(session_factory, f"Journal-{uuid4()}")
    store = LocalFileStore(tmp_path)
    storage_key = f"orphan/{uuid4()}"
    with session_factory() as session:
        operation_id = create_file_write_journal(
            session,
            organization_id=organization.id,
            storage_key=storage_key,
        )
    store.put(BytesIO(b"orphan"), storage_key)

    with session_factory() as session:
        recovered = recover_file_write_journals(
            session,
            file_store=store,
            now=datetime.now(UTC) + timedelta(seconds=301),
        )
        operation = session.get(FileCleanupOperation, operation_id)
        assert recovered == [operation_id]
        assert operation is not None and operation.status == "finalized"
    assert not store.exists(storage_key)


def test_notification_compensation_is_bounded_and_keeps_warning(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed_warning_facts(session_factory)
    warning_id = _generate_warning(session_factory, facts)
    with session_factory() as session:
        notification = session.scalar(
            select(Notification).where(Notification.warning_id == warning_id).limit(1)
        )
        assert notification is not None
        notification.delivery_status = "failed"
        notification.attempts = 1
        notification.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        notification.error_code = "IN_APP_DELIVERY_FAILED"
        session.commit()

    def fail(_notification: Notification) -> None:
        raise OSError("injected notification failure")

    for _ in range(2):
        with session_factory() as session:
            notification = session.scalar(
                select(Notification).where(Notification.id == notification.id)
            )
            assert notification is not None
            notification.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
            retry_failed_notifications(session, deliver=fail)

    with session_factory() as session:
        notification = session.get(Notification, notification.id)
        assert notification is not None
        assert notification.delivery_status == "failed"
        assert notification.attempts == 3
        assert notification.next_attempt_at is None
