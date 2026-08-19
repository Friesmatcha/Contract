from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import (
    AuthOneTimeToken,
    AuthSession,
    Organization,
    OrganizationMembership,
    SupportAccessGrant,
    User,
)
from backend.app.modules.identity.support_access import authorize_support_access
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
from backend.tests.integration.auth.conftest import FakeMailer

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"


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


def _login(client: TestClient, email: str) -> str:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def _csrf_headers(csrf_token: str, **headers: str) -> dict[str, str]:
    return {**ORIGIN, "X-CSRF-Token": csrf_token, **headers}


def test_invite_is_idempotent_and_persists_delivery_status(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "成员企业")
    admin = _seed_user(
        session_factory, email="admin@example.com", organization=organization, role="org_admin"
    )
    csrf_token = _login(auth_client, admin.email)
    headers = _csrf_headers(csrf_token, **{"Idempotency-Key": "invite-1"})
    body = {"email": "reviewer@example.com", "role": "reviewer"}

    created = auth_client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers=headers,
        json=body,
    )
    replayed = auth_client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers=headers,
        json=body,
    )

    assert created.status_code == replayed.status_code == 201
    assert created.json()["status"] == "pending_invitation"
    assert created.json()["email_delivery_status"] == "queued"
    assert created.json()["id"] == replayed.json()["id"]
    assert len(fake_mailer.invitations) == 1

    listed = auth_client.get(f"/api/v1/organizations/{organization.id}/members")
    assert listed.status_code == 200
    member = listed.json()["items"][0]
    assert member["email"] == "reviewer@example.com"
    assert member["email_delivery_status"] == "sent"
    assert member["invited_at"] is not None
    with session_factory() as session:
        assert (
            session.scalar(
                select(AuthOneTimeToken).where(
                    AuthOneTimeToken.membership_id == UUID(member["id"]),
                    AuthOneTimeToken.used_at.is_(None),
                )
            )
            is not None
        )
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "organization.member_invited")
        )


def test_invitation_delivery_failure_is_visible_without_leaking_token(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    class FailingMailer(FakeMailer):
        def send_invitation(self, *, recipient: str, invitation_url: str) -> None:
            raise RuntimeError("smtp unavailable")

    auth_client.app.state.mailer = FailingMailer()
    organization = _seed_organization(session_factory, "投递企业")
    admin = _seed_user(
        session_factory, email="admin@example.com", organization=organization, role="org_admin"
    )
    csrf_token = _login(auth_client, admin.email)

    created = auth_client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "invite-failed"}),
        json={"email": "failed@example.com", "role": "viewer"},
    )

    assert created.status_code == 201
    assert "invite_" not in created.text
    listed = auth_client.get(f"/api/v1/organizations/{organization.id}/members")
    assert listed.json()["items"][0]["email_delivery_status"] == "failed"


def test_resend_invalidates_previous_invitation_token(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "重发企业")
    admin = _seed_user(
        session_factory, email="admin@example.com", organization=organization, role="org_admin"
    )
    csrf_token = _login(auth_client, admin.email)
    created = auth_client.post(
        f"/api/v1/organizations/{organization.id}/members",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "invite-resend-create"}),
        json={"email": "resend@example.com", "role": "reviewer"},
    )
    assert created.status_code == 201
    member_id = UUID(created.json()["id"])

    resent = auth_client.post(
        f"/api/v1/members/{member_id}/resend-invitation",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "invite-resend-1"}),
        json={},
    )
    assert resent.status_code == 202
    assert resent.json()["email_delivery_status"] == "queued"
    assert len(fake_mailer.invitations) == 2
    with session_factory() as session:
        tokens = list(
            session.scalars(
                select(AuthOneTimeToken)
                .where(AuthOneTimeToken.membership_id == member_id)
                .order_by(AuthOneTimeToken.created_at)
            )
        )
        assert len(tokens) == 2
        assert tokens[0].used_at is not None
        assert tokens[1].used_at is None


def test_member_updates_revoke_sessions_and_protect_last_admin(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "权限企业")
    admin = _seed_user(
        session_factory, email="admin@example.com", organization=organization, role="org_admin"
    )
    reviewer = _seed_user(
        session_factory, email="reviewer@example.com", organization=organization, role="reviewer"
    )
    reviewer_csrf = _login(auth_client, reviewer.email)
    _login(auth_client, admin.email)
    admin_csrf = str(auth_client.get("/api/v1/auth/session").json()["csrf_token"])

    with session_factory() as session:
        reviewer_membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == reviewer.id,
            )
        )
        assert reviewer_membership is not None
        reviewer_member_id = reviewer_membership.id
        reviewer_version = reviewer_membership.version

    updated = auth_client.patch(
        f"/api/v1/members/{reviewer_member_id}",
        headers=_csrf_headers(admin_csrf),
        json={"role": "viewer", "version": reviewer_version},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "viewer"
    with session_factory() as session:
        assert session.scalar(
            select(AuthSession).where(
                AuthSession.user_id == reviewer.id,
                AuthSession.revoked_at.is_not(None),
            )
        )

    with session_factory() as session:
        admin_membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == admin.id,
            )
        )
        assert admin_membership is not None
        admin_member_id = admin_membership.id
        admin_version = admin_membership.version
    blocked = auth_client.patch(
        f"/api/v1/members/{admin_member_id}",
        headers=_csrf_headers(admin_csrf),
        json={"role": "reviewer", "version": admin_version},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "LAST_ORG_ADMIN"
    assert reviewer_csrf

    pending_member = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        email="pending-without-user@example.com",
        normalized_email="pending-without-user@example.com",
        display_name=None,
        role="reviewer",
        status="pending_invitation",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(pending_member)
        unit_of_work.commit()
    disabled = auth_client.patch(
        f"/api/v1/members/{pending_member.id}",
        headers=_csrf_headers(admin_csrf),
        json={"status": "disabled", "version": 1},
    )
    assert disabled.status_code == 200
    cannot_activate = auth_client.patch(
        f"/api/v1/members/{pending_member.id}",
        headers=_csrf_headers(admin_csrf),
        json={"status": "active", "version": 2},
    )
    assert cannot_activate.status_code == 409
    assert cannot_activate.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_member_routes_hide_other_organizations_and_reject_non_admins(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "组织一")
    other_organization = _seed_organization(session_factory, "组织二")
    admin = _seed_user(
        session_factory, email="admin@example.com", organization=organization, role="org_admin"
    )
    reviewer = _seed_user(
        session_factory, email="reviewer@example.com", organization=organization, role="reviewer"
    )
    outsider = _seed_user(
        session_factory,
        email="outsider@example.com",
        organization=other_organization,
        role="org_admin",
    )
    _login(auth_client, reviewer.email)
    forbidden = auth_client.get(f"/api/v1/organizations/{organization.id}/members")
    assert forbidden.status_code == 403

    _login(auth_client, admin.email)
    with session_factory() as session:
        outsider_membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == outsider.id,
                OrganizationMembership.organization_id == other_organization.id,
            )
        )
        assert outsider_membership is not None
    hidden = auth_client.patch(
        f"/api/v1/members/{outsider_membership.id}",
        headers=_csrf_headers(str(auth_client.get("/api/v1/auth/session").json()["csrf_token"])),
        json={"role": "viewer", "version": outsider_membership.version},
    )
    assert hidden.status_code == 404


def test_support_access_is_limited_audited_and_revocable(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "支持企业")
    admin = _seed_user(
        session_factory, email="admin@example.com", organization=organization, role="org_admin"
    )
    platform = _seed_user(
        session_factory, email="platform@example.com", is_platform_admin=True
    )
    regular = _seed_user(session_factory, email="regular@example.com")
    csrf_token = _login(auth_client, admin.email)
    expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    body = {
        "platform_admin_user_id": str(platform.id),
        "reason": "排查报告生成失败",
        "expires_at": expires_at,
    }

    created = auth_client.post(
        f"/api/v1/organizations/{organization.id}/support-access-grants",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "grant-1"}),
        json=body,
    )
    assert created.status_code == 201
    grant_id = created.json()["id"]

    duplicate = auth_client.post(
        f"/api/v1/organizations/{organization.id}/support-access-grants",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "grant-2"}),
        json=body,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ACTIVE_SUPPORT_GRANT_EXISTS"

    too_long = auth_client.post(
        f"/api/v1/organizations/{organization.id}/support-access-grants",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "grant-long"}),
        json={**body, "expires_at": (datetime.now(UTC) + timedelta(hours=5)).isoformat()},
    )
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "SUPPORT_GRANT_DURATION_INVALID"

    wrong_target = auth_client.post(
        f"/api/v1/organizations/{organization.id}/support-access-grants",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "grant-regular"}),
        json={**body, "platform_admin_user_id": str(regular.id)},
    )
    assert wrong_target.status_code == 404
    assert wrong_target.json()["error"]["code"] == "PLATFORM_ADMIN_NOT_FOUND"

    listed = auth_client.get(f"/api/v1/organizations/{organization.id}/support-access-grants")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "active"

    with monkeypatch.context() as context:
        context.setattr(
            "backend.app.modules.identity.support_access._now",
            lambda: datetime.now(UTC) + timedelta(hours=5),
        )
        replayed = auth_client.post(
            f"/api/v1/organizations/{organization.id}/support-access-grants",
            headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "grant-1"}),
            json=body,
        )
    assert replayed.status_code == 201
    assert replayed.json()["id"] == grant_id

    with session_factory() as session:
        authorized = authorize_support_access(
            session,
            grant_id=UUID(grant_id),
            platform_admin_user_id=platform.id,
            request_id="req-support-use",
        )
        assert authorized.id == UUID(grant_id)
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "support_access.grant_used")
        )

    revoked = auth_client.delete(
        f"/api/v1/organizations/{organization.id}/support-access-grants/{grant_id}",
        headers=_csrf_headers(csrf_token),
    )
    repeated = auth_client.delete(
        f"/api/v1/organizations/{organization.id}/support-access-grants/{grant_id}",
        headers=_csrf_headers(csrf_token),
    )
    assert revoked.status_code == repeated.status_code == 204
    with session_factory() as session:
        with pytest.raises(ApplicationError, match="SUPPORT_ACCESS_REQUIRED"):
            authorize_support_access(
                session,
                grant_id=UUID(grant_id),
                platform_admin_user_id=platform.id,
                request_id="req-support-after-revoke",
            )
        grant = session.get(SupportAccessGrant, UUID(grant_id))
        assert grant is not None
        assert grant.status == "revoked"
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "support_access.grant_revoked")
        )
