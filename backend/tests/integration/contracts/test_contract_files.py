from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings
from backend.app.integrations.antivirus.clamav import (
    AntivirusUnavailableError,
    InfectedFileError,
)
from backend.app.integrations.storage.local import LocalFileStore
from backend.app.main import create_app
from backend.app.modules.contracts.models import ContractFile, FileObject
from backend.app.modules.identity.models import (
    Organization,
    OrganizationMembership,
    SupportAccessGrant,
    User,
)
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import UnitOfWork
from backend.tests.integration.contracts.test_contract_catalog import (
    ORIGIN,
    PASSWORD,
)


class FakeScanner:
    def __init__(self, result: str = "clean") -> None:
        self.result = result
        self.paths: list[Path] = []

    def scan(self, path: Path) -> None:
        self.paths.append(path)
        if self.result == "unavailable":
            raise AntivirusUnavailableError
        if self.result == "infected":
            raise InfectedFileError


def _seed_organization(session_factory: sessionmaker[Session], name: str) -> Organization:
    organization = Organization(id=uuid4(), name=name)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(organization)
        unit_of_work.commit()
    return organization


def _seed_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    organization: Organization | None = None,
    role: str = "reviewer",
    is_platform_admin: bool = False,
) -> User:
    user = User(
        id=uuid4(),
        email=email,
        normalized_email=email,
        display_name=email.split("@")[0],
        password_hash=PasswordHasher().hash(PASSWORD),
        is_platform_admin=is_platform_admin,
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(user)
        if organization is not None:
            session.flush()
            session.add(
                OrganizationMembership(
                    id=uuid4(),
                    organization_id=organization.id,
                    user_id=user.id,
                    email=email,
                    normalized_email=email,
                    display_name=user.display_name,
                    role=role,
                    status="active",
                )
            )
        unit_of_work.commit()
    return user


def _client(
    database_engine: Engine,
    scanner: FakeScanner,
    root: Path,
    fake_mailer: object,
) -> TestClient:
    settings = Settings(
        app_env="test",
        database_url=SecretStr(database_engine.url.render_as_string(hide_password=False)),
        redis_url=SecretStr("redis://localhost:6379/15"),
        allowed_origins=["http://localhost:5173"],
        smtp_host="localhost",
        smtp_from="contract-review@example.test",
        frontend_base_url="http://localhost:5173",
        model_name="qwen-test-model",
        model_api_key=SecretStr("test-model-api-key"),
    )
    app = create_app(
        settings=settings,
        database_check=lambda: None,
        file_store=LocalFileStore(root),
        antivirus_scanner=scanner,
    )
    app.state.mailer = fake_mailer
    return TestClient(app)


def _login(client: TestClient, email: str) -> str:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def _csrf_headers(csrf_token: str, **headers: str) -> dict[str, str]:
    return {**ORIGIN, "X-CSRF-Token": csrf_token, **headers}


def _create_contract(
    client: TestClient, csrf_token: str, organization_id: UUID
) -> dict[str, object]:
    response = client.post(
        "/api/v1/contracts",
        headers=_csrf_headers(
            csrf_token,
            **{"X-Organization-ID": str(organization_id), "Idempotency-Key": "file-contract"},
        ),
        json={"title": "安全文件合同", "declared_type": "purchase"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def _upload(
    client: TestClient,
    *,
    csrf_token: str,
    contract_id: object,
    key: str,
    filename: str = "contract.pdf",
    content: bytes = b"%PDF-1.7\n1 0 obj\n%%EOF",
    media_type: str = "application/pdf",
    make_current: bool = True,
    acknowledged: bool = True,
):
    return client.post(
        f"/api/v1/contracts/{contract_id}/files",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": key}),
        files={"file": (filename, BytesIO(content), media_type)},
        data={
            "make_current": str(make_current).lower(),
            "external_model_notice_acknowledged": str(acknowledged).lower(),
        },
    )


def test_upload_is_streamed_scanned_atomically_and_download_is_reauthorized(
    database_engine,
    session_factory: sessionmaker[Session],
    fake_mailer,
    tmp_path: Path,
) -> None:
    organization = _seed_organization(session_factory, "文件企业")
    reviewer = _seed_user(
        session_factory,
        email="file-reviewer@example.com",
        organization=organization,
    )
    scanner = FakeScanner()
    with _client(database_engine, scanner, tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        contract = _create_contract(client, csrf, organization.id)
        uploaded = _upload(client, csrf_token=csrf, contract_id=contract["id"], key="upload-1")
        assert uploaded.status_code == 201, uploaded.text
        payload = uploaded.json()
        assert payload["file"]["scan_status"] == "clean"
        assert payload["file"]["storage_status"] == "stored"
        assert len(payload["file"]["sha256"]) == 64
        assert scanner.paths and not scanner.paths[0].exists()
        assert not list((tmp_path / "quarantine").glob("*"))

        replayed = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="upload-1",
        )
        assert replayed.status_code == 201
        assert replayed.json()["contract_file_id"] == payload["contract_file_id"]

        detail = client.get(f"/api/v1/contracts/{contract['id']}")
        assert detail.status_code == 200
        assert len(detail.json()["files"]) == 1
        file_id = payload["file"]["id"]
        download = client.get(f"/api/v1/files/{file_id}/download")
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF-1.7")
        assert download.headers["content-length"] == str(payload["file"]["size_bytes"])
        assert "attachment" in download.headers["content-disposition"]

    with session_factory() as session:
        assert session.scalar(select(func.count(FileObject.id))) == 1
        assert session.scalar(select(func.count(ContractFile.id))) == 1
        assert session.scalar(select(AuditLog).where(AuditLog.action == "file.downloaded"))


def test_upload_validation_versions_and_failures_leave_no_file_artifacts(
    database_engine,
    session_factory: sessionmaker[Session],
    fake_mailer,
    tmp_path: Path,
) -> None:
    organization = _seed_organization(session_factory, "文件校验企业")
    reviewer = _seed_user(
        session_factory,
        email="validation-reviewer@example.com",
        organization=organization,
    )
    scanner = FakeScanner()
    with _client(database_engine, scanner, tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        contract = _create_contract(client, csrf, organization.id)
        unsupported = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="bad-mime",
            filename="contract.pdf",
            content=b"not a pdf",
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["error"]["code"] == "CONTRACT_FILE_UNSUPPORTED"

        mismatched_media_type = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="mismatched-media-type",
            media_type="text/plain",
        )
        assert mismatched_media_type.status_code == 415
        assert mismatched_media_type.json()["error"]["code"] == "CONTRACT_FILE_UNSUPPORTED"

        with session_factory() as session, UnitOfWork(session) as unit_of_work:
            limited_organization = session.get(Organization, organization.id)
            assert limited_organization is not None
            limited_organization.settings_json = {"file_size_limit_bytes": 8}
            unit_of_work.commit()
        too_large = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="too-large",
        )
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "FILE_TOO_LARGE"
        with session_factory() as session, UnitOfWork(session) as unit_of_work:
            limited_organization = session.get(Organization, organization.id)
            assert limited_organization is not None
            limited_organization.settings_json = {}
            unit_of_work.commit()

        corrupted = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="bad-pdf",
            content=b"%PDF-1.7\ntruncated",
        )
        assert corrupted.status_code == 422
        assert corrupted.json()["error"]["code"] == "FILE_CORRUPTED"

        no_ack = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="no-ack",
            acknowledged=False,
        )
        assert no_ack.status_code == 422
        assert no_ack.json()["error"]["code"] == "EXTERNAL_MODEL_NOTICE_NOT_ACKNOWLEDGED"

        first = _upload(client, csrf_token=csrf, contract_id=contract["id"], key="v1")
        second = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="v2",
            content=b"%PDF-1.7\nsecond\n%%EOF",
        )
        third = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="v3",
            content=b"%PDF-1.7\nthird\n%%EOF",
            make_current=False,
        )
        assert [first.status_code, second.status_code, third.status_code] == [201, 201, 201]
        detail = client.get(f"/api/v1/contracts/{contract['id']}").json()
        assert [item["version_no"] for item in detail["files"]] == [3, 2, 1]
        assert [item["is_current"] for item in detail["files"]] == [False, True, False]

        archived = client.post(
            f"/api/v1/contracts/{contract['id']}/archive",
            headers=_csrf_headers(csrf),
        )
        assert archived.status_code == 200, archived.text
        blocked = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="archived-contract",
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "CONTRACT_ARCHIVED"

    infected_scanner = FakeScanner("infected")
    with _client(database_engine, infected_scanner, tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        infected = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="infected",
        )
        assert infected.status_code == 422
        assert infected.json()["error"]["code"] == "FILE_CORRUPTED"
        assert not list((tmp_path / "quarantine").glob("*"))

    unavailable_scanner = FakeScanner("unavailable")
    with _client(database_engine, unavailable_scanner, tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        unavailable = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="scanner-down",
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "ANTIVIRUS_UNAVAILABLE"
        assert not list((tmp_path / "quarantine").glob("*"))

    with session_factory() as session:
        assert session.scalar(select(func.count(FileObject.id))) == 3


def test_viewer_and_support_access_cannot_bypass_file_authorization(
    database_engine,
    session_factory: sessionmaker[Session],
    fake_mailer,
    tmp_path: Path,
) -> None:
    organization = _seed_organization(session_factory, "文件授权企业")
    admin = _seed_user(
        session_factory,
        email="file-admin@example.com",
        organization=organization,
        role="org_admin",
    )
    viewer = _seed_user(
        session_factory,
        email="file-viewer@example.com",
        organization=organization,
        role="viewer",
    )
    platform_admin = _seed_user(
        session_factory,
        email="file-platform@example.com",
        is_platform_admin=True,
    )
    scanner = FakeScanner()
    with _client(database_engine, scanner, tmp_path, fake_mailer) as client:
        admin_csrf = _login(client, admin.email)
        contract = _create_contract(client, admin_csrf, organization.id)
        uploaded = _upload(
            client,
            csrf_token=admin_csrf,
            contract_id=contract["id"],
            key="auth-file",
        )
        file_id = uploaded.json()["file"]["id"]

        _login(client, viewer.email)
        denied = client.get(f"/api/v1/files/{file_id}/download")
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "FILE_NOT_FOUND"

        admin_csrf = _login(client, admin.email)
        granted = client.put(
            f"/api/v1/contracts/{contract['id']}/access-grants/{viewer.id}",
            headers=_csrf_headers(admin_csrf),
            json={"access_level": "read"},
        )
        assert granted.status_code == 200, granted.text
        _login(client, viewer.email)
        allowed = client.get(f"/api/v1/files/{file_id}/download?disposition=inline")
        assert allowed.status_code == 200
        assert "inline" in allowed.headers["content-disposition"]

        now = datetime.now(UTC)
        grant_id = uuid4()
        with session_factory() as session, UnitOfWork(session) as unit_of_work:
            session.add(
                SupportAccessGrant(
                    id=grant_id,
                    organization_id=organization.id,
                    platform_admin_user_id=platform_admin.id,
                    reason="排查文件下载",
                    status="active",
                    granted_by=admin.id,
                    created_at=now,
                    updated_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
            unit_of_work.commit()
        _login(client, platform_admin.email)
        support_denied = client.get(
            f"/api/v1/files/{file_id}/download",
            headers={"X-Support-Access-Grant": str(grant_id)},
        )
        assert support_denied.status_code == 404
        assert support_denied.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_contract_file_openapi_projects_phase6_paths(auth_client: TestClient) -> None:
    paths = auth_client.app.openapi()["paths"]
    upload = paths["/api/v1/contracts/{contract_id}/files"]["post"]["responses"]
    download = paths["/api/v1/files/{file_id}/download"]["get"]["responses"]

    assert {"201", "403", "404", "409", "413", "415", "422", "503"} <= set(upload)
    assert {"200", "404", "409", "429"} <= set(download)
