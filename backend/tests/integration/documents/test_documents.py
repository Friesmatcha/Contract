from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.documents.models import (
    DocumentBlock,
    DocumentPage,
    DocumentVersion,
    SourceSpan,
)
from backend.app.modules.documents.service import parse_contract_file
from backend.tests.golden.documents.test_parsers import FakeOcr, _text_pdf_bytes
from backend.tests.integration.contracts.test_contract_catalog import ORIGIN
from backend.tests.integration.contracts.test_contract_files import (
    FakeScanner,
    _client,
    _create_contract,
    _login,
    _seed_organization,
    _seed_user,
    _upload,
)


class FailingPageImageStore(LocalFileStore):
    def put(self, source: BinaryIO, storage_key: str) -> tuple[int, str]:
        raise OSError("page image storage failure")


def test_parsing_is_tenant_scoped_idempotent_and_persists_evidence(
    database_engine,
    session_factory: sessionmaker[Session],
    fake_mailer,
    tmp_path: Path,
) -> None:
    organization = _seed_organization(session_factory, "文档解析企业")
    reviewer = _seed_user(
        session_factory,
        email="document-reviewer@example.com",
        organization=organization,
    )
    with _client(database_engine, FakeScanner(), tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        contract = _create_contract(client, csrf, organization.id)
        uploaded = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="document-upload",
            content=_text_pdf_bytes(),
        )
        assert uploaded.status_code == 201, uploaded.text
        contract_file_id = UUID(str(uploaded.json()["contract_file_id"]))

        with session_factory() as session:
            first = parse_contract_file(
                session,
                organization_id=organization.id,
                contract_file_id=contract_file_id,
                file_store=LocalFileStore(tmp_path),
                ocr_engine=FakeOcr(error=True),
            )
            second = parse_contract_file(
                session,
                organization_id=organization.id,
                contract_file_id=contract_file_id,
                file_store=LocalFileStore(tmp_path),
                ocr_engine=FakeOcr(error=True),
            )
            assert first.id == second.id
            assert first.status == "succeeded"
            assert first.page_count == 1
            assert first.ocr_status == "not_required"

        page = client.get(f"/api/v1/documents/{first.id}/pages/1")
        assert page.status_code == 200, page.text
        page_payload = page.json()
        assert page_payload["document_kind"] == "pdf"
        assert page_payload["text"] == "Text PDF evidence"
        assert page_payload["blocks"][0]["source_spans"][0]["kind"] == "pdf_page"

        blocks = client.get(f"/api/v1/documents/{first.id}/blocks")
        assert blocks.status_code == 200, blocks.text
        assert blocks.json()["blocks"][0]["text"] == "Text PDF evidence"

    with session_factory() as session:
        assert session.scalar(select(func.count(DocumentVersion.id))) == 1
        assert session.scalar(select(func.count(DocumentBlock.id))) == 1
        assert session.scalar(select(func.count(SourceSpan.id))) == 1


def test_document_preview_reuses_contract_viewer_authorization(
    database_engine,
    session_factory: sessionmaker[Session],
    fake_mailer,
    tmp_path: Path,
) -> None:
    organization = _seed_organization(session_factory, "文档权限企业")
    reviewer = _seed_user(
        session_factory,
        email="document-admin@example.com",
        organization=organization,
        role="org_admin",
    )
    viewer = _seed_user(
        session_factory,
        email="document-viewer@example.com",
        organization=organization,
        role="viewer",
    )
    with _client(database_engine, FakeScanner(), tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        contract = _create_contract(client, csrf, organization.id)
        uploaded = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="document-auth-upload",
            content=_text_pdf_bytes(),
        )
        with session_factory() as session:
            document = parse_contract_file(
                session,
                organization_id=organization.id,
                contract_file_id=UUID(str(uploaded.json()["contract_file_id"])),
                file_store=LocalFileStore(tmp_path),
                ocr_engine=FakeOcr(error=True),
            )

        _login(client, viewer.email)
        denied = client.get(f"/api/v1/documents/{document.id}/blocks")
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
        denied_page = client.get(f"/api/v1/documents/{document.id}/pages/1")
        assert denied_page.status_code == 404
        assert denied_page.json()["error"]["code"] == "DOCUMENT_OR_PAGE_NOT_FOUND"

        admin_csrf = _login(client, reviewer.email)
        granted = client.put(
            f"/api/v1/contracts/{contract['id']}/access-grants/{viewer.id}",
            headers={**ORIGIN, "X-CSRF-Token": admin_csrf},
            json={"access_level": "read"},
        )
        assert granted.status_code == 200, granted.text

        _login(client, viewer.email)
        allowed = client.get(f"/api/v1/documents/{document.id}/blocks")
        assert allowed.status_code == 200, allowed.text


def test_document_openapi_projects_physical_and_logical_routes(auth_client) -> None:
    paths = auth_client.app.openapi()["paths"]
    assert "/api/v1/documents/{document_version_id}/pages/{page_no}" in paths
    assert "/api/v1/documents/{document_version_id}/blocks" in paths


def test_parse_failure_rolls_back_partial_page_rows(
    database_engine,
    session_factory: sessionmaker[Session],
    fake_mailer,
    tmp_path: Path,
) -> None:
    organization = _seed_organization(session_factory, "文档失败回滚企业")
    reviewer = _seed_user(
        session_factory,
        email="document-failure@example.com",
        organization=organization,
    )
    with _client(database_engine, FakeScanner(), tmp_path, fake_mailer) as client:
        csrf = _login(client, reviewer.email)
        contract = _create_contract(client, csrf, organization.id)
        uploaded = _upload(
            client,
            csrf_token=csrf,
            contract_id=contract["id"],
            key="document-failure-upload",
            content=_text_pdf_bytes(),
        )
        with session_factory() as session:
            document = parse_contract_file(
                session,
                organization_id=organization.id,
                contract_file_id=UUID(str(uploaded.json()["contract_file_id"])),
                file_store=FailingPageImageStore(tmp_path),
                ocr_engine=FakeOcr(error=True),
            )
            assert document.status == "failed"
            assert document.error_code == "DOCUMENT_PARSE_FAILED"
            assert session.scalar(
                select(func.count(DocumentPage.id)).where(
                    DocumentPage.document_version_id == document.id,
                )
            ) == 0
            assert session.scalar(
                select(func.count(DocumentBlock.id)).where(
                    DocumentBlock.document_version_id == document.id,
                )
            ) == 0
