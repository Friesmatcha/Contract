import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.notifications.smtp import UnavailableMailer
from backend.app.modules.identity.models import (
    AuthOneTimeToken,
    AuthSession,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.modules.identity.service import (
    issue_invitation_token,
    load_authenticated_session,
    rotate_csrf,
)
from backend.app.shared.audit import AuditLog
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


def _seed_pending_invitation(session_factory: sessionmaker[Session]) -> OrganizationMembership:
    organization = Organization(id=uuid4(), name="受邀企业")
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        email="invitee@example.com",
        normalized_email="invitee@example.com",
        display_name="受邀审核员",
        role="reviewer",
        status="pending_invitation",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([organization, membership])
        unit_of_work.commit()
    return membership


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
    concurrent_refresh = auth_client.get("/api/v1/auth/session")
    assert concurrent_refresh.status_code == 200
    current_csrf_token = concurrent_refresh.json()["csrf_token"]
    assert current_csrf_token != csrf_token

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


def test_public_auth_requests_require_origin(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/auth/login",
        json={"email": "legal@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_INVALID"


def test_invalid_login_email_uses_contract_status_and_audit(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": "invalid", "password": "correct-horse-battery"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    with session_factory() as session:
        event = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.login_failed", AuditLog.actor_id.is_(None)
            )
        )
    assert event is not None
    assert event.after_summary_json == {"reason": "invalid_credentials"}


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


def test_password_reset_accepts_maximum_password_length(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_active_user(session_factory)
    requested = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": "legal@example.com"},
    )
    assert requested.status_code == 202
    token = parse_qs(urlparse(fake_mailer.password_resets[0][1]).query)["token"][0]
    response = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "a" * 128},
    )
    assert response.status_code == 204


def test_password_reset_rejects_expired_token_and_oversized_password(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_active_user(session_factory)
    requested = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": "legal@example.com"},
    )
    assert requested.status_code == 202
    token = parse_qs(urlparse(fake_mailer.password_resets[0][1]).query)["token"][0]

    oversized = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "a" * 129},
    )
    assert oversized.status_code == 422

    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.execute(
            update(AuthOneTimeToken)
            .where(AuthOneTimeToken.token_hash.is_not(None))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        unit_of_work.commit()
    expired = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "new-correct-password"},
    )
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_login_rate_limit_normalizes_email_and_audits_failures(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    user = _seed_active_user(session_factory)
    for email in ["LEGAL@EXAMPLE.COM", " legal@example.com "] * 3:
        response = auth_client.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"email": email, "password": "wrong-password"},
        )
        if response.status_code == 429:
            break
    assert response.status_code == 429

    with session_factory() as session:
        events = list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "auth.login_failed",
                    AuditLog.actor_id == user.id,
                )
            )
        )
    assert len(events) == 5
    assert all(event.before_summary_json is None for event in events)
    assert all(event.after_summary_json == {"reason": "invalid_credentials"} for event in events)


def test_reset_rate_limit_normalizes_email(auth_client: TestClient) -> None:
    for email in ["LEGAL@EXAMPLE.COM", " legal@example.com "] * 2:
        response = auth_client.post(
            "/api/v1/auth/password-reset/request",
            headers=ORIGIN,
            json={"email": email},
        )
        if response.status_code == 429:
            break
    assert response.status_code == 429


def test_disabled_login_is_forbidden_and_audited(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    user = _seed_active_user(session_factory)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.execute(
            User.__table__.update().where(User.id == user.id).values(status="disabled")
        )
        unit_of_work.commit()

    response = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": "legal@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_DISABLED"
    with session_factory() as session:
        event = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.login_failed", AuditLog.actor_id == user.id
            )
        )
    assert event is not None
    assert event.after_summary_json == {"reason": "user_disabled"}


def test_password_reset_failure_is_logged_without_sensitive_values(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
    caplog,
) -> None:
    _seed_active_user(session_factory)

    class FailingMailer(FakeMailer):
        def send_password_reset(self, *, recipient: str, reset_url: str) -> None:
            raise RuntimeError("smtp failed for recipient")

    auth_client.app.state.mailer = FailingMailer()
    response = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": "legal@example.com"},
    )
    assert response.status_code == 202
    delivery_logs = [
        record for record in caplog.records if record.message == "auth_email_delivery_failed"
    ]
    assert delivery_logs
    message = " ".join(str(record.__dict__) for record in delivery_logs)
    assert "legal@example.com" not in message
    assert "token" not in message.lower()


def test_password_reset_without_smtp_fails_before_account_lookup(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    user = _seed_active_user(session_factory)
    auth_client.app.state.mailer = UnavailableMailer()
    response = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": user.email},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SMTP_NOT_CONFIGURED"
    with session_factory() as session:
        assert session.scalar(select(AuthOneTimeToken)) is None
        assert (
            session.scalar(
                select(AuditLog).where(AuditLog.action == "auth.password_reset_requested")
            )
            is None
        )


def test_previous_csrf_expires_after_grace_period(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_active_user(session_factory)
    first_csrf = _login(auth_client)["csrf_token"]
    assert isinstance(first_csrf, str)
    refreshed = auth_client.get("/api/v1/auth/session")
    assert refreshed.status_code == 200

    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.execute(
            update(AuthSession).values(
                csrf_previous_expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        unit_of_work.commit()

    logout = auth_client.post(
        "/api/v1/auth/logout",
        headers={**ORIGIN, "X-CSRF-Token": first_csrf},
    )
    assert logout.status_code == 403
    assert logout.json()["error"]["code"] == "CSRF_INVALID"


def test_csrf_rotation_refreshes_locked_row_after_another_session_updates_it(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_active_user(session_factory)
    _login(auth_client)
    raw_session = auth_client.cookies.get("session")
    assert raw_session

    with session_factory() as first_session, session_factory() as second_session:
        first = load_authenticated_session(first_session, raw_session)
        second = load_authenticated_session(second_session, raw_session)
        second_token = rotate_csrf(second_session, second)
        third_token = rotate_csrf(first_session, first)

    with session_factory() as session:
        row = session.scalar(select(AuthSession).where(AuthSession.token_hash.is_not(None)))
        assert row is not None
        assert row.csrf_hash == hashlib.sha256(third_token.encode()).hexdigest()
        assert row.csrf_previous_hash == hashlib.sha256(second_token.encode()).hexdigest()


def test_trusted_proxy_forwarded_ip_is_used_for_auth_audit(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    user = _seed_active_user(session_factory)
    auth_client.app.state.settings.trusted_proxy_hops = 1
    response = auth_client.post(
        "/api/v1/auth/login",
        headers={**ORIGIN, "X-Forwarded-For": "198.51.100.42"},
        json={"email": user.email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    with session_factory() as session:
        event = session.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.login_failed", AuditLog.actor_id == user.id
            )
        )
    assert event is not None
    assert event.ip == "198.51.100.42"


def test_invitation_acceptance_handles_success_and_expiry(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    membership = _seed_pending_invitation(session_factory)
    with session_factory() as session:
        token = issue_invitation_token(session, membership_id=membership.id)
    accepted = auth_client.post(
        "/api/v1/auth/invitations/accept",
        headers=ORIGIN,
        json={
            "token": token,
            "display_name": "新审核员",
            "password": "new-correct-password",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "active"

    expired_membership = _seed_pending_invitation(session_factory)
    with session_factory() as session:
        expired_token = issue_invitation_token(session, membership_id=expired_membership.id)
        session.execute(
            update(AuthOneTimeToken)
            .where(AuthOneTimeToken.membership_id == expired_membership.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()
    expired = auth_client.post(
        "/api/v1/auth/invitations/accept",
        headers=ORIGIN,
        json={
            "token": expired_token,
            "display_name": "新审核员",
            "password": "new-correct-password",
        },
    )
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_password_reset_openapi_projects_contract_errors(auth_client: TestClient) -> None:
    responses = auth_client.app.openapi()["paths"][
        "/api/v1/auth/password-reset/request"
    ]["post"]["responses"]
    assert {"202", "422", "429", "503"}.issubset(responses)


def test_password_reset_rejects_expired_token_and_invalid_password_length(
    auth_client: TestClient,
    fake_mailer: FakeMailer,
    session_factory: sessionmaker[Session],
) -> None:
    user = _seed_active_user(session_factory)
    request = auth_client.post(
        "/api/v1/auth/password-reset/request",
        headers=ORIGIN,
        json={"email": user.email},
    )
    assert request.status_code == 202
    token = parse_qs(urlparse(fake_mailer.password_resets[0][1]).query)["token"][0]
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.execute(
            AuthOneTimeToken.__table__.update()
            .where(AuthOneTimeToken.token_hash.is_not(None))
            .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
        unit_of_work.commit()
    expired = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "new-correct-password"},
    )
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "TOKEN_EXPIRED"

    long_password = auth_client.post(
        "/api/v1/auth/password-reset/confirm",
        headers=ORIGIN,
        json={"token": token, "new_password": "x" * 129},
    )
    assert long_password.status_code == 422


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
