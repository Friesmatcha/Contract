from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import (
    AuthOneTimeToken,
    AuthSession,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.modules.identity.service import issue_invitation_token
from backend.app.shared.db import UnitOfWork
from backend.tests.integration.auth.conftest import FakeMailer

ORIGIN = {"Origin": "http://localhost:5173"}


def _seed_active_user(session_factory: sessionmaker[Session]) -> User:
    organization = Organization(id=uuid4(), name="示例企业")
    user = User(
        id=uuid4(),
        email="legal@example.com",
        normalized_email="legal@example.com",
        display_name="李法务",
        password_hash=PasswordHasher().hash("correct-horse-battery"),
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
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([organization, user])
        session.flush()
        session.add(membership)
        unit_of_work.commit()
    return user


def _login(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": "legal@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    return response.json()


def test_login_session_and_logout_enforce_origin_and_csrf(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    user = _seed_active_user(session_factory)
    with session_factory() as session:
        assert (
            session.scalar(
                select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)
            )
            is not None
        )

    payload = _login(auth_client)
    assert "session" not in payload
    assert "session_token" not in payload
    assert auth_client.cookies.get("session")
    assert payload["user"]["id"] == str(user.id)
    assert payload["organizations"][0]["role"] == "reviewer"

    refreshed = auth_client.get("/api/v1/auth/session")
    assert refreshed.status_code == 200
    csrf_token = refreshed.json()["csrf_token"]
    assert csrf_token != payload["csrf_token"]

    missing_csrf = auth_client.post("/api/v1/auth/logout", headers=ORIGIN)
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "CSRF_INVALID"

    invalid_origin = auth_client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf_token},
    )
    assert invalid_origin.status_code == 403
    assert invalid_origin.json()["error"]["code"] == "ORIGIN_INVALID"

    logout = auth_client.post(
        "/api/v1/auth/logout",
        headers={**ORIGIN, "X-CSRF-Token": csrf_token},
    )
    assert logout.status_code == 204
    assert auth_client.get("/api/v1/auth/session").status_code == 401


def test_password_reset_is_generic_one_time_and_revokes_existing_sessions(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_active_user(session_factory)
    _login(auth_client)

    unknown = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": "unknown@example.com"},
    )
    known = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": "legal@example.com"},
    )
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert len(fake_mailer.password_resets) == 1

    token = parse_qs(urlparse(fake_mailer.password_resets[0][1]).query)["token"][0]
    confirm = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "new-correct-password"},
    )
    assert confirm.status_code == 204
    assert auth_client.get("/api/v1/auth/session").status_code == 401

    reused = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "other-correct-password"},
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "TOKEN_ALREADY_USED"

    old_password = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": "legal@example.com", "password": "correct-horse-battery"},
    )
    new_password = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": "legal@example.com", "password": "new-correct-password"},
    )
    assert old_password.status_code == 401
    assert new_password.status_code == 200

    with session_factory() as session:
        assert (
            session.scalar(select(AuthSession).where(AuthSession.revoked_at.is_not(None)))
            is not None
        )
        assert (
            session.scalar(select(AuthOneTimeToken).where(AuthOneTimeToken.used_at.is_not(None)))
            is not None
        )


def test_new_and_existing_users_can_accept_a_valid_invitation(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = Organization(id=uuid4(), name="邀请组织")
    new_membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        email="new@example.com",
        normalized_email="new@example.com",
        role="viewer",
    )
    existing_user = User(
        id=uuid4(),
        email="existing@example.com",
        normalized_email="existing@example.com",
        display_name="已有用户",
        password_hash=PasswordHasher().hash("existing-password"),
    )
    existing_membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        email=existing_user.email,
        normalized_email=existing_user.normalized_email,
        role="reviewer",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([organization, existing_user])
        session.flush()
        session.add_all([new_membership, existing_membership])
        unit_of_work.commit()
    with session_factory() as session:
        new_token = issue_invitation_token(session, membership_id=new_membership.id)
    with session_factory() as session:
        existing_token = issue_invitation_token(session, membership_id=existing_membership.id)

    accepted_new = auth_client.post(
        "/api/v1/auth/invitations/accept",
        headers=ORIGIN,
        json={"token": new_token, "display_name": "新用户", "password": "new-user-password"},
    )
    accepted_existing = auth_client.post(
        "/api/v1/auth/invitations/accept",
        headers=ORIGIN,
        json={"token": existing_token},
    )
    assert accepted_new.status_code == 200
    assert accepted_new.json()["status"] == "active"
    assert accepted_existing.status_code == 200
    assert accepted_existing.json()["user_id"] == str(existing_user.id)

    reused = auth_client.post(
        "/api/v1/auth/invitations/accept",
        headers=ORIGIN,
        json={"token": new_token},
    )
    assert reused.status_code == 409
