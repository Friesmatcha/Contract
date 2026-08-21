from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.identity.models import User
from backend.app.modules.reports.models import Report
from backend.app.modules.reports.renderer import FakeReportRenderer, ReportRendererError
from backend.app.modules.reports.service import (
    create_report,
    get_report,
    get_report_download,
    process_report,
)
from backend.app.modules.reviews.results.models import ContractClassification
from backend.app.shared.errors import ApplicationError
from backend.app.shared.tenant import TenantContext
from backend.tests.integration.human_review.test_human_review import _actor, _prepare_results

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"


def _prepare_actor(session_factory: sessionmaker[Session]) -> tuple[dict[str, UUID], TenantContext]:
    facts = _prepare_results(session_factory)
    with session_factory() as session:
        user = session.get(User, facts["user_id"])
        assert user is not None
        user.password_hash = PasswordHasher().hash(PASSWORD)
        session.commit()
    with session_factory() as session:
        return facts, _actor(session, facts)


def test_report_snapshot_is_immutable_and_new_generation_is_a_new_record(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch
) -> None:
    facts, actor = _prepare_actor(session_factory)
    monkeypatch.setattr("backend.app.modules.reports.service._enqueue_report", lambda _id: None)
    file_store = LocalFileStore(tmp_path)
    renderer = FakeReportRenderer()

    with session_factory() as session:
        first, replayed = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="html",
            idempotency_key="report-first",
            request_id="report-test",
            renderer=renderer,
        )
        assert not replayed
        first_id = first.id
        process_report(session, report_id=first.id, file_store=file_store, renderer=renderer)

    with session_factory() as session:
        persisted_first = session.get(Report, first_id)
        assert persisted_first is not None and persisted_first.status == "ready"
        original = persisted_first.snapshot_json["results"]["classification"]["current_value"]
        assert original == "other"
        classification = session.scalar(
            select(ContractClassification).where(
                ContractClassification.organization_id == actor.organization_id,
                ContractClassification.review_task_id == facts["task_id"],
            )
        )
        assert classification is not None
        classification.current_value = "purchase"
        session.commit()

    with session_factory() as session:
        second, _ = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="html",
            idempotency_key="report-second",
            request_id="report-test",
            renderer=renderer,
        )
        assert second.id != first_id
        process_report(session, report_id=second.id, file_store=file_store, renderer=renderer)

        replay, replayed = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="html",
            idempotency_key="report-first",
            request_id="report-test",
            renderer=renderer,
        )
        assert replayed and replay.id == first_id

    with session_factory() as session:
        reports = list(
            session.scalars(
                select(Report)
                .where(Report.organization_id == actor.organization_id)
                .order_by(Report.created_at, Report.id)
            )
        )
        assert len(reports) == 2
        assert reports[0].snapshot_json["results"]["classification"]["current_value"] == "other"
        assert reports[1].snapshot_json["results"]["classification"]["current_value"] == "purchase"
        reports[0].snapshot_json = {"tampered": True}
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        unchanged = session.get(Report, reports[0].id)
        assert unchanged is not None
        assert unchanged.snapshot_json["results"]["classification"]["current_value"] == "other"
        reports[0].expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        expired = get_report(
            session,
            organization_id=actor.organization_id,
            report_id=reports[0].id,
            viewer_user_id=None,
        )
        assert expired["status"] == "expired"
        assert expired["download_available"] is False
        with pytest.raises(ApplicationError) as download_error:
            get_report_download(
                session,
                organization_id=actor.organization_id,
                report_id=reports[0].id,
                viewer_user_id=None,
                file_store=file_store,
            )
        assert download_error.value.status_code == 410
        assert download_error.value.code == "REPORT_EXPIRED"


def test_report_idempotency_replay_does_not_require_renderer(
    session_factory: sessionmaker[Session], monkeypatch
) -> None:
    facts, actor = _prepare_actor(session_factory)
    monkeypatch.setattr("backend.app.modules.reports.service._enqueue_report", lambda _id: None)

    class UnavailableRenderer(FakeReportRenderer):
        def available(self, format: str) -> bool:
            return False

    with session_factory() as session:
        created, replayed = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="html",
            idempotency_key="renderer-replay",
            request_id="report-test",
            renderer=FakeReportRenderer(),
        )
        assert not replayed
        replay, replayed = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="html",
            idempotency_key="renderer-replay",
            request_id="report-test",
            renderer=UnavailableRenderer(),
        )
        assert replayed and replay.id == created.id


def test_failed_report_keeps_review_data_and_can_be_regenerated(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch
) -> None:
    facts, actor = _prepare_actor(session_factory)
    monkeypatch.setattr("backend.app.modules.reports.service._enqueue_report", lambda _id: None)

    class FailingRenderer(FakeReportRenderer):
        def render_pdf(self, html: str) -> bytes:
            raise ReportRendererError("REPORT_RENDER_FAILED")

    with session_factory() as session:
        failed, _ = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="pdf",
            idempotency_key="report-failed",
            request_id="report-test",
            renderer=FakeReportRenderer(),
        )
        process_report(
            session,
            report_id=failed.id,
            file_store=LocalFileStore(tmp_path),
            renderer=FailingRenderer(),
        )
        assert failed.status == "failed"
        recovered, _ = create_report(
            session,
            actor=actor,
            task_id=facts["task_id"],
            report_format="pdf",
            idempotency_key="report-recovered",
            request_id="report-test",
            renderer=FakeReportRenderer(),
        )
        assert recovered.id != failed.id


def test_report_api_returns_status_and_secure_html_download(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    facts, _ = _prepare_actor(session_factory)
    monkeypatch.setattr("backend.app.modules.reports.service._enqueue_report", lambda _id: None)
    store = LocalFileStore(tmp_path)
    auth_client.app.state.file_store = store
    login = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": f"{facts['user_id']}@example.test", "password": PASSWORD},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    headers = {**ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": "api-report"}
    created = auth_client.post(
        f"/api/v1/review-tasks/{facts['task_id']}/reports",
        headers=headers,
        json={"format": "html"},
    )
    assert created.status_code == 202
    report_id = created.json()["id"]
    processing = auth_client.get(f"/api/v1/reports/{report_id}")
    assert processing.status_code == 200
    assert processing.json()["status"] == "generating"

    with session_factory() as session:
        process_report(
            session,
            report_id=UUID(report_id),
            file_store=store,
            renderer=FakeReportRenderer(),
        )
    ready = auth_client.get(f"/api/v1/reports/{report_id}")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    download = auth_client.get(f"/api/v1/reports/{report_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/html")
    assert download.headers["content-security-policy"] == "default-src 'none'"
    assert download.headers["content-disposition"].startswith("attachment;")


def test_report_openapi_projects_phase13_contract(auth_client: TestClient) -> None:
    paths = auth_client.app.openapi()["paths"]
    create = paths["/api/v1/review-tasks/{review_task_id}/reports"]["post"]
    metadata = paths["/api/v1/reports/{report_id}"]["get"]
    download = paths["/api/v1/reports/{report_id}/download"]["get"]
    assert {"202", "409", "422", "429", "503"}.issubset(create["responses"])
    assert {"200", "403", "404"}.issubset(metadata["responses"])
    assert {"200", "403", "404", "409", "410", "429"}.issubset(download["responses"])
    assert any(
        parameter["name"] == "Idempotency-Key" and parameter["in"] == "header"
        for parameter in create["parameters"]
    )
