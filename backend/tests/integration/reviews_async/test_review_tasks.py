from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import cast
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.clauses.templates.models import ClauseTemplate, ClauseTemplateVersion
from backend.app.modules.contracts.models import (
    Contract,
    ContractAccessGrant,
    ContractFile,
    FileObject,
)
from backend.app.modules.contracts.service import archive_contract
from backend.app.modules.identity.models import (
    Organization,
    OrganizationMembership,
    SupportAccessGrant,
    User,
)
from backend.app.modules.reviews.models import ReviewStageRun, ReviewTask
from backend.app.modules.reviews.schemas import CreateReviewTaskRequest
from backend.app.modules.reviews.service import (
    FakeStageExecutor,
    claim_next_stage,
    create_review_task,
    process_review_task,
    recover_expired_leases,
    requeue_orphaned_tasks,
)
from backend.app.modules.risks.rules.models import RiskRuleBundle, RiskRuleBundleVersion
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
from backend.app.shared.tenant import TenantContext

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"


def _seed_facts(
    session_factory: sessionmaker[Session],
) -> tuple[Organization, User, Contract, UUID]:
    organization = Organization(id=uuid4(), name="审核编排企业")
    user = User(
        id=uuid4(),
        email="reviewer-9a@example.com",
        normalized_email="reviewer-9a@example.com",
        display_name="审核员",
        password_hash=PasswordHasher().hash(PASSWORD),
    )
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        email=user.email,
        normalized_email=user.normalized_email,
        display_name=user.display_name,
        role="reviewer",
        status="active",
    )
    contract = Contract(
        id=uuid4(),
        organization_id=organization.id,
        display_no="CTR-9A-000001",
        title="采购审核合同",
        declared_type="purchase",
        owner_id=user.id,
    )
    file_object = FileObject(
        id=uuid4(),
        organization_id=organization.id,
        storage_key="9a/review-file",
        original_name="contract.pdf",
        media_type="application/pdf",
        size_bytes=128,
        sha256="a" * 64,
        scan_status="clean",
        storage_status="stored",
    )
    contract_file = ContractFile(
        id=uuid4(),
        organization_id=organization.id,
        contract_id=contract.id,
        file_object_id=file_object.id,
        version_no=1,
        is_current=True,
        external_model_notice_acknowledged_at=datetime.now(UTC),
        external_model_notice_acknowledged_by=user.id,
    )
    rule_bundle = RiskRuleBundle(
        id=uuid4(),
        organization_id=organization.id,
        name="默认规则",
        normalized_name="默认规则",
        status="active",
        is_default=False,
    )
    rule_version = RiskRuleBundleVersion(
        id=uuid4(),
        organization_id=organization.id,
        bundle_id=rule_bundle.id,
        version_no=1,
        status="published",
        change_note="初始版本",
        published_by=user.id,
    )
    template = ClauseTemplate(
        id=uuid4(),
        organization_id=organization.id,
        name="采购默认模板",
        normalized_name="采购默认模板",
        contract_type="purchase",
        business_scenario="standard",
        status="active",
        is_default=False,
    )
    template_version = ClauseTemplateVersion(
        id=uuid4(),
        organization_id=organization.id,
        template_id=template.id,
        version_no=1,
        status="published",
        change_note="初始版本",
        published_by=user.id,
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([organization, user])
        session.flush()
        session.add(membership)
        session.flush()
        session.add_all([contract, file_object])
        session.flush()
        session.add(contract_file)
        session.flush()
        session.add_all([rule_bundle, template])
        session.flush()
        session.add_all([rule_version, template_version])
        session.flush()
        rule_bundle.current_published_version_id = rule_version.id
        rule_bundle.is_default = True
        template.current_published_version_id = template_version.id
        template.is_default = True
        unit_of_work.commit()
    return organization, user, contract, contract_file.id


def _add_contracts(
    session_factory: sessionmaker[Session],
    *,
    organization: Organization,
    user: User,
    count: int,
) -> list[tuple[UUID, UUID]]:
    facts: list[tuple[UUID, UUID]] = []
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        for index in range(count):
            contract = Contract(
                id=uuid4(),
                organization_id=organization.id,
                display_no=f"CTR-9A-CONCURRENT-{index:02d}",
                title=f"并发审核合同 {index}",
                declared_type="purchase",
                owner_id=user.id,
            )
            file_object = FileObject(
                id=uuid4(),
                organization_id=organization.id,
                storage_key=f"9a/concurrent-review-file-{index}",
                original_name=f"contract-{index}.pdf",
                media_type="application/pdf",
                size_bytes=128,
                sha256=f"{index + 1:064x}",
                scan_status="clean",
                storage_status="stored",
            )
            contract_file = ContractFile(
                id=uuid4(),
                organization_id=organization.id,
                contract_id=contract.id,
                file_object_id=file_object.id,
                version_no=1,
                is_current=True,
                external_model_notice_acknowledged_at=datetime.now(UTC),
                external_model_notice_acknowledged_by=user.id,
            )
            session.add_all([contract, file_object])
            session.flush()
            session.add(contract_file)
            session.flush()
            facts.append((contract.id, contract_file.id))
        unit_of_work.commit()
    return facts


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return cast(str, response.json()["csrf_token"])


def _headers(csrf: str, **extra: str) -> dict[str, str]:
    return {**ORIGIN, "X-CSRF-Token": csrf, **extra}


def _create_task(
    client: TestClient, *, contract_id: UUID, file_id: UUID, csrf: str, key: str
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/contracts/{contract_id}/reviews",
        headers=_headers(csrf, **{"Idempotency-Key": key}),
        json={"contract_file_id": str(file_id)},
    )
    assert response.status_code == 202, response.text
    return cast(dict[str, object], response.json())


def test_create_locks_versions_and_idempotently_replays(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    organization, user, contract, file_id = _seed_facts(session_factory)
    csrf = _login(auth_client, user.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )

    created = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-create-1",
    )
    replayed = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-create-1",
    )

    assert created["id"] == replayed["id"]
    assert created["status"] == "pending"
    assert created["document_version_id"] is None
    assert UUID(str(created["rule_bundle_version_id"]))
    assert UUID(str(created["clause_template_version_id"]))
    with session_factory() as session:
        task = session.get(ReviewTask, UUID(str(created["id"])))
        assert task is not None
        assert task.input_snapshot_json["file_sha256"] == "a" * 64
        assert task.model_config_json["organization_overrides_allowed"] is False
        assert "api_key" not in task.model_config_json
        assert session.scalar(
            select(ReviewStageRun).where(ReviewStageRun.review_task_id == task.id)
        ) is not None
    assert organization.id == task.organization_id
    conflict = auth_client.post(
        f"/api/v1/contracts/{contract.id}/reviews",
        headers=_headers(csrf, **{"Idempotency-Key": "review-create-2"}),
        json={"contract_file_id": str(file_id)},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ACTIVE_REVIEW_EXISTS"


def test_concurrent_creates_are_serialized_at_organization_limit(
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    organization, user, first_contract, first_file_id = _seed_facts(session_factory)
    additional = _add_contracts(
        session_factory,
        organization=organization,
        user=user,
        count=3,
    )
    facts = [(first_contract.id, first_file_id), *additional]
    with session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
        )
        assert membership is not None
        actor = TenantContext(
            organization_id=organization.id,
            user_id=user.id,
            membership_id=membership.id,
        )
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    barrier = Barrier(len(facts))

    def create(index: int, contract_id: UUID, file_id: UUID) -> tuple[str, str]:
        barrier.wait(timeout=10)
        with session_factory() as session:
            try:
                task = create_review_task(
                    session,
                    actor=actor,
                    contract_id=contract_id,
                    body=CreateReviewTaskRequest(contract_file_id=file_id),
                    idempotency_key=f"review-concurrent-{index}",
                    request_id=f"review-concurrent-{index}",
                )
            except ApplicationError as exc:
                return ("error", exc.code)
            return ("created", str(task.id))

    with ThreadPoolExecutor(max_workers=len(facts)) as executor:
        results = [
            future.result(timeout=20)
            for future in [
                executor.submit(create, index, contract_id, file_id)
                for index, (contract_id, file_id) in enumerate(facts)
            ]
        ]
    assert sum(result[0] == "created" for result in results) == 3
    assert [result for result in results if result[1] == "CONCURRENCY_LIMIT_EXCEEDED"] == [
        ("error", "CONCURRENCY_LIMIT_EXCEEDED")
    ]


def test_viewer_requires_explicit_contract_grant_and_cannot_retry(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    organization, reviewer, contract, file_id = _seed_facts(session_factory)
    viewer = User(
        id=uuid4(),
        email="viewer-9a@example.com",
        normalized_email="viewer-9a@example.com",
        display_name="查看者",
        password_hash=PasswordHasher().hash(PASSWORD),
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(viewer)
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=organization.id,
                user_id=viewer.id,
                email=viewer.email,
                normalized_email=viewer.normalized_email,
                display_name=viewer.display_name,
                role="viewer",
                status="active",
            )
        )
        unit_of_work.commit()
    reviewer_csrf = _login(auth_client, reviewer.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=reviewer_csrf,
        key="review-viewer-1",
    )
    viewer_csrf = _login(auth_client, viewer.email)
    no_grant = auth_client.get(
        f"/api/v1/review-tasks/{task['id']}",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert no_grant.status_code == 404
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(
            ContractAccessGrant(
                id=uuid4(),
                organization_id=organization.id,
                contract_id=contract.id,
                user_id=viewer.id,
                access_level="read",
            )
        )
        unit_of_work.commit()
    allowed = auth_client.get(
        f"/api/v1/review-tasks/{task['id']}",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert allowed.status_code == 200
    retry = auth_client.post(
        f"/api/v1/review-tasks/{task['id']}/retry",
        headers=_headers(viewer_csrf, **{"Idempotency-Key": "viewer-retry"}),
        json={},
    )
    assert retry.status_code == 403


def test_support_access_can_read_task_but_cannot_retry(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    organization, reviewer, contract, file_id = _seed_facts(session_factory)
    platform_admin = User(
        id=uuid4(),
        email="platform-review-9a@example.com",
        normalized_email="platform-review-9a@example.com",
        display_name="平台支持",
        password_hash=PasswordHasher().hash(PASSWORD),
        is_platform_admin=True,
    )
    grant_id = uuid4()
    now = datetime.now(UTC)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(platform_admin)
        session.flush()
        session.add(
            SupportAccessGrant(
                id=grant_id,
                organization_id=organization.id,
                platform_admin_user_id=platform_admin.id,
                reason="审核任务只读排查",
                status="active",
                granted_by=reviewer.id,
                expires_at=now + timedelta(hours=1),
            )
        )
        unit_of_work.commit()
    reviewer_csrf = _login(auth_client, reviewer.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=reviewer_csrf,
        key="review-support-read",
    )
    platform_csrf = _login(auth_client, platform_admin.email)
    readable = auth_client.get(
        f"/api/v1/review-tasks/{task['id']}",
        headers={"X-Support-Access-Grant": str(grant_id)},
    )
    assert readable.status_code == 200
    retry = auth_client.post(
        f"/api/v1/review-tasks/{task['id']}/retry",
        headers=_headers(
            platform_csrf,
            **{
                "X-Support-Access-Grant": str(grant_id),
                "Idempotency-Key": "review-support-retry",
            },
        ),
        json={},
    )
    assert retry.status_code == 404


def test_task_resource_resolves_tenant_without_organization_header(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    organization, user, contract, file_id = _seed_facts(session_factory)
    second_organization = Organization(id=uuid4(), name="第二审核企业")
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(second_organization)
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=second_organization.id,
                user_id=user.id,
                email=user.email,
                normalized_email=user.normalized_email,
                display_name=user.display_name,
                role="reviewer",
                status="active",
            )
        )
        unit_of_work.commit()
    csrf = _login(auth_client, user.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-tenant-resource-1",
    )
    response = auth_client.get(f"/api/v1/review-tasks/{task['id']}")
    assert response.status_code == 200, response.text
    assert response.json()["contract_id"] == str(contract.id)
    assert organization.id != second_organization.id


def test_worker_duplicate_claim_failure_retry_and_lease_recovery(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    _, user, contract, file_id = _seed_facts(session_factory)
    csrf = _login(auth_client, user.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-worker-1",
    )
    task_id = UUID(str(task["id"]))
    with session_factory() as session:
        first = claim_next_stage(session, task_id=task_id, lease_owner="worker-a")
        second = claim_next_stage(session, task_id=task_id, lease_owner="worker-b")
        assert first is not None
        assert second is None

    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        run = session.scalar(select(ReviewStageRun).where(ReviewStageRun.review_task_id == task_id))
        assert run is not None
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        unit_of_work.commit()
    recovery_executor = FakeStageExecutor()
    with session_factory() as session:
        recovered = recover_expired_leases(session, executor=recovery_executor)
        assert recovered == [task_id]
    assert recovery_executor.compensated_stages == ["parsing"]
    with session_factory() as session:
        retryable = session.scalar(
            select(ReviewStageRun).where(ReviewStageRun.review_task_id == task_id)
        )
        assert retryable is not None and retryable.status == "retryable"
    with session_factory() as session:
        executor = FakeStageExecutor(failing_stages=["parsing"])
        process_review_task(session, task_id=task_id, executor=executor)
        failed = session.get(ReviewTask, task_id)
        assert failed is not None and failed.status == "failed"

    retried = auth_client.post(
        f"/api/v1/review-tasks/{task_id}/retry",
        headers=_headers(csrf, **{"Idempotency-Key": "review-worker-retry"}),
        json={},
    )
    assert retried.status_code == 202, retried.text
    for _ in range(6):
        with session_factory() as session:
            process_review_task(session, task_id=task_id, executor=FakeStageExecutor())
    with session_factory() as session:
        completed = session.get(ReviewTask, task_id)
        assert completed is not None and completed.status == "pending_review"
        assert session.scalar(
            select(ReviewStageRun).where(
                ReviewStageRun.review_task_id == task_id,
                ReviewStageRun.attempt_no == 2,
            )
        ) is not None


def test_retry_limit_keeps_failed_task_without_new_attempt(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    _, user, contract, file_id = _seed_facts(session_factory)
    csrf = _login(auth_client, user.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-retry-limit-create",
    )
    task_id = UUID(str(task["id"]))
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        stored = session.get(ReviewTask, task_id)
        assert stored is not None
        stored.status = "failed"
        stored.retry_count = 3
        stored.error_code = "STAGE_EXECUTION_FAILED"
        stored.error_message = "阶段执行失败，请重试。"
        unit_of_work.commit()
    response = auth_client.post(
        f"/api/v1/review-tasks/{task_id}/retry",
        headers=_headers(csrf, **{"Idempotency-Key": "review-retry-limit"}),
        json={},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RETRY_LIMIT_EXCEEDED"
    with session_factory() as session:
        stored = session.get(ReviewTask, task_id)
        assert stored is not None and stored.status == "failed" and stored.retry_count == 3
        stage_runs = list(
            session.scalars(
                select(ReviewStageRun).where(ReviewStageRun.review_task_id == task_id)
            )
        )
        assert len(stage_runs) == 1


def test_archive_is_blocked_by_active_task_and_preserves_failed_history(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    _, user, contract, file_id = _seed_facts(session_factory)
    csrf = _login(auth_client, user.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-archive-1",
    )
    blocked = auth_client.post(
        f"/api/v1/contracts/{contract.id}/archive",
        headers=_headers(csrf),
        json={},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "ACTIVE_REVIEW_EXISTS"
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        stored = session.get(ReviewTask, UUID(str(task["id"])))
        assert stored is not None
        stored.status = "failed"
        stored.error_code = "STAGE_EXECUTION_FAILED"
        stored.error_message = "阶段执行失败，请重试。"
        unit_of_work.commit()
    archived = auth_client.post(
        f"/api/v1/contracts/{contract.id}/archive",
        headers=_headers(csrf),
        json={},
    )
    assert archived.status_code == 200
    with session_factory() as session:
        stored = session.get(ReviewTask, UUID(str(task["id"])))
        assert stored is not None and stored.status == "failed"


def test_concurrent_review_creation_and_archive_have_one_transaction_winner(
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    organization, user, contract, file_id = _seed_facts(session_factory)
    with session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
        )
        assert membership is not None
        actor = TenantContext(
            organization_id=organization.id,
            user_id=user.id,
            membership_id=membership.id,
        )
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    barrier = Barrier(2)

    def create() -> str:
        barrier.wait(timeout=10)
        with session_factory() as session:
            try:
                create_review_task(
                    session,
                    actor=actor,
                    contract_id=contract.id,
                    body=CreateReviewTaskRequest(contract_file_id=file_id),
                    idempotency_key="review-archive-race-create",
                    request_id="review-archive-race-create",
                )
            except ApplicationError as exc:
                return exc.code
        return "CREATED"

    def archive() -> str:
        barrier.wait(timeout=10)
        with session_factory() as session:
            try:
                archive_contract(
                    session,
                    actor=actor,
                    contract_id=contract.id,
                    request_id="review-archive-race-archive",
                )
            except ApplicationError as exc:
                return exc.code
        return "ARCHIVED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [executor.submit(create), executor.submit(archive)]
        ]
    assert sorted(results) in (
        ["ACTIVE_REVIEW_EXISTS", "CREATED"],
        ["ARCHIVED", "CONTRACT_ARCHIVED"],
    )


def test_orphaned_pending_task_can_be_requeued(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    _, user, contract, file_id = _seed_facts(session_factory)
    csrf = _login(auth_client, user.email)
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task", lambda _task_id: None
    )
    task = _create_task(
        auth_client,
        contract_id=contract.id,
        file_id=file_id,
        csrf=csrf,
        key="review-orphan-1",
    )
    queued: list[UUID] = []
    monkeypatch.setattr(
        "backend.app.modules.reviews.service._enqueue_review_task",
        lambda task_id: queued.append(task_id),
    )
    with session_factory() as session:
        assert requeue_orphaned_tasks(session) == [UUID(str(task["id"]))]
    assert queued == [UUID(str(task["id"]))]


def test_review_openapi_projects_phase9a_contract(auth_client: TestClient) -> None:
    paths = auth_client.app.openapi()["paths"]

    create = paths["/api/v1/contracts/{contract_id}/reviews"]["post"]
    assert create["responses"]["202"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/ReviewTaskResponse"
    )
    assert "Idempotency-Key" in {
        parameter["name"] for parameter in create["parameters"]
    }

    get = paths["/api/v1/review-tasks/{review_task_id}"]["get"]
    assert "include_stage_runs" in {
        parameter["name"] for parameter in get["parameters"]
    }
    assert get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/ReviewTaskResponse"
    )

    retry = paths["/api/v1/review-tasks/{review_task_id}/retry"]["post"]
    assert retry["responses"]["202"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/RetryReviewTaskResponse"
    )
    assert "Idempotency-Key" in {
        parameter["name"] for parameter in retry["parameters"]
    }
