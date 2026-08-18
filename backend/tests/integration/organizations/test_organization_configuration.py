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
    PlatformModelConfiguration,
    User,
)
from backend.app.modules.identity.organization import require_organization_member
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import UnitOfWork

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"


def _seed_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    is_platform_admin: bool = False,
    organization: Organization | None = None,
    role: str = "reviewer",
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


def _seed_organization(session_factory: sessionmaker[Session], name: str) -> Organization:
    organization = Organization(id=uuid4(), name=name)
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(organization)
        unit_of_work.commit()
    return organization


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


def test_platform_organization_create_is_idempotent_and_creates_pending_admin(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    platform = _seed_user(session_factory, email="platform@example.com", is_platform_admin=True)
    csrf_token = _login(auth_client, platform.email)
    body = {
        "name": "示例企业",
        "initial_admin_email": "admin@example.com",
        "retention_days": 90,
    }
    headers = _csrf_headers(csrf_token, **{"Idempotency-Key": "create-org-1"})

    created = auth_client.post("/api/v1/platform/organizations", headers=headers, json=body)
    replayed = auth_client.post("/api/v1/platform/organizations", headers=headers, json=body)

    assert created.status_code == replayed.status_code == 201
    assert created.json()["id"] == replayed.json()["id"]
    assert created.json()["settings"]["retention_days"] == 90
    assert "secret_ref" not in created.text
    with session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == created.json()["id"]
            )
        )
        assert membership is not None
        assert membership.role == "org_admin"
        assert membership.status == "pending_invitation"
        assert membership.user_id is None
        assert session.scalar(select(AuthOneTimeToken)) is None
        assert (
            session.scalar(select(AuditLog).where(AuditLog.action == "organization.created"))
            is not None
        )

    reused = auth_client.post(
        "/api/v1/platform/organizations",
        headers=headers,
        json={**body, "name": "另一家企业"},
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_platform_organization_permissions_name_conflict_and_cursor_sorting(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    platform = _seed_user(session_factory, email="platform@example.com", is_platform_admin=True)
    reviewer = _seed_user(session_factory, email="reviewer@example.com")
    _seed_organization(session_factory, "Beta Corp")
    _seed_organization(session_factory, "Alpha Corp")
    csrf_token = _login(auth_client, platform.email)

    first = auth_client.get(
        "/api/v1/platform/organizations?sort=name&direction=asc&limit=1"
    )
    assert first.status_code == 200
    assert first.json()["items"][0]["name"] == "Alpha Corp"
    assert first.json()["has_more"] is True
    next_page = auth_client.get(
        "/api/v1/platform/organizations",
        params={
            "sort": "name",
            "direction": "asc",
            "limit": 1,
            "cursor": first.json()["next_cursor"],
        },
    )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["name"] == "Beta Corp"

    created = auth_client.post(
        "/api/v1/platform/organizations",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "create-org-2"}),
        json={"name": "大小写冲突", "initial_admin_email": "admin@example.com"},
    )
    assert created.status_code == 201
    conflict = auth_client.post(
        "/api/v1/platform/organizations",
        headers=_csrf_headers(csrf_token, **{"Idempotency-Key": "create-org-3"}),
        json={"name": "  大小写冲突  ", "initial_admin_email": "other@example.com"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ORGANIZATION_NAME_CONFLICT"

    renamed = auth_client.patch(
        f"/api/v1/platform/organizations/{created.json()['id']}",
        headers=_csrf_headers(csrf_token),
        json={"name": "  beta corp ", "version": 1},
    )
    assert renamed.status_code == 409
    assert renamed.json()["error"]["code"] == "ORGANIZATION_NAME_CONFLICT"

    _login(auth_client, reviewer.email)
    forbidden = auth_client.get("/api/v1/platform/organizations")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_platform_organization_update_checks_version_and_disables_member_sessions(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "待停用企业")
    actor = _seed_user(
        session_factory,
        email="platform@example.com",
        is_platform_admin=True,
        organization=organization,
        role="org_admin",
    )
    csrf_token = _login(auth_client, actor.email)

    stale = auth_client.patch(
        f"/api/v1/platform/organizations/{organization.id}",
        headers=_csrf_headers(csrf_token),
        json={"name": "新的名字", "version": 99},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    disabled = auth_client.patch(
        f"/api/v1/platform/organizations/{organization.id}",
        headers=_csrf_headers(csrf_token),
        json={"status": "disabled", "version": 1},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["version"] == 2
    assert auth_client.get("/api/v1/auth/session").status_code == 401
    with session_factory() as session:
        revoked = session.scalar(
            select(AuthSession).where(
                AuthSession.user_id == actor.id,
                AuthSession.revoked_at.is_not(None),
            )
        )
        assert revoked is not None


def test_organization_profile_and_settings_enforce_tenant_roles_and_versions(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "设置企业")
    other_organization = _seed_organization(session_factory, "其他企业")
    admin = _seed_user(
        session_factory,
        email="admin@example.com",
        organization=organization,
        role="org_admin",
    )
    reviewer = _seed_user(
        session_factory,
        email="reviewer@example.com",
        organization=organization,
        role="reviewer",
    )
    outsider = _seed_user(
        session_factory,
        email="outsider@example.com",
        organization=other_organization,
        role="viewer",
    )

    reviewer_csrf = _login(auth_client, reviewer.email)
    profile = auth_client.get(f"/api/v1/organizations/{organization.id}")
    assert profile.status_code == 200
    assert profile.json()["my_role"] == "reviewer"
    assert profile.json()["permissions"] == [
        "organization:read",
        "contracts:read",
        "contracts:create",
        "reviews:write",
        "warnings:write",
    ]
    assert auth_client.get(f"/api/v1/organizations/{organization.id}/settings").status_code == 403
    reviewer_update = auth_client.patch(
        f"/api/v1/organizations/{organization.id}/settings",
        headers=_csrf_headers(reviewer_csrf),
        json={"page_limit": 50, "version": 1},
    )
    assert reviewer_update.status_code == 403
    assert reviewer_update.json()["error"]["code"] == "ORG_ADMIN_REQUIRED"

    _login(auth_client, outsider.email)
    hidden = auth_client.get(f"/api/v1/organizations/{organization.id}")
    assert hidden.status_code == 404

    admin_csrf = _login(auth_client, admin.email)
    initial = auth_client.get(f"/api/v1/organizations/{organization.id}/settings")
    assert initial.status_code == 200
    assert initial.json() == {
        "file_size_limit_bytes": 20 * 1024 * 1024,
        "page_limit": 100,
        "concurrent_review_limit": 3,
        "warn_on_medium_risk": False,
        "ocr_low_confidence_threshold": 0.8,
        "retention_days": 180,
        "report_watermark": "仅供内部审核",
        "version": 1,
    }
    updated = auth_client.patch(
        f"/api/v1/organizations/{organization.id}/settings",
        headers=_csrf_headers(admin_csrf),
        json={"warn_on_medium_risk": True, "retention_days": 30, "version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["warn_on_medium_risk"] is True
    assert updated.json()["retention_days"] == 30
    assert updated.json()["version"] == 2
    stale = auth_client.patch(
        f"/api/v1/organizations/{organization.id}/settings",
        headers=_csrf_headers(admin_csrf),
        json={"page_limit": 50, "version": 1},
    )
    assert stale.status_code == 409
    unknown = auth_client.patch(
        f"/api/v1/organizations/{organization.id}/settings",
        headers=_csrf_headers(admin_csrf),
        json={"model_api_key": "forbidden", "version": 2},
    )
    assert unknown.status_code == 422
    with session_factory() as session:
        persisted = session.get(Organization, organization.id)
        assert persisted is not None
        assert persisted.retention_days == 30
        assert persisted.settings_json["retention_days"] == 30
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "organization.settings_updated")
        )
        assert audit is not None
        assert "model_api_key" not in str(audit.after_summary_json)


def test_organization_authorization_does_not_commit_unrelated_changes(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "事务边界企业")
    member = _seed_user(
        session_factory,
        email="transaction-boundary@example.com",
        organization=organization,
        role="reviewer",
    )

    with session_factory() as session:
        loaded = session.get(Organization, organization.id)
        assert loaded is not None
        loaded.name = "不应被授权检查提交"
        require_organization_member(
            session,
            organization_id=organization.id,
            user_id=member.id,
        )
        session.rollback()

    with session_factory() as session:
        persisted = session.get(Organization, organization.id)
        assert persisted is not None
        assert persisted.name == "事务边界企业"


def test_disabled_organization_is_hidden_from_member_profile_and_settings(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "已停用企业")
    member = _seed_user(
        session_factory,
        email="disabled-member@example.com",
        organization=organization,
        role="org_admin",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.execute(
            Organization.__table__.update()
            .where(Organization.id == organization.id)
            .values(status="disabled")
        )
        unit_of_work.commit()

    _login(auth_client, member.email)
    profile = auth_client.get(f"/api/v1/organizations/{organization.id}")
    settings = auth_client.get(f"/api/v1/organizations/{organization.id}/settings")
    assert profile.status_code == settings.status_code == 404
    assert profile.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"
    assert settings.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"


def test_platform_model_configuration_hides_environment_secret_and_enforces_access(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    platform = _seed_user(session_factory, email="platform@example.com", is_platform_admin=True)
    reviewer = _seed_user(session_factory, email="reviewer@example.com")
    csrf_token = _login(auth_client, platform.email)

    configuration = auth_client.get("/api/v1/platform/model-configuration")
    assert configuration.status_code == 200
    payload = configuration.json()
    assert payload["provider"] == "qwen"
    assert payload["model"] == "qwen-test-model"
    assert payload["model_source"] == "environment"
    assert payload["secret_configured"] is True
    assert payload["organization_overrides_allowed"] is False
    assert "test-model-api-key" not in configuration.text

    updated = auth_client.patch(
        "/api/v1/platform/model-configuration",
        headers=_csrf_headers(csrf_token),
        json={"timeout_seconds": 90, "usage_tracking_enabled": False, "version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["timeout_seconds"] == 90
    assert updated.json()["usage_tracking_enabled"] is False
    assert updated.json()["version"] == 2
    stale = auth_client.patch(
        "/api/v1/platform/model-configuration",
        headers=_csrf_headers(csrf_token),
        json={"max_retries": 1, "version": 1},
    )
    assert stale.status_code == 409
    with session_factory() as session:
        stored = session.scalar(select(PlatformModelConfiguration))
        assert stored is not None
        assert stored.timeout_seconds == 90
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "platform.model_configuration_updated")
        )
        assert audit is not None
        assert "test-model-api-key" not in str(audit.after_summary_json)

    _login(auth_client, reviewer.email)
    forbidden = auth_client.get("/api/v1/platform/model-configuration")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_model_configuration_update_requires_environment_configuration(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    platform = _seed_user(session_factory, email="platform@example.com", is_platform_admin=True)
    csrf_token = _login(auth_client, platform.email)
    auth_client.app.state.settings.model_name = None
    auth_client.app.state.settings.model_api_key = None

    unavailable = auth_client.patch(
        "/api/v1/platform/model-configuration",
        headers=_csrf_headers(csrf_token),
        json={"max_retries": 2, "version": 1},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "MODEL_ENVIRONMENT_NOT_CONFIGURED"
