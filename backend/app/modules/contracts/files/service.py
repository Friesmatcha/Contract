import hashlib
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from backend.app.integrations.antivirus.clamav import (
    AntivirusUnavailableError,
    InfectedFileError,
)
from backend.app.integrations.storage.local import LocalFileStore, file_storage_key
from backend.app.modules.contracts.models import (
    Contract,
    ContractAccessGrant,
    ContractFile,
    FileObject,
)
from backend.app.modules.identity.models import Organization
from backend.app.modules.identity.organization import organization_settings
from backend.app.modules.retention.service import (
    create_file_write_journal,
    finalize_file_write_journal,
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

SUPPORTED_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
CHUNK_SIZE = 1024 * 1024
_SAFE_FILENAME_PART = re.compile(r"[\x00-\x1f\x7f]")


def _now() -> datetime:
    return datetime.now(UTC)


def _file_not_found() -> ApplicationError:
    return ApplicationError(
        status_code=404,
        code="FILE_NOT_FOUND",
        message="文件不存在。",
    )


def _file_too_large() -> ApplicationError:
    return ApplicationError(
        status_code=413,
        code="FILE_TOO_LARGE",
        message="文件超过组织配置的大小限制。",
        details={"field": "file"},
    )


def _unsupported() -> ApplicationError:
    return ApplicationError(
        status_code=415,
        code="CONTRACT_FILE_UNSUPPORTED",
        message="仅支持 DOCX、PDF、PNG 和 JPEG 文件。",
        details={"field": "file"},
    )


def _corrupted() -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="FILE_CORRUPTED",
        message="文件内容损坏或无法验证。",
        details={"field": "file"},
    )


def _notice_not_acknowledged() -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="EXTERNAL_MODEL_NOTICE_NOT_ACKNOWLEDGED",
        message="请先确认合同内容将按系统说明用于自动审核。",
        details={"field": "external_model_notice_acknowledged"},
    )


def _antivirus_unavailable() -> ApplicationError:
    return ApplicationError(
        status_code=503,
        code="ANTIVIRUS_UNAVAILABLE",
        message="病毒扫描服务暂时不可用，请稍后重试。",
    )


def _infected_file() -> ApplicationError:
    return ApplicationError(
        status_code=422,
        code="FILE_CORRUPTED",
        message="文件未通过安全扫描。",
        details={"field": "file"},
    )


def _normalize_filename(filename: str | None) -> tuple[str, str]:
    raw = (filename or "").replace("\\", "/")
    basename = raw.rsplit("/", 1)[-1].strip()
    basename = _SAFE_FILENAME_PART.sub("_", basename)
    if not basename or len(basename) > 512:
        raise _unsupported()
    suffix = Path(basename).suffix.lower()
    return basename, suffix


def _validate_metadata(filename: str | None, media_type: str | None) -> tuple[str, str]:
    original_name, suffix = _normalize_filename(filename)
    expected_media_type = SUPPORTED_MEDIA_TYPES.get(suffix)
    normalized_media_type = (media_type or "").split(";", 1)[0].strip().lower()
    if expected_media_type is None or normalized_media_type != expected_media_type:
        raise _unsupported()
    return original_name, normalized_media_type


def _copy_to_quarantine(
    source: BinaryIO,
    target: BinaryIO,
    *,
    max_size: int,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(CHUNK_SIZE):
        size += len(chunk)
        if size > max_size:
            raise _file_too_large()
        digest.update(chunk)
        target.write(chunk)
    target.flush()
    os.fsync(target.fileno())
    return size, digest.hexdigest()


def _validate_signature(path: Path, suffix: str) -> None:
    with path.open("rb") as handle:
        header = handle.read(32)
    if suffix == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise _unsupported()
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 1024))
            if b"%%EOF" not in handle.read(1024):
                raise _corrupted()
        return
    if suffix == ".png":
        if not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise _unsupported()
        if len(header) < 24 or header[12:16] != b"IHDR":
            raise _corrupted()
        return
    if suffix in {".jpg", ".jpeg"}:
        if not header.startswith(b"\xff\xd8\xff"):
            raise _unsupported()
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 2))
            if handle.read(2) != b"\xff\xd9":
                raise _corrupted()
        return
    if not header.startswith(b"PK\x03\x04"):
        raise _unsupported()
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise _corrupted()
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise _corrupted()
    except zipfile.BadZipFile as exc:
        raise _corrupted() from exc


def _contract_file_payload(session: Session, contract_file_id: UUID) -> dict[str, Any]:
    row = session.execute(
        select(ContractFile, FileObject)
        .join(
            FileObject,
            and_(
                FileObject.organization_id == ContractFile.organization_id,
                FileObject.id == ContractFile.file_object_id,
            ),
        )
        .where(ContractFile.id == contract_file_id)
    ).one()
    contract_file, file_object = row
    return {
        "file": {
            "id": file_object.id,
            "original_name": file_object.original_name,
            "media_type": file_object.media_type,
            "size_bytes": file_object.size_bytes,
            "sha256": file_object.sha256,
            "scan_status": file_object.scan_status,
            "storage_status": file_object.storage_status,
            "created_at": file_object.created_at,
        },
        "contract_file_id": contract_file.id,
        "version_no": contract_file.version_no,
        "is_current": contract_file.is_current,
        "external_model_notice_acknowledged_at": (
            contract_file.external_model_notice_acknowledged_at
        ),
    }


def upload_contract_file(
    session: Session,
    *,
    actor: TenantContext,
    contract_id: UUID,
    source: BinaryIO,
    original_name: str | None,
    media_type: str | None,
    make_current: bool,
    external_model_notice_acknowledged: bool,
    idempotency_key: str,
    request_id: str,
    file_store: LocalFileStore,
    antivirus_scanner: Any,
) -> dict[str, Any]:
    if not external_model_notice_acknowledged:
        raise _notice_not_acknowledged()
    normalized_name, normalized_media_type = _validate_metadata(original_name, media_type)
    organization = session.get(Organization, actor.organization_id)
    if organization is None:
        raise ApplicationError(
            status_code=404,
            code="CONTRACT_NOT_FOUND",
            message="合同不存在。",
        )
    session.commit()
    quarantine_path: Path | None = None
    promoted_key: str | None = None
    committed = False
    try:
        quarantine_path, quarantine_handle = file_store.create_quarantine_file()
        with quarantine_handle:
            size_bytes, sha256 = _copy_to_quarantine(
                source,
                quarantine_handle,
                max_size=int(organization_settings(organization)["file_size_limit_bytes"]),
            )
        _validate_signature(quarantine_path, Path(normalized_name).suffix.lower())
        try:
            antivirus_scanner.scan(quarantine_path)
        except InfectedFileError as exc:
            raise _infected_file() from exc
        except AntivirusUnavailableError as exc:
            raise _antivirus_unavailable() from exc

        fingerprint = request_fingerprint(
            method="POST",
            operation_key="POST /api/v1/contracts/{contract_id}/files",
            path={"contract_id": contract_id},
            body={
                "file_sha256": sha256,
                "original_name": normalized_name,
                "media_type": normalized_media_type,
                "size_bytes": size_bytes,
                "make_current": make_current,
                "external_model_notice_acknowledged": True,
            },
        )
        created_file_id = uuid4()
        storage_key = file_storage_key(
            organization_id=actor.organization_id,
            contract_id=contract_id,
            file_id=created_file_id,
        )
        write_operation_id = create_file_write_journal(
            session,
            organization_id=actor.organization_id,
            storage_key=storage_key,
        )
        with UnitOfWork(session) as unit_of_work:
            contract = session.scalar(
                select(Contract)
                .where(
                    Contract.organization_id == actor.organization_id,
                    Contract.id == contract_id,
                )
                .with_for_update()
            )
            if contract is None:
                raise ApplicationError(
                    status_code=404,
                    code="CONTRACT_NOT_FOUND",
                    message="合同不存在。",
                )
            if contract.status == "archived":
                raise ApplicationError(
                    status_code=409,
                    code="CONTRACT_ARCHIVED",
                    message="归档合同不可上传文件。",
                )
            created: ContractFile | None = None

            def operation() -> IdempotencyResult:
                nonlocal created, promoted_key
                version_no = int(
                    session.scalar(
                        select(func.coalesce(func.max(ContractFile.version_no), 0)).where(
                            ContractFile.organization_id == actor.organization_id,
                            ContractFile.contract_id == contract_id,
                        )
                    )
                ) + 1
                if make_current:
                    session.execute(
                        update(ContractFile)
                        .where(
                            ContractFile.organization_id == actor.organization_id,
                            ContractFile.contract_id == contract_id,
                            ContractFile.is_current.is_(True),
                        )
                        .values(is_current=False)
                    )
                file_object = FileObject(
                    id=created_file_id,
                    organization_id=actor.organization_id,
                    storage_key=storage_key,
                    original_name=normalized_name,
                    media_type=normalized_media_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    scan_status="clean",
                    storage_status="quarantine",
                )
                created = ContractFile(
                    id=uuid4(),
                    organization_id=actor.organization_id,
                    contract_id=contract_id,
                    file_object_id=file_object.id,
                    version_no=version_no,
                    is_current=make_current,
                    external_model_notice_acknowledged_at=_now(),
                    external_model_notice_acknowledged_by=actor.user_id,
                )
                session.add(file_object)
                session.flush()
                session.add(created)
                session.flush()
                file_store.promote(quarantine_path, storage_key)
                promoted_key = storage_key
                file_object.storage_status = "stored"
                finalize_file_write_journal(
                    session,
                    operation_id=write_operation_id,
                    file_object_id=file_object.id,
                )
                contract.updated_at = _now()
                append_audit_log(
                    session,
                    actor=actor,
                    action="contract.file_uploaded",
                    resource_type="contract_file",
                    resource_id=created.id,
                    request_id=request_id,
                    after={
                        "contract_id": str(contract_id),
                        "file_object_id": str(file_object.id),
                        "version_no": version_no,
                        "size_bytes": size_bytes,
                        "sha256": sha256,
                        "media_type": normalized_media_type,
                        "scan_status": file_object.scan_status,
                        "storage_status": file_object.storage_status,
                        "is_current": make_current,
                        "external_model_notice_acknowledged_at": (
                            created.external_model_notice_acknowledged_at.isoformat()
                        ),
                        "external_model_notice_acknowledged_by": str(actor.user_id),
                    },
                )
                return IdempotencyResult(201, "contract_file", created.id)

            result = execute_idempotent(
                session,
                scope=organization_scope(actor),
                idempotency_key=idempotency_key,
                operation_key="POST /api/v1/contracts/{contract_id}/files",
                fingerprint=fingerprint,
                operation=operation,
            )
            if result.replayed:
                if result.resource_id is None:
                    raise RuntimeError("file idempotency record has no resource")
                created = session.get(ContractFile, result.resource_id)
                if created is None:
                    raise RuntimeError("file idempotency resource is missing")
                finalize_file_write_journal(
                    session,
                    operation_id=write_operation_id,
                    file_object_id=created.file_object_id,
                )
            unit_of_work.commit()
            committed = True
        if created is None:
            raise RuntimeError("file upload returned no resource")
        return _contract_file_payload(session, created.id)
    finally:
        if quarantine_path is not None:
            file_store.remove_quarantine(quarantine_path)
        if promoted_key is not None and not committed:
            file_store.delete(promoted_key)


def authorize_file_download(
    session: Session,
    *,
    actor: TenantContext,
    file_id: UUID,
    viewer_user_id: UUID | None,
    request_id: str,
    disposition: str,
    file_store: LocalFileStore,
) -> FileObject:
    statement = (
        select(FileObject, ContractFile)
        .join(
            ContractFile,
            and_(
                ContractFile.organization_id == FileObject.organization_id,
                ContractFile.file_object_id == FileObject.id,
            ),
        )
        .join(
            Contract,
            and_(
                Contract.organization_id == ContractFile.organization_id,
                Contract.id == ContractFile.contract_id,
            ),
        )
        .where(
            FileObject.organization_id == actor.organization_id,
            FileObject.id == file_id,
        )
    )
    if viewer_user_id is not None:
        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == ContractFile.organization_id,
                ContractAccessGrant.contract_id == ContractFile.contract_id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    row = session.execute(statement).first()
    if row is None:
        raise _file_not_found()
    file_object = cast(FileObject, row[0])
    if file_object.scan_status != "clean" or file_object.storage_status != "stored":
        raise ApplicationError(
            status_code=409,
            code="FILE_NOT_READY",
            message="文件尚未准备好下载。",
        )
    if not file_store.exists(file_object.storage_key):
        raise ApplicationError(
            status_code=409,
            code="FILE_NOT_READY",
            message="文件尚未准备好下载。",
        )
    session.commit()
    with UnitOfWork(session) as unit_of_work:
        append_audit_log(
            session,
            actor=actor,
            action="file.downloaded",
            resource_type="file_object",
            resource_id=file_object.id,
            request_id=request_id,
            after={
                "contract_file_id": str(row[1].id),
                "media_type": file_object.media_type,
                "size_bytes": file_object.size_bytes,
                "disposition": disposition,
            },
        )
        unit_of_work.commit()
    return file_object
