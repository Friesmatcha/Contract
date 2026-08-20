from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.clauses.templates.models import (
    ClauseTemplate,
    ClauseTemplateVersion,
    StandardClause,
)
from backend.app.modules.clauses.templates.service import publish_version
from backend.app.modules.identity.models import Organization, OrganizationMembership, User
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import UnitOfWork
from backend.app.shared.tenant import TenantContext

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
    organization: Organization,
    role: str,
) -> User:
    user = User(
        id=uuid4(),
        email=email,
        normalized_email=email,
        display_name=email.split("@")[0],
        password_hash=PasswordHasher().hash(PASSWORD),
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(user)
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


def _write_headers(csrf_token: str, organization_id: str, **extra: str) -> dict[str, str]:
    return {
        **ORIGIN,
        "X-CSRF-Token": csrf_token,
        "X-Organization-ID": organization_id,
        **extra,
    }


def _read_headers(organization_id: str) -> dict[str, str]:
    return {"X-Organization-ID": organization_id}


def _clause(clause_key: str = "payment", order_no: int = 1) -> dict[str, object]:
    return {
        "clause_key": clause_key,
        "name": "付款",
        "standard_text": "付款应在验收后 30 日内完成。",
        "allowed_deviation": "期限可协商但必须明确。",
        "severity": "medium",
        "applicability": {"contract_type": "purchase"},
        "suggestion": "请补充付款期限。",
        "enabled": True,
        "order_no": order_no,
    }


def _tenant_context(
    session_factory: sessionmaker[Session], *, organization: Organization, user: User
) -> TenantContext:
    with session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
        )
    assert membership is not None
    return TenantContext(
        organization_id=organization.id,
        user_id=user.id,
        membership_id=membership.id,
    )


def test_clause_template_workflow_permissions_and_p05(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "条款测试组织")
    admin = _seed_user(
        session_factory,
        email="clause-admin@example.com",
        organization=organization,
        role="org_admin",
    )
    reviewer = _seed_user(
        session_factory,
        email="clause-reviewer@example.com",
        organization=organization,
        role="reviewer",
    )
    viewer = _seed_user(
        session_factory,
        email="clause-viewer@example.com",
        organization=organization,
        role="viewer",
    )
    organization_id = str(organization.id)
    csrf = _login(auth_client, admin.email)

    created = auth_client.post(
        "/api/v1/clause-templates",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "clause-template-1"}),
        json={"name": "采购付款基线", "contract_type": "purchase", "business_scenario": "  "},
    )
    replayed = auth_client.post(
        "/api/v1/clause-templates",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "clause-template-1"}),
        json={"name": "采购付款基线", "contract_type": "purchase", "business_scenario": "  "},
    )
    assert created.status_code == replayed.status_code == 201
    assert created.json()["id"] == replayed.json()["id"]
    assert created.json()["business_scenario"] == "standard"
    assert created.json()["is_default"] is False
    template_id = created.json()["id"]

    draft_body = {"change_note": "初始化采购条款", "clauses": [_clause()]}
    draft = auth_client.post(
        f"/api/v1/clause-templates/{template_id}/versions",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "clause-version-1"}),
        json=draft_body,
    )
    draft_replay = auth_client.post(
        f"/api/v1/clause-templates/{template_id}/versions",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "clause-version-1"}),
        json=draft_body,
    )
    assert draft.status_code == draft_replay.status_code == 201
    assert draft.json()["id"] == draft_replay.json()["id"]
    version_id = draft.json()["id"]

    detail_without_clauses = auth_client.get(
        f"/api/v1/clause-templates/{template_id}", headers=_read_headers(organization_id)
    )
    detail_with_clauses = auth_client.get(
        f"/api/v1/clause-templates/{template_id}?include_clauses=true",
        headers=_read_headers(organization_id),
    )
    assert detail_without_clauses.status_code == detail_with_clauses.status_code == 200
    assert "clauses" not in detail_without_clauses.json()["versions"][0]
    assert detail_with_clauses.json()["versions"][0]["clauses"][0]["clause_key"] == "payment"

    published = auth_client.post(
        f"/api/v1/clause-template-versions/{version_id}/publish",
        headers=_write_headers(csrf, organization_id),
        json={},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["is_default"] is True
    assert published.json()["current_published_version_id"] == version_id

    immutable = auth_client.patch(
        f"/api/v1/clause-template-versions/{version_id}",
        headers=_write_headers(csrf, organization_id),
        json={"change_note": "不应修改", "version": 1},
    )
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "VERSION_ALREADY_PUBLISHED"

    second_template = auth_client.post(
        "/api/v1/clause-templates",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "clause-template-2"}),
        json={"name": "采购付款备选基线", "contract_type": "purchase"},
    )
    assert second_template.status_code == 201
    second_id = second_template.json()["id"]
    second_draft = auth_client.post(
        f"/api/v1/clause-templates/{second_id}/versions",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "clause-version-2"}),
        json={"change_note": "备选版本", "clauses": [_clause("payment_alt")]},
    )
    assert second_draft.status_code == 201
    second_published = auth_client.post(
        f"/api/v1/clause-template-versions/{second_draft.json()['id']}/publish",
        headers=_write_headers(csrf, organization_id),
        json={},
    )
    assert second_published.status_code == 200
    assert second_published.json()["is_default"] is False
    reviewer_draft_created = auth_client.post(
        f"/api/v1/clause-templates/{second_id}/versions",
        headers=_write_headers(
            csrf, organization_id, **{"Idempotency-Key": "reviewer-visible-draft"}
        ),
        json={"change_note": "审核员不可见草稿", "clauses": [_clause("draft_only")]},
    )
    assert reviewer_draft_created.status_code == 201

    switched = auth_client.patch(
        f"/api/v1/clause-templates/{second_id}",
        headers=_write_headers(csrf, organization_id),
        json={"is_default": True, "version": second_template.json()["version"] + 1},
    )
    assert switched.status_code == 200
    assert switched.json()["is_default"] is True
    assert (
        auth_client.get(
            f"/api/v1/clause-templates/{template_id}", headers=_read_headers(organization_id)
        ).json()["is_default"]
        is False
    )

    disable_default = auth_client.patch(
        f"/api/v1/clause-templates/{second_id}",
        headers=_write_headers(csrf, organization_id),
        json={"status": "disabled", "version": switched.json()["version"]},
    )
    assert disable_default.status_code == 409
    assert disable_default.json()["error"]["code"] == "DEFAULT_CLAUSE_TEMPLATE_REQUIRED"

    first_detail = auth_client.get(
        f"/api/v1/clause-templates/{template_id}", headers=_read_headers(organization_id)
    )
    disabled = auth_client.patch(
        f"/api/v1/clause-templates/{template_id}",
        headers=_write_headers(csrf, organization_id),
        json={"status": "disabled", "version": first_detail.json()["version"]},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"

    _login(auth_client, reviewer.email)
    reviewer_list = auth_client.get(
        "/api/v1/clause-templates", headers=_read_headers(organization_id)
    )
    assert reviewer_list.status_code == 200
    reviewer_draft = auth_client.get(
        f"/api/v1/clause-template-versions/{reviewer_draft_created.json()['id']}",
        headers=_read_headers(organization_id),
    )
    assert reviewer_draft.status_code == 403
    reviewer_published = auth_client.get(
        f"/api/v1/clause-template-versions/{second_published.json()['id']}",
        headers=_read_headers(organization_id),
    )
    assert reviewer_published.status_code == 200

    _login(auth_client, viewer.email)
    viewer_read = auth_client.get(
        "/api/v1/clause-templates", headers=_read_headers(organization_id)
    )
    assert viewer_read.status_code == 403

    with session_factory() as session:
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "clause_template_version.published")
        ) is not None


def test_clause_template_exact_scenario_and_validation_errors(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "场景规范组织")
    admin = _seed_user(
        session_factory,
        email="scenario-admin@example.com",
        organization=organization,
        role="org_admin",
    )
    organization_id = str(organization.id)
    csrf = _login(auth_client, admin.email)
    template = auth_client.post(
        "/api/v1/clause-templates",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "scenario-template"}),
        json={
            "name": "项目采购基线",
            "contract_type": "purchase",
            "business_scenario": " Project ",
        },
    )
    assert template.status_code == 201
    assert template.json()["business_scenario"] == "project"
    duplicate = auth_client.post(
        "/api/v1/clause-templates",
        headers=_write_headers(
            csrf, organization_id, **{"Idempotency-Key": "scenario-template-dup"}
        ),
        json={"name": "项目采购基线", "contract_type": "purchase", "business_scenario": "project"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "TEMPLATE_NAME_CONFLICT"

    invalid = auth_client.post(
        f"/api/v1/clause-templates/{template.json()['id']}/versions",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "invalid-clauses"}),
        json={
            "change_note": "重复条款键",
            "clauses": [_clause("same", 1), _clause("same", 2)],
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "CLAUSE_SCHEMA_INVALID"

    source_invalid = auth_client.post(
        f"/api/v1/clause-templates/{template.json()['id']}/versions",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "invalid-source"}),
        json={"change_note": "无效来源", "source_version_id": str(uuid4()), "clauses": [_clause()]},
    )
    assert source_invalid.status_code == 409
    assert source_invalid.json()["error"]["code"] == "VERSION_SOURCE_INVALID"

    empty_draft = auth_client.post(
        f"/api/v1/clause-templates/{template.json()['id']}/versions",
        headers=_write_headers(csrf, organization_id, **{"Idempotency-Key": "empty-draft"}),
        json={"change_note": "等待编辑", "clauses": []},
    )
    assert empty_draft.status_code == 201
    empty_publish = auth_client.post(
        f"/api/v1/clause-template-versions/{empty_draft.json()['id']}/publish",
        headers=_write_headers(csrf, organization_id),
        json={},
    )
    assert empty_publish.status_code == 422
    assert empty_publish.json()["error"]["code"] == "CLAUSE_SCHEMA_INVALID"


def test_clause_template_concurrent_first_publications_keep_one_default(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "并发默认组织")
    admin = _seed_user(
        session_factory,
        email="concurrent-clause@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    templates: list[tuple[ClauseTemplate, ClauseTemplateVersion]] = []
    for index in range(2):
        template = ClauseTemplate(
            id=uuid4(),
            organization_id=organization.id,
            name=f"并发模板 {index}",
            normalized_name=f"并发模板 {index}",
            contract_type="purchase",
            business_scenario="standard",
        )
        version = ClauseTemplateVersion(
            id=uuid4(),
            organization_id=organization.id,
            template_id=template.id,
            version_no=1,
            change_note="并发发布草稿",
        )
        clause = StandardClause(
            id=uuid4(),
            organization_id=organization.id,
            template_version_id=version.id,
            clause_key=f"payment_{index}",
            name="付款",
            standard_text="付款期限应明确。",
            allowed_deviation="可协商但不得留空。",
            severity="medium",
            applicability_json={},
            suggestion="请复核付款条款。",
            enabled=True,
            order_no=1,
        )
        with session_factory() as session, UnitOfWork(session) as unit_of_work:
            session.add_all([template, version, clause])
            unit_of_work.commit()
        templates.append((template, version))

    barrier = Barrier(2)

    def publish(version_id: UUID, request_id: str) -> None:
        with session_factory() as session:
            barrier.wait(timeout=5)
            publish_version(session, actor=actor, version_id=version_id, request_id=request_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(publish, version.id, f"concurrent-clause-publish-{index}")
            for index, (_, version) in enumerate(templates)
        ]
        for future in futures:
            future.result(timeout=10)

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ClauseTemplate).where(
                    ClauseTemplate.organization_id == organization.id,
                    ClauseTemplate.contract_type == "purchase",
                    ClauseTemplate.business_scenario == "standard",
                )
            )
        )
        assert sum(template.is_default for template in rows) == 1
        assert all(template.current_published_version_id is not None for template in rows)


def test_clause_template_database_immutability_and_tenant_foreign_keys(
    session_factory: sessionmaker[Session],
) -> None:
    first = _seed_organization(session_factory, "条款约束组织一")
    second = _seed_organization(session_factory, "条款约束组织二")
    template = ClauseTemplate(
        id=uuid4(),
        organization_id=first.id,
        name="约束模板",
        normalized_name="约束模板",
        contract_type="purchase",
        business_scenario="standard",
    )
    version = ClauseTemplateVersion(
        id=uuid4(),
        organization_id=first.id,
        template_id=template.id,
        version_no=1,
        change_note="已发布",
    )
    clause = StandardClause(
        id=uuid4(),
        organization_id=first.id,
        template_version_id=version.id,
        clause_key="payment",
        name="付款",
        standard_text="付款期限应明确。",
        allowed_deviation="可协商。",
        severity="medium",
        applicability_json={},
        suggestion="请复核。",
        enabled=True,
        order_no=1,
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add_all([template, version, clause])
        unit_of_work.commit()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        saved_version = session.get(ClauseTemplateVersion, version.id)
        assert saved_version is not None
        saved_version.status = "published"
        unit_of_work.commit()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        saved_template = session.get(ClauseTemplate, template.id)
        assert saved_template is not None
        saved_template.current_published_version_id = version.id
        saved_template.is_default = True
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        saved_clause = session.get(StandardClause, clause.id)
        assert saved_clause is not None
        saved_clause.standard_text = "不应修改已发布正文。"
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        saved_template = session.get(ClauseTemplate, template.id)
        assert saved_template is not None
        saved_template.current_published_version_id = uuid4()
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            ClauseTemplateVersion(
                id=uuid4(),
                organization_id=second.id,
                template_id=template.id,
                version_no=2,
                change_note="跨组织版本",
            )
        )
        unit_of_work.commit()


def test_clause_template_openapi_projects_phase8b_contract(
    auth_client: TestClient,
) -> None:
    paths = auth_client.app.openapi()["paths"]
    expected_methods = {
        "/api/v1/clause-templates": {"get", "post"},
        "/api/v1/clause-templates/{template_id}": {"get", "patch"},
        "/api/v1/clause-templates/{template_id}/versions": {"post"},
        "/api/v1/clause-template-versions/{version_id}": {"get", "patch"},
        "/api/v1/clause-template-versions/{version_id}/publish": {"post"},
    }
    for path, methods in expected_methods.items():
        assert path in paths
        assert methods <= set(paths[path])

    expected_responses = {
        ("/api/v1/clause-templates", "get"): ("200", "ClauseTemplateCursorPageResponse"),
        ("/api/v1/clause-templates", "post"): ("201", "ClauseTemplateResponse"),
        ("/api/v1/clause-templates/{template_id}", "get"): (
            "200",
            "ClauseTemplateDetailResponse",
        ),
        ("/api/v1/clause-templates/{template_id}", "patch"): (
            "200",
            "ClauseTemplateResponse",
        ),
        ("/api/v1/clause-templates/{template_id}/versions", "post"): (
            "201",
            "ClauseTemplateVersionResponse",
        ),
        ("/api/v1/clause-template-versions/{version_id}", "get"): (
            "200",
            "ClauseTemplateVersionResponse",
        ),
        ("/api/v1/clause-template-versions/{version_id}", "patch"): (
            "200",
            "ClauseTemplateVersionResponse",
        ),
        ("/api/v1/clause-template-versions/{version_id}/publish", "post"): (
            "200",
            "ClauseTemplateVersionResponse",
        ),
    }
    for (path, method), (status_code, schema_name) in expected_responses.items():
        schema = paths[path][method]["responses"][status_code]["content"]["application/json"][
            "schema"
        ]
        schema_ref = schema["$ref"].rsplit("/", 1)[-1]
        assert schema_ref == schema_name or schema_ref.endswith(f"_{schema_name}")

    write_operations = {
        ("/api/v1/clause-templates", "post"): "CreateClauseTemplateRequest",
        ("/api/v1/clause-templates/{template_id}", "patch"): "UpdateClauseTemplateRequest",
        ("/api/v1/clause-templates/{template_id}/versions", "post"):
        "CreateClauseTemplateVersionRequest",
        ("/api/v1/clause-template-versions/{version_id}", "patch"):
        "UpdateClauseTemplateVersionRequest",
        ("/api/v1/clause-template-versions/{version_id}/publish", "post"):
        "PublishClauseTemplateVersionRequest",
    }
    for (path, method), schema_name in write_operations.items():
        operation = paths[path][method]
        assert operation["requestBody"]["required"] is True
        schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        schema_ref = schema_ref.rsplit("/", 1)[-1]
        assert schema_ref == schema_name or schema_ref.endswith(f"_{schema_name}")

    assert paths["/api/v1/clause-templates"]["post"]["parameters"]
    assert paths["/api/v1/clause-templates/{template_id}/versions"]["post"]["parameters"]
    assert {
        "200",
        "401",
        "403",
        "404",
        "409",
        "422",
    } <= set(paths["/api/v1/clause-template-versions/{version_id}/publish"]["post"]["responses"])
