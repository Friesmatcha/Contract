from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.contracts.models import ContractAccessGrant
from backend.app.modules.identity.models import (
    Organization,
    OrganizationMembership,
    SupportAccessGrant,
    User,
)
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import UnitOfWork

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


def _create_contract(
    client: TestClient,
    *,
    csrf_token: str,
    organization_id: UUID,
    title: str,
    key: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/contracts",
        headers=_csrf_headers(
            csrf_token,
            **{
                "X-Organization-ID": str(organization_id),
                "Idempotency-Key": key,
            },
        ),
        json={"title": title, "declared_type": "purchase"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def test_contract_catalog_supports_idempotency_cursor_filters_and_versioned_lifecycle(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "合同目录企业")
    admin = _seed_user(
        session_factory,
        email="admin@example.com",
        organization=organization,
        role="org_admin",
    )
    csrf_token = _login(auth_client, admin.email)

    created = _create_contract(
        auth_client,
        csrf_token=csrf_token,
        organization_id=organization.id,
        title="采购框架合同",
        key="contract-create-1",
    )
    replayed = _create_contract(
        auth_client,
        csrf_token=csrf_token,
        organization_id=organization.id,
        title="采购框架合同",
        key="contract-create-1",
    )
    assert created["id"] == replayed["id"]
    assert str(created["display_no"]).startswith("CTR-")
    assert created["current_file"] is None
    assert created["files"] == []

    second = _create_contract(
        auth_client,
        csrf_token=csrf_token,
        organization_id=organization.id,
        title="销售补充协议",
        key="contract-create-2",
    )
    listed = auth_client.get(
        "/api/v1/contracts",
        headers={"X-Organization-ID": str(organization.id)},
        params={"q": "协议", "sort": "title", "direction": "asc", "limit": 1},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [second["id"]]

    invalid_cursor = auth_client.get(
        "/api/v1/contracts",
        headers={"X-Organization-ID": str(organization.id)},
        params={"cursor": "A"},
    )
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"]["code"] == "VALIDATION_ERROR"

    first_page = auth_client.get(
        "/api/v1/contracts",
        headers={"X-Organization-ID": str(organization.id)},
        params={
            "sort": "title",
            "direction": "asc",
            "limit": 1,
            "owner_id": str(admin.id),
        },
    )
    assert first_page.status_code == 200
    assert first_page.json()["has_more"] is True
    next_page = auth_client.get(
        "/api/v1/contracts",
        headers={"X-Organization-ID": str(organization.id)},
        params={
            "sort": "title",
            "direction": "asc",
            "limit": 1,
            "cursor": first_page.json()["next_cursor"],
        },
    )
    assert next_page.status_code == 200
    assert [item["id"] for item in next_page.json()["items"]] == [second["id"]]

    detail = auth_client.get(
        f"/api/v1/contracts/{created['id']}",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert detail.status_code == 200
    assert detail.json()["latest_review"] is None

    updated = auth_client.patch(
        f"/api/v1/contracts/{created['id']}",
        headers=_csrf_headers(csrf_token),
        json={"title": "采购框架合同（修订）", "version": created["version"]},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    stale = auth_client.patch(
        f"/api/v1/contracts/{created['id']}",
        headers=_csrf_headers(csrf_token),
        json={"title": "过期修改", "version": created["version"]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    archived = auth_client.post(
        f"/api/v1/contracts/{created['id']}/archive",
        headers=_csrf_headers(csrf_token),
        json={},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    blocked_edit = auth_client.patch(
        f"/api/v1/contracts/{created['id']}",
        headers=_csrf_headers(csrf_token),
        json={"title": "归档修改", "version": 3},
    )
    assert blocked_edit.status_code == 409
    assert blocked_edit.json()["error"]["code"] == "CONTRACT_ARCHIVED"

    restored = auth_client.post(
        f"/api/v1/contracts/{created['id']}/restore",
        headers=_csrf_headers(csrf_token),
        json={},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["archived_at"] is None

    with session_factory() as session:
        actions = session.scalars(
            select(AuditLog.action).where(AuditLog.resource_id == UUID(str(created["id"])))
        ).all()
        assert {
            "contract.created",
            "contract.updated",
            "contract.archived",
            "contract.restored",
        }.issubset(set(actions))


def test_viewer_access_is_explicit_and_cross_organization_resources_are_hidden(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "授权企业")
    other_organization = _seed_organization(session_factory, "另一授权企业")
    admin = _seed_user(
        session_factory,
        email="admin-access@example.com",
        organization=organization,
        role="org_admin",
    )
    viewer = _seed_user(
        session_factory,
        email="viewer-access@example.com",
        organization=organization,
        role="viewer",
    )
    other_viewer = _seed_user(
        session_factory,
        email="viewer-other@example.com",
        organization=other_organization,
        role="viewer",
    )
    csrf_token = _login(auth_client, admin.email)
    contract = _create_contract(
        auth_client,
        csrf_token=csrf_token,
        organization_id=organization.id,
        title="仅授权合同",
        key="contract-access-create",
    )

    viewer_csrf = _login(auth_client, viewer.email)
    no_access = auth_client.get(
        "/api/v1/contracts",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert no_access.status_code == 200
    assert no_access.json()["items"] == []
    hidden = auth_client.get(
        f"/api/v1/contracts/{contract['id']}",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "CONTRACT_NOT_FOUND"
    forbidden_write = auth_client.patch(
        f"/api/v1/contracts/{contract['id']}",
        headers=_csrf_headers(viewer_csrf),
        json={"title": "viewer write", "version": 1},
    )
    assert forbidden_write.status_code == 403

    admin_csrf = _login(auth_client, admin.email)
    granted = auth_client.put(
        f"/api/v1/contracts/{contract['id']}/access-grants/{viewer.id}",
        headers=_csrf_headers(admin_csrf),
        json={"access_level": "read"},
    )
    assert granted.status_code == 200
    assert granted.json() == {
        "contract_id": contract["id"],
        "user_id": str(viewer.id),
        "access_level": "read",
    }
    replayed_grant = auth_client.put(
        f"/api/v1/contracts/{contract['id']}/access-grants/{viewer.id}",
        headers=_csrf_headers(admin_csrf),
        json={"access_level": "read"},
    )
    assert replayed_grant.status_code == 200

    viewer_csrf = _login(auth_client, viewer.email)
    visible = auth_client.get(
        "/api/v1/contracts",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == [contract["id"]]
    visible_detail = auth_client.get(
        f"/api/v1/contracts/{contract['id']}",
        headers={"X-Organization-ID": str(organization.id)},
    )
    assert visible_detail.status_code == 200

    admin_csrf = _login(auth_client, admin.email)
    cross_org = auth_client.put(
        f"/api/v1/contracts/{contract['id']}/access-grants/{other_viewer.id}",
        headers=_csrf_headers(admin_csrf),
        json={"access_level": "read"},
    )
    assert cross_org.status_code == 409
    assert cross_org.json()["error"]["code"] == "CROSS_ORGANIZATION_ACCESS"

    revoke = auth_client.delete(
        f"/api/v1/contracts/{contract['id']}/access-grants/{viewer.id}",
        headers=_csrf_headers(admin_csrf),
    )
    assert revoke.status_code == 204
    repeat_revoke = auth_client.delete(
        f"/api/v1/contracts/{contract['id']}/access-grants/{viewer.id}",
        headers=_csrf_headers(admin_csrf),
    )
    assert repeat_revoke.status_code == 204

    with session_factory() as session:
        assert session.scalar(
            select(ContractAccessGrant).where(
                ContractAccessGrant.contract_id == UUID(str(contract["id"])),
            )
        ) is None
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "contract.access_granted")
        ) is not None
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "contract.access_revoked")
        ) is not None


def test_platform_support_grant_can_read_contract_json_but_cannot_write(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "支持访问企业")
    admin = _seed_user(
        session_factory,
        email="admin-support@example.com",
        organization=organization,
        role="org_admin",
    )
    platform_admin = _seed_user(
        session_factory,
        email="platform-support@example.com",
        is_platform_admin=True,
    )
    csrf_token = _login(auth_client, admin.email)
    contract = _create_contract(
        auth_client,
        csrf_token=csrf_token,
        organization_id=organization.id,
        title="支持只读合同",
        key="contract-support-create",
    )
    now = datetime.now(UTC)
    grant_id = uuid4()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(
            SupportAccessGrant(
                id=grant_id,
                organization_id=organization.id,
                platform_admin_user_id=platform_admin.id,
                reason="排查合同目录",
                status="active",
                granted_by=admin.id,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        unit_of_work.commit()

    support_csrf = _login(auth_client, platform_admin.email)
    headers = {"X-Support-Access-Grant": str(grant_id)}
    listed = auth_client.get("/api/v1/contracts", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [contract["id"]]
    detail = auth_client.get(f"/api/v1/contracts/{contract['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == contract["id"]
    write = auth_client.patch(
        f"/api/v1/contracts/{contract['id']}",
        headers={**headers, **_csrf_headers(support_csrf)},
        json={"title": "不允许写", "version": 1},
    )
    assert write.status_code == 404


def test_contract_openapi_projects_phase5_paths(auth_client: TestClient) -> None:
    paths = auth_client.app.openapi()["paths"]
    expected_methods = {
        "/api/v1/contracts": {"get", "post"},
        "/api/v1/contracts/{contract_id}": {"get", "patch"},
        "/api/v1/contracts/{contract_id}/archive": {"post"},
        "/api/v1/contracts/{contract_id}/restore": {"post"},
        "/api/v1/contracts/{contract_id}/access-grants/{user_id}": {"put", "delete"},
    }
    for path, methods in expected_methods.items():
        assert path in paths
        assert methods <= set(paths[path])
