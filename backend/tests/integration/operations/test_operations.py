from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import OrganizationMembership, User
from backend.app.modules.reviews.models import ModelCall, ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import RiskFinding
from backend.app.modules.reviews.revisions.models import ResultRevision
from backend.app.modules.warnings.service import generate_warnings
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.tenant import PlatformContext, TenantContext
from backend.tests.integration.classification_extraction.test_results import _seed

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"
FROM = datetime(2026, 8, 1, tzinfo=UTC)
TO = datetime(2026, 8, 2, tzinfo=UTC)


def _seed_admin(session_factory: sessionmaker[Session], facts: dict[str, UUID]) -> User:
    admin = User(
        id=uuid4(),
        email=f"admin-{uuid4().hex[:8]}@example.test",
        normalized_email="",
        display_name="Operations Admin",
        password_hash=PasswordHasher().hash(PASSWORD),
    )
    admin.normalized_email = admin.email
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=facts["organization_id"],
        user_id=admin.id,
        email=admin.email,
        normalized_email=admin.email,
        display_name=admin.display_name,
        role="org_admin",
        status="active",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(admin)
        session.flush()
        session.add(membership)
        unit_of_work.commit()
    return admin


def _login(client: TestClient, user: User) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": user.email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def _seed_metrics_facts(session_factory: sessionmaker[Session], facts: dict[str, UUID]) -> None:
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        task = session.get(ReviewTask, facts["task_id"])
        classification_run = session.scalar(
            select(ReviewStageRun).where(
                ReviewStageRun.review_task_id == facts["task_id"],
                ReviewStageRun.stage == "classification",
            )
        )
        assert task is not None and classification_run is not None
        task.created_at = FROM + timedelta(hours=1)
        task.status = "completed"
        task.started_at = FROM + timedelta(hours=1)
        task.finished_at = task.started_at + timedelta(seconds=2)
        classification_run.status = "failed"
        classification_run.started_at = task.started_at
        classification_run.finished_at = task.started_at + timedelta(seconds=1)
        parsing_run = ReviewStageRun(
            id=uuid4(),
            organization_id=task.organization_id,
            review_task_id=task.id,
            stage="parsing",
            attempt_no=1,
            status="failed",
            input_fingerprint="1" * 64,
            started_at=task.started_at,
            finished_at=task.started_at + timedelta(seconds=1),
        )
        session.add(parsing_run)
        session.flush()
        session.add(
            ModelCall(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=classification_run.id,
                capability="classification",
                provider="fake",
                model="fake-model-v1",
                model_fingerprint="2" * 64,
                prompt_version="prompt-v1",
                response_schema_version="schema-v1",
                sanitization_policy_version="sanitization-v1",
                request_fingerprint="3" * 64,
                status="failed",
                latency_ms=10,
            )
        )
        session.add(
            ResultRevision(
                organization_id=task.organization_id,
                review_task_id=task.id,
                subject_type="classification",
                subject_id=uuid4(),
                before_json={"status": "detected"},
                after_json={"status": "detected"},
                version_before=1,
                version_after=2,
                actor_id=facts["user_id"],
                created_at=task.started_at,
            )
        )
        unit_of_work.commit()


def test_audit_queries_are_tenant_scoped_and_read_only(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    admin = _seed_admin(session_factory, facts)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        persisted_admin = session.get(User, admin.id)
        assert persisted_admin is not None
        persisted_admin.is_platform_admin = True
        unit_of_work.commit()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        membership = session.scalar(
            select(OrganizationMembership).where(OrganizationMembership.user_id == admin.id)
        )
        assert membership is not None
        append_audit_log(
            session,
            actor=TenantContext(facts["organization_id"], admin.id, membership.id),
            action="warning_event",
            resource_type="warning",
            request_id="req-audit-1",
            after={"status": "in_progress"},
        )
        append_audit_log(
            session,
            actor=PlatformContext(admin.id),
            organization_id=None,
            action="platform_event",
            resource_type="platform",
            request_id="req-audit-2",
        )
        unit_of_work.commit()

    csrf = _login(auth_client, admin)
    org_id = str(facts["organization_id"])
    response = auth_client.get(
        "/api/v1/audit-logs",
        headers={"X-Organization-ID": org_id},
        params={"action": "warning_event", "limit": 1},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["request_id"] == "req-audit-1"
    assert "contract_text" not in response.text
    assert "prompt" not in response.text

    platform = auth_client.get("/api/v1/platform/audit-logs")
    assert platform.status_code == 200
    assert {item["request_id"] for item in platform.json()["items"]} >= {
        "req-audit-1",
        "req-audit-2",
    }

    invalid_range = auth_client.get(
        "/api/v1/audit-logs",
        headers={"X-Organization-ID": org_id},
        params={"created_from": TO.isoformat(), "created_to": FROM.isoformat()},
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["error"]["code"] == "INVALID_FILTER"
    assert csrf


def test_metrics_use_contract_facts_and_enforce_org_admin(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    admin = _seed_admin(session_factory, facts)
    _seed_metrics_facts(session_factory, facts)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        risk_run = ReviewStageRun(
            id=uuid4(),
            organization_id=task.organization_id,
            review_task_id=task.id,
            stage="risk_analysis",
            attempt_no=1,
            status="succeeded",
            input_fingerprint="4" * 64,
        )
        session.add(risk_run)
        session.flush()
        session.add(
            RiskFinding(
                id=uuid4(),
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=risk_run.id,
                document_version_id=facts["document_id"],
                evidence_span_id=facts["span_id"],
                risk_type="unlimited_liability",
                severity="high",
                title="责任范围不封顶",
                description="需要复核。",
                basis="测试证据。",
                suggestion="补充上限。",
                confidence=0.9,
                source="rule",
                status="pending_review",
                input_fingerprint="5" * 64,
                model_fingerprint="6" * 64,
                result_fingerprint="7" * 64,
            )
        )
        unit_of_work.commit()
    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        generated = generate_warnings(session, task=task)
        assert len(generated) == 1
        generated[0].triggered_at = FROM + timedelta(hours=2)
        session.commit()

    _login(auth_client, admin)
    org_id = str(facts["organization_id"])
    review = auth_client.get(
        f"/api/v1/organizations/{org_id}/metrics/reviews",
        params={"from": FROM.isoformat(), "to": TO.isoformat(), "contract_type": "purchase"},
    )
    assert review.status_code == 200
    assert review.json()["review_count"] == 1
    assert review.json()["completed_count"] == 1
    assert review.json()["failed_count"] == 0
    assert review.json()["average_duration_ms"] == 2000
    assert review.json()["parse_failure_rate"] == 1
    assert review.json()["model_failure_rate"] == 1
    assert review.json()["manual_edit_rate"] == 1

    warnings = auth_client.get(
        f"/api/v1/organizations/{org_id}/metrics/warnings",
        params={"from": FROM.isoformat(), "to": TO.isoformat(), "risk_type": "unlimited_liability"},
    )
    assert warnings.status_code == 200
    assert warnings.json()["created_count"] == 1
    assert warnings.json()["unprocessed_count"] == 1
    assert warnings.json()["by_risk_type"] == [{"risk_type": "unlimited_liability", "count": 1}]


def test_metrics_disabled_and_non_admin_are_safe(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        reviewer = session.get(User, facts["user_id"])
        assert reviewer is not None
        reviewer.password_hash = PasswordHasher().hash(PASSWORD)
        unit_of_work.commit()
    _login(auth_client, reviewer)
    endpoint = f"/api/v1/organizations/{facts['organization_id']}/metrics/reviews"
    forbidden = auth_client.get(endpoint, params={"from": FROM.isoformat(), "to": TO.isoformat()})
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "ORG_ADMIN_REQUIRED"


def test_phase14a_openapi_keeps_metrics_internal(
    auth_client: TestClient,
) -> None:
    paths = auth_client.app.openapi()["paths"]
    assert "/api/v1/audit-logs" in paths
    assert "/api/v1/platform/audit-logs" in paths
    assert "/api/v1/organizations/{organization_id}/metrics/reviews" in paths
    assert "/api/v1/organizations/{organization_id}/metrics/warnings" in paths
    assert "/metrics" not in paths

    metrics = auth_client.get("/metrics")
    assert metrics.status_code == 200
    assert "contract_http_requests_total" in metrics.text
