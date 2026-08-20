from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import OrganizationMembership, User
from backend.app.modules.reviews.models import ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import RiskFinding
from backend.app.modules.warnings.models import Notification, WarningEvent
from backend.app.modules.warnings.schemas import (
    NotificationListQuery,
    WarningEventRequest,
    WarningListQuery,
)
from backend.app.modules.warnings.service import (
    create_warning_event,
    generate_warnings,
    get_warning,
    list_notifications,
    list_warnings,
    mark_notification_read,
    unread_count,
)
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
from backend.app.shared.tenant import TenantContext
from backend.tests.integration.classification_extraction.test_results import _seed

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"


def _seed_warning_facts(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    facts = _seed(session_factory)
    admin_id = uuid4()
    admin_membership_id = uuid4()
    risk_run_id = uuid4()
    finding_id = uuid4()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        reviewer = session.get(User, facts["user_id"])
        assert reviewer is not None
        reviewer_membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == facts["organization_id"],
                OrganizationMembership.user_id == facts["user_id"],
            )
        )
        assert reviewer_membership is not None
        reviewer.password_hash = PasswordHasher().hash(PASSWORD)
        admin = User(
            id=admin_id,
            email=f"admin-{admin_id}@example.test",
            normalized_email=f"admin-{admin_id}@example.test",
            display_name="Phase 11 Admin",
            password_hash=PasswordHasher().hash(PASSWORD),
        )
        session.add(admin)
        session.flush()
        admin_membership = OrganizationMembership(
            id=admin_membership_id,
            organization_id=facts["organization_id"],
            user_id=admin_id,
            email=admin.email,
            normalized_email=admin.normalized_email,
            display_name=admin.display_name,
            role="org_admin",
            status="active",
        )
        risk_run = ReviewStageRun(
            id=risk_run_id,
            organization_id=facts["organization_id"],
            review_task_id=facts["task_id"],
            stage="risk_analysis",
            attempt_no=1,
            status="succeeded",
            input_fingerprint="f" * 64,
        )
        finding = RiskFinding(
            id=finding_id,
            organization_id=facts["organization_id"],
            review_task_id=facts["task_id"],
            stage_run_id=risk_run_id,
            document_version_id=facts["document_id"],
            evidence_span_id=facts["span_id"],
            risk_type="unlimited_liability",
            severity="high",
            title="责任范围不封顶",
            description="责任范围需要人工复核。",
            basis="原文缺少责任上限。",
            suggestion="补充责任上限。",
            confidence=0.95,
            source="rule",
            status="pending_review",
            input_fingerprint="1" * 64,
            model_fingerprint="2" * 64,
            result_fingerprint="3" * 64,
        )
        session.add_all([admin_membership, risk_run, finding])
        unit_of_work.commit()
    facts.update(
        {
            "admin_id": admin_id,
            "admin_membership_id": admin_membership_id,
            "membership_id": reviewer_membership.id,
            "risk_run_id": risk_run_id,
            "finding_id": finding_id,
        }
    )
    return facts


def _generate_warning(session_factory: sessionmaker[Session], facts: dict[str, UUID]) -> UUID:
    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        generated = generate_warnings(session, task=task)
        session.commit()
        assert len(generated) == 1
        return generated[0].id


def _tenant(facts: dict[str, UUID], *, admin: bool = False) -> TenantContext:
    return TenantContext(
        organization_id=facts["organization_id"],
        user_id=facts["admin_id" if admin else "user_id"],
        membership_id=facts["admin_membership_id" if admin else "membership_id"],
    )


def test_warning_generation_is_deduplicated_and_notifies_active_reviewers(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed_warning_facts(session_factory)
    warning_id = _generate_warning(session_factory, facts)

    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        repeated = generate_warnings(session, task=task)
        session.commit()
        notifications = list(
            session.scalars(
                select(Notification).where(Notification.warning_id == warning_id)
            )
        )
        events = list(
            session.scalars(
                select(WarningEvent).where(WarningEvent.warning_id == warning_id)
            )
        )

    assert len(repeated) == 1
    assert repeated[0].id == warning_id
    assert len(notifications) == 2
    assert all(item.delivery_status == "delivered" for item in notifications)
    assert len(events) == 1
    assert events[0].event_type == "created"


def test_warning_state_machine_enforces_assignment_notes_and_reopen_permissions(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed_warning_facts(session_factory)
    warning_id = _generate_warning(session_factory, facts)
    actor = _tenant(facts)
    admin = _tenant(facts, admin=True)

    with session_factory() as session:
        assigned = create_warning_event(
            session,
            actor=actor,
            role="reviewer",
            warning_id=warning_id,
            body=WarningEventRequest(
                type="assign",
                assignee_id=facts["user_id"],
                due_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
                note="请复核责任范围",
            ),
            request_id="test-assign",
        )
        assert assigned["assignee_id"] == facts["user_id"]
        assert assigned["note"] == "请复核责任范围"
        assert assigned["due_at"] is not None

        create_warning_event(
            session,
            actor=actor,
            role="reviewer",
            warning_id=warning_id,
            body=WarningEventRequest(type="confirm"),
            request_id="test-confirm",
        )
        create_warning_event(
            session,
            actor=actor,
            role="reviewer",
            warning_id=warning_id,
            body=WarningEventRequest(type="note", note="已核对证据"),
            request_id="test-note",
        )
        false_positive = create_warning_event(
            session,
            actor=actor,
            role="reviewer",
            warning_id=warning_id,
            body=WarningEventRequest(type="false_positive"),
            request_id="test-false-positive",
        )
        assert false_positive["to_status"] == "ignored"

        finding = session.get(RiskFinding, facts["finding_id"])
        assert finding is not None and finding.status == "false_positive"
        session.rollback()

        for event_type, body in (
            ("assign", WarningEventRequest(type="assign", assignee_id=facts["user_id"])),
            ("note", WarningEventRequest(type="note", note="不能追加")),
        ):
            with pytest.raises(ApplicationError) as error_info:
                create_warning_event(
                    session,
                    actor=actor,
                    role="reviewer",
                    warning_id=warning_id,
                    body=body,
                    request_id=f"test-invalid-{event_type}",
                )
            assert error_info.value.status_code == 409
            assert error_info.value.code == "INVALID_STATE_TRANSITION"

        with pytest.raises(ApplicationError) as error_info:
            create_warning_event(
                session,
                actor=actor,
                role="reviewer",
                warning_id=warning_id,
                body=WarningEventRequest(type="reopen"),
                request_id="test-reviewer-reopen",
            )
        assert error_info.value.status_code == 403

        reopened = create_warning_event(
            session,
            actor=admin,
            role="org_admin",
            warning_id=warning_id,
            body=WarningEventRequest(type="reopen"),
            request_id="test-admin-reopen",
        )
        assert reopened["to_status"] == "in_progress"
        create_warning_event(
            session,
            actor=actor,
            role="reviewer",
            warning_id=warning_id,
            body=WarningEventRequest(type="resolve"),
            request_id="test-resolve",
        )
        for event_type, body in (
            ("assign", WarningEventRequest(type="assign", assignee_id=facts["user_id"])),
            ("note", WarningEventRequest(type="note", note="解决后不能追加")),
        ):
            with pytest.raises(ApplicationError) as error_info:
                create_warning_event(
                    session,
                    actor=actor,
                    role="reviewer",
                    warning_id=warning_id,
                    body=body,
                    request_id=f"test-resolved-invalid-{event_type}",
                )
            assert error_info.value.status_code == 409
            assert error_info.value.code == "INVALID_STATE_TRANSITION"
        create_warning_event(
            session,
            actor=actor,
            role="reviewer",
            warning_id=warning_id,
            body=WarningEventRequest(type="close", resolution="已完成复核"),
            request_id="test-close",
        )

        for event_type, body in (
            ("assign", WarningEventRequest(type="assign", assignee_id=facts["user_id"])),
            ("note", WarningEventRequest(type="note", note="关闭后不能追加")),
        ):
            with pytest.raises(ApplicationError) as error_info:
                create_warning_event(
                    session,
                    actor=actor,
                    role="reviewer",
                    warning_id=warning_id,
                    body=body,
                    request_id=f"test-closed-invalid-{event_type}",
                )
            assert error_info.value.status_code == 409
            assert error_info.value.code == "INVALID_STATE_TRANSITION"

        reopened_closed = create_warning_event(
            session,
            actor=admin,
            role="org_admin",
            warning_id=warning_id,
            body=WarningEventRequest(type="reopen"),
            request_id="test-closed-reopen",
        )
        assert reopened_closed["to_status"] == "in_progress"


def test_notification_read_state_is_idempotent_and_separate_from_delivery(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed_warning_facts(session_factory)
    warning_id = _generate_warning(session_factory, facts)

    with session_factory() as session:
        page = list_notifications(
            session,
            user_id=facts["user_id"],
            query=NotificationListQuery(status="unread"),
        )
        assert page["items"] and page["items"][0]["warning_id"] == warning_id
        notification_id = page["items"][0]["id"]
        session.rollback()
        first = mark_notification_read(
            session, user_id=facts["user_id"], notification_id=notification_id
        )
        second = mark_notification_read(
            session, user_id=facts["user_id"], notification_id=notification_id
        )
        assert first["read_at"] == second["read_at"]
        assert unread_count(session, user_id=facts["user_id"]) == 0
        read_page = list_notifications(
            session,
            user_id=facts["user_id"],
            query=NotificationListQuery(status="read"),
        )
        assert read_page["items"][0]["status"] == "read"
        notification = session.get(Notification, notification_id)
        assert notification is not None and notification.delivery_status == "delivered"


def test_warning_api_returns_contract_validation_and_event_response(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed_warning_facts(session_factory)
    warning_id = _generate_warning(session_factory, facts)
    login = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": f"{facts['user_id']}@example.test", "password": PASSWORD},
    )
    assert login.status_code == 200
    csrf_token = str(login.json()["csrf_token"])
    organization_id = str(facts["organization_id"])

    invalid = auth_client.get(
        "/api/v1/warnings",
        headers={"X-Organization-ID": organization_id},
        params={"status": "not-a-warning-status"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    detail = auth_client.get(
        f"/api/v1/warnings/{warning_id}",
        headers={"X-Organization-ID": organization_id},
    )
    assert detail.status_code == 200
    assert detail.json()["evidence"][0]["quote"] == "甲方与乙方签订采购合同"

    event = auth_client.post(
        f"/api/v1/warnings/{warning_id}/events",
        headers={
            **ORIGIN,
            "X-CSRF-Token": csrf_token,
            "X-Organization-ID": organization_id,
        },
        json={"type": "assign", "assignee_id": str(facts["user_id"]), "note": "API 分派"},
    )
    assert event.status_code == 201
    assert event.json()["note"] == "API 分派"
    assert event.json()["due_at"] is None


def test_warning_service_list_and_detail_are_tenant_scoped(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed_warning_facts(session_factory)
    warning_id = _generate_warning(session_factory, facts)

    with session_factory() as session:
        page = list_warnings(
            session,
            organization_id=facts["organization_id"],
            viewer_user_id=None,
            query=WarningListQuery(status="pending_confirmation"),
        )
        detail = get_warning(
            session,
            organization_id=facts["organization_id"],
            warning_id=warning_id,
            viewer_user_id=None,
        )

    assert page["summary"] == {"unprocessed_count": 1, "high_count": 1}
    assert page["items"][0]["id"] == warning_id
    assert detail["events"][0]["event_type"] == "created"
