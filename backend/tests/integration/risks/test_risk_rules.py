from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.identity.models import (
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.modules.risks.rules.models import RiskRule, RiskRuleBundle, RiskRuleBundleVersion
from backend.app.modules.risks.rules.schemas import UpdateRiskRuleBundleRequest
from backend.app.modules.risks.rules.service import (
    install_risk_rule_baseline,
    publish_version,
    update_bundle,
)
from backend.app.shared.audit import AuditLog
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
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


def _rule(rule_key: str = "payment_cap") -> dict[str, object]:
    return {
        "rule_key": rule_key,
        "risk_type": "payment_terms",
        "engine": "deterministic",
        "condition": {
            "operator": "amount_threshold",
            "field": "contract_amount",
            "comparison": "gt",
            "value": "30",
        },
        "severity": "high",
        "suggestion": "请复核付款比例。",
        "enabled": True,
    }


def _seed_draft_bundle(
    session_factory: sessionmaker[Session],
    *,
    organization: Organization,
    name: str,
    rule_key: str,
) -> tuple[RiskRuleBundle, RiskRuleBundleVersion]:
    bundle = RiskRuleBundle(
        id=uuid4(),
        organization_id=organization.id,
        name=name,
        normalized_name=name.lower(),
    )
    version = RiskRuleBundleVersion(
        id=uuid4(),
        organization_id=organization.id,
        bundle_id=bundle.id,
        version_no=1,
        status="draft",
        change_note=f"{name} 初始草稿",
    )
    rule = RiskRule(
        id=uuid4(),
        organization_id=organization.id,
        bundle_version_id=version.id,
        rule_key=rule_key,
        risk_type="payment_terms",
        engine="deterministic",
        condition_json={"operator": "field_missing", "field": "payment_terms"},
        severity="medium",
        suggestion="请复核付款条件。",
        enabled=True,
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(bundle)
        session.flush()
        session.add(version)
        session.flush()
        session.add(rule)
        unit_of_work.commit()
    return bundle, version


def _tenant_context(
    session_factory: sessionmaker[Session],
    *,
    organization: Organization,
    user: User,
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


def test_risk_rule_full_workflow_and_permissions(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "规则测试组织")
    admin = _seed_user(
        session_factory,
        email="risk-admin@example.com",
        organization=organization,
        role="org_admin",
    )
    reviewer = _seed_user(
        session_factory,
        email="risk-reviewer@example.com",
        organization=organization,
        role="reviewer",
    )
    viewer = _seed_user(
        session_factory,
        email="risk-viewer@example.com",
        organization=organization,
        role="viewer",
    )
    organization_id = str(organization.id)
    csrf = _login(auth_client, admin.email)
    write_headers = _write_headers(
        csrf,
        organization_id,
        **{"Idempotency-Key": "risk-bundle-1"},
    )

    created = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers={
            **ORIGIN,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "risk-bundle-1",
        },
        json={"name": "付款风险规则"},
    )
    replayed = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=write_headers,
        json={"name": "付款风险规则"},
    )
    assert created.status_code == replayed.status_code == 201
    assert created.json()["id"] == replayed.json()["id"]
    bundle_id = created.json()["id"]
    assert created.json()["is_default"] is False

    draft_body = {
        "change_note": "初始化付款规则",
        "rules": [
            _rule(),
            {
                "rule_key": "semantic_payment",
                "risk_type": "payment_terms",
                "engine": "model",
                "condition": {"operator": "semantic"},
                "severity": "medium",
                "suggestion": "请结合合同上下文复核付款条件。",
                "enabled": True,
            },
        ],
    }
    draft = auth_client.post(
        f"/api/v1/risk-rule-bundles/{bundle_id}/versions",
        headers=_write_headers(
            csrf,
            organization_id,
            **{"Idempotency-Key": "risk-version-1"},
        ),
        json=draft_body,
    )
    draft_replay = auth_client.post(
        f"/api/v1/risk-rule-bundles/{bundle_id}/versions",
        headers=_write_headers(
            csrf,
            organization_id,
            **{"Idempotency-Key": "risk-version-1"},
        ),
        json=draft_body,
    )
    assert draft.status_code == draft_replay.status_code == 201
    assert draft.json()["id"] == draft_replay.json()["id"]
    version_id = draft.json()["id"]
    assert draft.json()["status"] == "draft"
    assert len(draft.json()["rules"]) == 2

    detail_without_rules = auth_client.get(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers=_read_headers(organization_id),
    )
    detail_with_rules = auth_client.get(
        f"/api/v1/risk-rule-bundles/{bundle_id}?include_rules=true",
        headers=_read_headers(organization_id),
    )
    assert detail_without_rules.status_code == detail_with_rules.status_code == 200
    assert "rules" not in detail_without_rules.json()["versions"][0]
    assert len(detail_with_rules.json()["versions"][0]["rules"]) == 2

    published = auth_client.post(
        f"/api/v1/risk-rule-bundle-versions/{version_id}/publish",
        headers=_write_headers(csrf, organization_id),
        json={},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["is_default"] is True
    assert published.json()["current_published_version_id"] == version_id

    immutable = auth_client.patch(
        f"/api/v1/risk-rule-bundle-versions/{version_id}",
        headers=_write_headers(csrf, organization_id),
        json={"change_note": "不应修改", "version": 1},
    )
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "VERSION_ALREADY_PUBLISHED"

    editable_draft = auth_client.post(
        f"/api/v1/risk-rule-bundles/{bundle_id}/versions",
        headers=_write_headers(
            csrf,
            organization_id,
            **{"Idempotency-Key": "risk-version-editable"},
        ),
        json={"change_note": "待编辑草稿", "rules": [_rule("draft_rule")]},
    )
    assert editable_draft.status_code == 201
    editable_version_id = editable_draft.json()["id"]
    saved_draft = auth_client.patch(
        f"/api/v1/risk-rule-bundle-versions/{editable_version_id}",
        headers=_write_headers(csrf, organization_id),
        json={"change_note": "已编辑草稿", "rules": [_rule("draft_rule_v2")], "version": 1},
    )
    assert saved_draft.status_code == 200
    stale_draft = auth_client.patch(
        f"/api/v1/risk-rule-bundle-versions/{editable_version_id}",
        headers=_write_headers(csrf, organization_id),
        json={"change_note": "覆盖他人修改", "version": 1},
    )
    assert stale_draft.status_code == 409
    assert stale_draft.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    second_bundle = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            csrf,
            organization_id,
            **{"Idempotency-Key": "risk-bundle-2"},
        ),
        json={"name": "销售风险规则"},
    )
    assert second_bundle.status_code == 201
    second_bundle_id = second_bundle.json()["id"]
    second_version = auth_client.post(
        f"/api/v1/risk-rule-bundles/{second_bundle_id}/versions",
        headers=_write_headers(
            csrf,
            organization_id,
            **{"Idempotency-Key": "risk-version-2"},
        ),
        json={"change_note": "销售初始化", "rules": [_rule("sales_cap")]},
    )
    assert second_version.status_code == 201
    second_published = auth_client.post(
        f"/api/v1/risk-rule-bundle-versions/{second_version.json()['id']}/publish",
        headers=_write_headers(csrf, organization_id),
        json={},
    )
    assert second_published.status_code == 200
    assert second_published.json()["is_default"] is False
    second_detail = auth_client.get(
        f"/api/v1/risk-rule-bundles/{second_bundle_id}",
        headers=_read_headers(organization_id),
    )
    assert second_detail.status_code == 200

    switched = auth_client.patch(
        f"/api/v1/risk-rule-bundles/{second_bundle_id}",
        headers=_write_headers(csrf, organization_id),
        json={"is_default": True, "version": second_detail.json()["version"]},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["is_default"] is True
    assert (
        auth_client.get(
            f"/api/v1/risk-rule-bundles/{bundle_id}",
            headers=_read_headers(organization_id),
        ).json()["is_default"]
        is False
    )

    disable_default = auth_client.patch(
        f"/api/v1/risk-rule-bundles/{second_bundle_id}",
        headers=_write_headers(csrf, organization_id),
        json={"status": "disabled", "version": switched.json()["version"]},
    )
    assert disable_default.status_code == 409
    assert disable_default.json()["error"]["code"] == "DEFAULT_RULE_BUNDLE_REQUIRED"

    first_detail = auth_client.get(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers=_read_headers(organization_id),
    )
    disable_non_default = auth_client.patch(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers=_write_headers(csrf, organization_id),
        json={"status": "disabled", "version": first_detail.json()["version"]},
    )
    assert disable_non_default.status_code == 200
    assert disable_non_default.json()["status"] == "disabled"
    enable_non_default = auth_client.patch(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers=_write_headers(csrf, organization_id),
        json={"status": "active", "version": disable_non_default.json()["version"]},
    )
    assert enable_non_default.status_code == 200
    assert enable_non_default.json()["status"] == "active"

    bad_code = auth_client.post(
        f"/api/v1/risk-rule-bundles/{bundle_id}/versions",
        headers=_write_headers(
            csrf,
            organization_id,
            **{"Idempotency-Key": "risk-version-bad"},
        ),
        json={
            "change_note": "非法条件",
            "rules": [
                {
                    **_rule("unsafe"),
                    "condition": {
                        "operator": "python",
                        "source": "__import__('os').system('id')",
                    },
                }
            ],
        },
    )
    assert bad_code.status_code == 422
    assert bad_code.json()["error"]["code"] == "VALIDATION_ERROR"

    _login(auth_client, reviewer.email)
    reviewer_list = auth_client.get(
        "/api/v1/risk-rule-bundles",
        headers=_read_headers(organization_id),
    )
    assert reviewer_list.status_code == 200
    assert len(reviewer_list.json()["items"]) == 2
    reviewer_draft = auth_client.get(
        f"/api/v1/risk-rule-bundle-versions/{editable_version_id}",
        headers=_read_headers(organization_id),
    )
    assert reviewer_draft.status_code == 403
    assert reviewer_draft.json()["error"]["code"] == "FORBIDDEN"
    reviewer_published = auth_client.get(
        f"/api/v1/risk-rule-bundle-versions/{version_id}",
        headers=_read_headers(organization_id),
    )
    assert reviewer_published.status_code == 200

    _login(auth_client, viewer.email)
    viewer_read = auth_client.get(
        "/api/v1/risk-rule-bundles",
        headers=_read_headers(organization_id),
    )
    assert viewer_read.status_code == 403

    with session_factory() as session:
        assert (
            session.scalar(select(AuditLog).where(AuditLog.action == "risk_rule_version.published"))
            is not None
        )


def test_risk_rule_draft_is_hidden_from_reviewer_and_cross_tenant_isolated(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    first = _seed_organization(session_factory, "规则组织一")
    second = _seed_organization(session_factory, "规则组织二")
    first_admin = _seed_user(
        session_factory,
        email="first-admin@example.com",
        organization=first,
        role="org_admin",
    )
    second_admin = _seed_user(
        session_factory,
        email="second-admin@example.com",
        organization=second,
        role="org_admin",
    )
    first_reviewer = _seed_user(
        session_factory,
        email="first-reviewer@example.com",
        organization=first,
        role="reviewer",
    )
    first_id = str(first.id)
    second_id = str(second.id)
    csrf = _login(auth_client, second_admin.email)
    second_bundle = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            csrf,
            second_id,
            **{"Idempotency-Key": "cross-tenant-bundle"},
        ),
        json={"name": "组织二规则"},
    )
    assert second_bundle.status_code == 201

    csrf = _login(auth_client, first_admin.email)
    hidden = auth_client.get(
        f"/api/v1/risk-rule-bundles/{second_bundle.json()['id']}",
        headers=_read_headers(first_id),
    )
    wrong_context = auth_client.get(
        "/api/v1/risk-rule-bundles",
        headers=_read_headers(second_id),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "RULE_BUNDLE_NOT_FOUND"
    assert wrong_context.status_code == 404
    assert wrong_context.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"

    reviewer_csrf = _login(auth_client, first_reviewer.email)
    forbidden_write = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            reviewer_csrf,
            first_id,
            **{"Idempotency-Key": "reviewer-write"},
        ),
        json={"name": "不应创建"},
    )
    assert forbidden_write.status_code == 403
    assert forbidden_write.json()["error"]["code"] == "ORG_ADMIN_REQUIRED"


def test_risk_rule_resource_paths_derive_tenant_from_resource(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    first = _seed_organization(session_factory, "路径组织一")
    second = _seed_organization(session_factory, "路径组织二")
    multi_org_admin = _seed_user(
        session_factory,
        email="resource-path-admin@example.com",
        organization=first,
        role="org_admin",
    )
    second_admin = _seed_user(
        session_factory,
        email="resource-path-owner@example.com",
        organization=second,
        role="org_admin",
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=second.id,
                user_id=multi_org_admin.id,
                email=multi_org_admin.email,
                normalized_email=multi_org_admin.normalized_email,
                display_name=multi_org_admin.display_name,
                role="org_admin",
                status="active",
            )
        )
        unit_of_work.commit()

    second_id = str(second.id)
    second_csrf = _login(auth_client, second_admin.email)
    created = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            second_csrf,
            second_id,
            **{"Idempotency-Key": "resource-path-bundle"},
        ),
        json={"name": "路径资源规则集"},
    )
    assert created.status_code == 201
    bundle_id = created.json()["id"]
    draft = auth_client.post(
        f"/api/v1/risk-rule-bundles/{bundle_id}/versions",
        headers=_write_headers(
            second_csrf,
            second_id,
            **{"Idempotency-Key": "resource-path-version"},
        ),
        json={"change_note": "路径资源草稿", "rules": [_rule()]},
    )
    assert draft.status_code == 201
    version_id = draft.json()["id"]

    first_id = str(first.id)
    multi_csrf = _login(auth_client, multi_org_admin.email)
    without_header = auth_client.get(f"/api/v1/risk-rule-bundles/{bundle_id}")
    wrong_header = auth_client.get(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers=_read_headers(first_id),
    )
    invalid_header = auth_client.get(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers={"X-Organization-ID": "not-a-uuid"},
    )
    assert (
        without_header.status_code
        == wrong_header.status_code
        == invalid_header.status_code
        == 200
    )
    assert without_header.json()["id"] == wrong_header.json()["id"] == bundle_id

    renamed = auth_client.patch(
        f"/api/v1/risk-rule-bundles/{bundle_id}",
        headers=_write_headers(multi_csrf, first_id),
        json={"name": "路径资源规则集（已核对）", "version": 1},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "路径资源规则集（已核对）"

    version_without_header = auth_client.get(
        f"/api/v1/risk-rule-bundle-versions/{version_id}"
    )
    version_wrong_header = auth_client.get(
        f"/api/v1/risk-rule-bundle-versions/{version_id}",
        headers=_read_headers(first_id),
    )
    assert version_without_header.status_code == version_wrong_header.status_code == 200
    assert version_without_header.json()["id"] == version_id


def test_invalid_source_versions_map_to_version_source_invalid(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    first = _seed_organization(session_factory, "来源规则组织一")
    second = _seed_organization(session_factory, "来源规则组织二")
    first_admin = _seed_user(
        session_factory,
        email="source-first-admin@example.com",
        organization=first,
        role="org_admin",
    )
    second_admin = _seed_user(
        session_factory,
        email="source-second-admin@example.com",
        organization=second,
        role="org_admin",
    )

    first_id = str(first.id)
    first_csrf = _login(auth_client, first_admin.email)
    source_bundle = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            first_csrf,
            first_id,
            **{"Idempotency-Key": "source-first-bundle"},
        ),
        json={"name": "来源规则集"},
    )
    assert source_bundle.status_code == 201
    source_bundle_id = source_bundle.json()["id"]
    source_draft = auth_client.post(
        f"/api/v1/risk-rule-bundles/{source_bundle_id}/versions",
        headers=_write_headers(
            first_csrf,
            first_id,
            **{"Idempotency-Key": "source-first-draft"},
        ),
        json={"change_note": "来源草稿", "rules": [_rule("source_draft_rule")]},
    )
    assert source_draft.status_code == 201
    source_draft_id = source_draft.json()["id"]
    source_published = auth_client.post(
        f"/api/v1/risk-rule-bundle-versions/{source_draft_id}/publish",
        headers=_write_headers(first_csrf, first_id),
        json={},
    )
    assert source_published.status_code == 200
    source_published_id = source_published.json()["id"]
    source_unpublished_draft = auth_client.post(
        f"/api/v1/risk-rule-bundles/{source_bundle_id}/versions",
        headers=_write_headers(
            first_csrf,
            first_id,
            **{"Idempotency-Key": "source-unpublished-draft"},
        ),
        json={"change_note": "未发布来源草稿", "rules": [_rule("source_unpublished_rule")]},
    )
    assert source_unpublished_draft.status_code == 201
    source_unpublished_draft_id = source_unpublished_draft.json()["id"]

    target_bundle = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            first_csrf,
            first_id,
            **{"Idempotency-Key": "source-target-bundle"},
        ),
        json={"name": "目标规则集"},
    )
    assert target_bundle.status_code == 201
    target_bundle_id = target_bundle.json()["id"]

    def assert_invalid_source(
        *, source_version_id: str, idempotency_key: str, bundle_id: str = target_bundle_id
    ) -> None:
        invalid = auth_client.post(
            f"/api/v1/risk-rule-bundles/{bundle_id}/versions",
            headers=_write_headers(
                first_csrf,
                first_id,
                **{"Idempotency-Key": idempotency_key},
            ),
            json={
                "change_note": "无效来源测试",
                "source_version_id": source_version_id,
                "rules": [_rule(idempotency_key)],
            },
        )
        assert invalid.status_code == 409
        assert invalid.json()["error"]["code"] == "VERSION_SOURCE_INVALID"

    assert_invalid_source(source_version_id=str(uuid4()), idempotency_key="source-missing")
    assert_invalid_source(
        source_version_id=source_unpublished_draft_id,
        idempotency_key="source-draft",
        bundle_id=source_bundle_id,
    )
    assert_invalid_source(
        source_version_id=source_published_id,
        idempotency_key="source-cross-bundle",
    )

    second_id = str(second.id)
    second_csrf = _login(auth_client, second_admin.email)
    second_bundle = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            second_csrf,
            second_id,
            **{"Idempotency-Key": "source-second-bundle"},
        ),
        json={"name": "其他组织来源规则集"},
    )
    assert second_bundle.status_code == 201
    second_version = auth_client.post(
        f"/api/v1/risk-rule-bundles/{second_bundle.json()['id']}/versions",
        headers=_write_headers(
            second_csrf,
            second_id,
            **{"Idempotency-Key": "source-second-draft"},
        ),
        json={"change_note": "其他组织来源草稿", "rules": [_rule("source_other_org")]},
    )
    assert second_version.status_code == 201
    second_published = auth_client.post(
        f"/api/v1/risk-rule-bundle-versions/{second_version.json()['id']}/publish",
        headers=_write_headers(second_csrf, second_id),
        json={},
    )
    assert second_published.status_code == 200

    first_csrf = _login(auth_client, first_admin.email)
    assert_invalid_source(
        source_version_id=second_published.json()["id"],
        idempotency_key="source-cross-organization",
    )


def test_publish_default_constraint_conflict_is_a_contract_error(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.modules.risks.rules import service as risk_rule_service

    organization = _seed_organization(session_factory, "默认冲突映射组织")
    admin = _seed_user(
        session_factory,
        email="default-conflict@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    _, version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="默认冲突规则集",
        rule_key="default_conflict_rule",
    )

    def fail_flush(*_args: object, **_kwargs: object) -> None:
        raise IntegrityError(
            "duplicate default",
            {},
            SimpleNamespace(
                diag=SimpleNamespace(constraint_name="uq_risk_rule_bundles_default")
            ),
        )

    with session_factory() as session:
        session.autoflush = False
        monkeypatch.setattr(session, "flush", fail_flush)
        with pytest.raises(ApplicationError) as error:
            risk_rule_service.publish_version(
                session,
                actor=actor,
                version_id=version.id,
                request_id="req_default_conflict_mapping",
            )
    assert error.value.status_code == 409
    assert error.value.code == "DEFAULT_RULE_BUNDLE_CONFLICT"


def test_risk_rule_bundle_blank_search_is_treated_as_unfiltered(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "空白搜索组织")
    admin = _seed_user(
        session_factory,
        email="blank-search@example.com",
        organization=organization,
        role="org_admin",
    )
    csrf = _login(auth_client, admin.email)
    response = auth_client.post(
        "/api/v1/risk-rule-bundles",
        headers=_write_headers(
            csrf,
            str(organization.id),
            **{"Idempotency-Key": "blank-search-bundle"},
        ),
        json={"name": "应被空白搜索返回"},
    )
    assert response.status_code == 201

    listed = auth_client.get(
        "/api/v1/risk-rule-bundles?q=%20%20%20",
        headers=_read_headers(str(organization.id)),
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1


def test_risk_rule_database_enforces_default_uniqueness_and_current_version_ownership(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "规则约束组织")
    admin = _seed_user(
        session_factory,
        email="constraint-admin@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    first_bundle, first_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="规则集一",
        rule_key="first_rule",
    )
    second_bundle, second_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="规则集二",
        rule_key="second_rule",
    )

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        locked = session.get(RiskRuleBundle, first_bundle.id)
        assert locked is not None
        locked.current_published_version_id = second_version.id
        unit_of_work.commit()

    for index, version in enumerate((first_version, second_version)):
        with session_factory() as session:
            publish_version(
                session,
                actor=actor,
                version_id=version.id,
                request_id=f"req_constraint_publish_{index}",
            )

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        second = session.get(RiskRuleBundle, second_bundle.id)
        assert second is not None
        second.is_default = True
        unit_of_work.commit()

    draft_version_id = uuid4()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(
            RiskRuleBundleVersion(
                id=draft_version_id,
                organization_id=organization.id,
                bundle_id=first_bundle.id,
                version_no=2,
                status="draft",
                change_note="约束测试草稿",
            )
        )
        unit_of_work.commit()

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        first = session.get(RiskRuleBundle, first_bundle.id)
        assert first is not None
        first.current_published_version_id = draft_version_id
        unit_of_work.commit()

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        first = session.get(RiskRuleBundle, first_bundle.id)
        assert first is not None
        first.status = "disabled"
        unit_of_work.commit()


def test_risk_rule_database_enforces_compound_tenant_foreign_keys(
    session_factory: sessionmaker[Session],
) -> None:
    first = _seed_organization(session_factory, "复合约束组织一")
    second = _seed_organization(session_factory, "复合约束组织二")
    second_user = _seed_user(
        session_factory,
        email="compound-tenant@example.com",
        organization=second,
        role="org_admin",
    )
    first_bundle, _ = _seed_draft_bundle(
        session_factory,
        organization=first,
        name="组织一规则",
        rule_key="tenant_one_rule",
    )
    second_bundle, second_version = _seed_draft_bundle(
        session_factory,
        organization=second,
        name="组织二规则",
        rule_key="tenant_two_rule",
    )

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            RiskRuleBundleVersion(
                id=uuid4(),
                organization_id=first.id,
                bundle_id=second_bundle.id,
                version_no=2,
                status="draft",
                change_note="跨组织版本",
            )
        )
        unit_of_work.commit()

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            RiskRule(
                id=uuid4(),
                organization_id=first.id,
                bundle_version_id=second_version.id,
                rule_key="cross_tenant_rule",
                risk_type="payment_terms",
                engine="deterministic",
                condition_json={"operator": "field_missing", "field": "payment_terms"},
                severity="medium",
                suggestion="不应写入。",
                enabled=True,
            )
        )
        unit_of_work.commit()

    with (
        pytest.raises(IntegrityError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            RiskRuleBundleVersion(
                id=uuid4(),
                organization_id=first.id,
                bundle_id=first_bundle.id,
                version_no=2,
                status="draft",
                change_note="跨组织发布人",
                published_by=second_user.id,
            )
        )
        unit_of_work.commit()


def test_concurrent_first_publications_leave_exactly_one_default_bundle(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "并发发布组织")
    admin = _seed_user(
        session_factory,
        email="concurrent-publish@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    bundles_and_versions = [
        _seed_draft_bundle(
            session_factory,
            organization=organization,
            name=f"并发规则集 {index}",
            rule_key=f"concurrent_rule_{index}",
        )
        for index in range(2)
    ]
    barrier = Barrier(2)

    def publish(version_id: UUID, request_id: str) -> None:
        with session_factory() as session:
            barrier.wait(timeout=5)
            publish_version(
                session,
                actor=actor,
                version_id=version_id,
                request_id=request_id,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(publish, version.id, f"req_publish_{index}")
            for index, (_, version) in enumerate(bundles_and_versions)
        ]
        for future in futures:
            future.result(timeout=10)

    with session_factory() as session:
        bundles = list(
            session.scalars(
                select(RiskRuleBundle).where(
                    RiskRuleBundle.organization_id == organization.id
                )
            )
        )
        versions = list(
            session.scalars(
                select(RiskRuleBundleVersion).where(
                    RiskRuleBundleVersion.organization_id == organization.id
                )
            )
        )
        assert sum(bundle.is_default for bundle in bundles) == 1
        assert all(bundle.current_published_version_id is not None for bundle in bundles)
        assert all(bundle.version == 2 for bundle in bundles)
        assert all(version.status == "published" and version.version == 2 for version in versions)
        assert (
            session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.organization_id == organization.id,
                    AuditLog.action == "risk_rule_version.published",
                )
            )
            == 2
        )


def test_concurrent_default_switches_are_serialized_and_versioned(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "并发切换组织")
    admin = _seed_user(
        session_factory,
        email="concurrent-switch@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    bundles_and_versions = [
        _seed_draft_bundle(
            session_factory,
            organization=organization,
            name=f"切换规则集 {index}",
            rule_key=f"switch_rule_{index}",
        )
        for index in range(3)
    ]
    for index, (_, version) in enumerate(bundles_and_versions):
        with session_factory() as session:
            publish_version(
                session,
                actor=actor,
                version_id=version.id,
                request_id=f"req_seed_publish_{index}",
            )

    targets = [bundle for bundle, _ in bundles_and_versions[1:]]
    barrier = Barrier(2)

    def switch(bundle_id: UUID, request_id: str) -> None:
        with session_factory() as session:
            barrier.wait(timeout=5)
            update_bundle(
                session,
                actor=actor,
                bundle_id=bundle_id,
                body=UpdateRiskRuleBundleRequest(is_default=True, version=2),
                request_id=request_id,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(switch, bundle.id, f"req_switch_{index}")
            for index, bundle in enumerate(targets)
        ]
        for future in futures:
            future.result(timeout=10)

    with session_factory() as session:
        bundles = list(
            session.scalars(
                select(RiskRuleBundle).where(
                    RiskRuleBundle.organization_id == organization.id
                )
            )
        )
        assert sum(bundle.is_default for bundle in bundles) == 1
        assert all(bundle.version >= 3 for bundle in bundles)
        assert (
            session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.organization_id == organization.id,
                    AuditLog.action == "risk_rule_bundle.updated",
                )
            )
            == 2
        )


def test_default_switch_audit_is_atomic_and_records_both_bundles(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.modules.risks.rules import service as risk_rule_service

    organization = _seed_organization(session_factory, "默认切换审计组织")
    admin = _seed_user(
        session_factory,
        email="switch-audit@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    first_bundle, first_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="原默认规则集",
        rule_key="original_default",
    )
    second_bundle, second_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="目标默认规则集",
        rule_key="target_default",
    )
    for index, version in enumerate((first_version, second_version)):
        with session_factory() as session:
            publish_version(
                session,
                actor=actor,
                version_id=version.id,
                request_id=f"req_switch_audit_publish_{index}",
            )

    with session_factory() as session:
        update_bundle(
            session,
            actor=actor,
            bundle_id=second_bundle.id,
            body=UpdateRiskRuleBundleRequest(is_default=True, version=2),
            request_id="req_switch_audit",
        )

    with session_factory() as session:
        event = session.scalar(
            select(AuditLog).where(AuditLog.request_id == "req_switch_audit")
        )
        original = session.get(RiskRuleBundle, first_bundle.id)
        target = session.get(RiskRuleBundle, second_bundle.id)
        assert event is not None and original is not None and target is not None
        assert event.before_summary_json is not None
        assert event.after_summary_json is not None
        assert event.before_summary_json["organization_default_bundle_id"] == str(
            first_bundle.id
        )
        assert event.after_summary_json["organization_default_bundle_id"] == str(
            second_bundle.id
        )
        assert original.is_default is False
        assert target.is_default is True

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("forced switch audit failure")

    monkeypatch.setattr(risk_rule_service, "append_audit_log", fail_audit)
    with (
        pytest.raises(RuntimeError, match="forced switch audit failure"),
        session_factory() as session,
    ):
        risk_rule_service.update_bundle(
            session,
            actor=actor,
            bundle_id=first_bundle.id,
            body=UpdateRiskRuleBundleRequest(is_default=True, version=3),
            request_id="req_switch_audit_rollback",
        )

    with session_factory() as session:
        original = session.get(RiskRuleBundle, first_bundle.id)
        target = session.get(RiskRuleBundle, second_bundle.id)
        assert original is not None and target is not None
        assert original.is_default is False and original.version == 3
        assert target.is_default is True and target.version == 3
        assert (
            session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.request_id == "req_switch_audit_rollback"
                )
            )
            == 0
        )


def test_combined_default_switch_and_conflicting_rename_rolls_back(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "组合更新冲突组织")
    admin = _seed_user(
        session_factory,
        email="combined-conflict@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    first_bundle, first_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="已占用名称",
        rule_key="occupied_name",
    )
    second_bundle, second_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="待切换名称",
        rule_key="switch_name",
    )
    for index, version in enumerate((first_version, second_version)):
        with session_factory() as session:
            publish_version(
                session,
                actor=actor,
                version_id=version.id,
                request_id=f"req_name_conflict_publish_{index}",
            )

    with pytest.raises(ApplicationError) as error, session_factory() as session:
        update_bundle(
            session,
            actor=actor,
            bundle_id=second_bundle.id,
            body=UpdateRiskRuleBundleRequest(
                name=first_bundle.name,
                is_default=True,
                version=2,
            ),
            request_id="req_combined_conflict",
        )
    assert error.value.code == "RULE_BUNDLE_NAME_CONFLICT"

    with session_factory() as session:
        original = session.get(RiskRuleBundle, first_bundle.id)
        target = session.get(RiskRuleBundle, second_bundle.id)
        assert original is not None and target is not None
        assert original.is_default is True and original.version == 2
        assert target.is_default is False and target.version == 2
        assert target.name == "待切换名称"
        assert (
            session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.request_id == "req_combined_conflict"
                )
            )
            == 0
        )


def test_publish_rolls_back_when_audit_write_fails(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.modules.risks.rules import service as risk_rule_service

    organization = _seed_organization(session_factory, "发布回滚组织")
    admin = _seed_user(
        session_factory,
        email="publish-rollback@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    bundle, version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="回滚规则集",
        rule_key="rollback_rule",
    )

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("forced audit failure")

    monkeypatch.setattr(risk_rule_service, "append_audit_log", fail_audit)
    with pytest.raises(RuntimeError, match="forced audit failure"), session_factory() as session:
        risk_rule_service.publish_version(
            session,
            actor=actor,
            version_id=version.id,
            request_id="req_publish_rollback",
        )

    with session_factory() as session:
        persisted_bundle = session.get(RiskRuleBundle, bundle.id)
        persisted_version = session.get(RiskRuleBundleVersion, version.id)
        assert persisted_bundle is not None and persisted_version is not None
        assert persisted_bundle.current_published_version_id is None
        assert persisted_bundle.is_default is False
        assert persisted_bundle.version == 1
        assert persisted_version.status == "draft"
        assert persisted_version.version == 1
        assert (
            session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.organization_id == organization.id,
                    AuditLog.action == "risk_rule_version.published",
                )
            )
            == 0
        )


def test_publishing_new_default_version_updates_current_without_mutating_history(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "默认规则新版本组织")
    admin = _seed_user(
        session_factory,
        email="default-version@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    bundle, first_version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="持续发布规则集",
        rule_key="first_published_rule",
    )
    with session_factory() as session:
        publish_version(
            session,
            actor=actor,
            version_id=first_version.id,
            request_id="req_first_default_publish",
        )
    with session_factory() as session:
        historical = session.get(RiskRuleBundleVersion, first_version.id)
        assert historical is not None and historical.effective_at is not None
        first_effective_at = historical.effective_at

    second_version_id = uuid4()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(
            RiskRuleBundleVersion(
                id=second_version_id,
                organization_id=organization.id,
                bundle_id=bundle.id,
                version_no=2,
                status="draft",
                change_note="第二个发布版本",
            )
        )
        session.flush()
        session.add(
            RiskRule(
                id=uuid4(),
                organization_id=organization.id,
                bundle_version_id=second_version_id,
                rule_key="second_published_rule",
                risk_type="payment_terms",
                engine="deterministic",
                condition_json={"operator": "field_missing", "field": "payment_terms"},
                severity="high",
                suggestion="请复核第二版付款条件。",
                enabled=True,
            )
        )
        unit_of_work.commit()

    with session_factory() as session:
        published = publish_version(
            session,
            actor=actor,
            version_id=second_version_id,
            request_id="req_second_default_publish",
        )
    assert published["is_default"] is True
    assert published["current_published_version_id"] == second_version_id

    with session_factory() as session:
        current_bundle = session.get(RiskRuleBundle, bundle.id)
        historical = session.get(RiskRuleBundleVersion, first_version.id)
        assert current_bundle is not None and historical is not None
        assert current_bundle.current_published_version_id == second_version_id
        assert historical.status == "published"
        assert historical.effective_at == first_effective_at
        assert historical.version == 2


def test_database_rejects_mutation_of_published_version_and_rules(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "不可变约束组织")
    admin = _seed_user(
        session_factory,
        email="immutable-rules@example.com",
        organization=organization,
        role="org_admin",
    )
    actor = _tenant_context(session_factory, organization=organization, user=admin)
    _, version = _seed_draft_bundle(
        session_factory,
        organization=organization,
        name="不可变规则集",
        rule_key="immutable_rule",
    )
    with session_factory() as session:
        publish_version(
            session,
            actor=actor,
            version_id=version.id,
            request_id="req_publish_immutable",
        )

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        published = session.get(RiskRuleBundleVersion, version.id)
        assert published is not None
        published.change_note = "不应修改"
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        published_rule = session.scalar(
            select(RiskRule).where(RiskRule.bundle_version_id == version.id)
        )
        assert published_rule is not None
        published_rule.suggestion = "不应修改"
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        session.add(
            RiskRule(
                id=uuid4(),
                organization_id=organization.id,
                bundle_version_id=version.id,
                rule_key="late_insert",
                risk_type="payment_terms",
                engine="deterministic",
                condition_json={"operator": "field_missing", "field": "payment_terms"},
                severity="medium",
                suggestion="不应插入。",
                enabled=True,
            )
        )
        unit_of_work.commit()

    draft_version_id = uuid4()
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        session.add(
            RiskRuleBundleVersion(
                id=draft_version_id,
                organization_id=organization.id,
                bundle_id=version.bundle_id,
                version_no=2,
                status="draft",
                change_note="不可变性测试草稿",
            )
        )
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        published_rule = session.scalar(
            select(RiskRule).where(RiskRule.bundle_version_id == version.id)
        )
        assert published_rule is not None
        published_rule.bundle_version_id = draft_version_id
        unit_of_work.commit()

    with (
        pytest.raises(DBAPIError),
        session_factory() as session,
        UnitOfWork(session) as unit_of_work,
    ):
        published_rule = session.scalar(
            select(RiskRule).where(RiskRule.bundle_version_id == version.id)
        )
        assert published_rule is not None
        session.delete(published_rule)
        unit_of_work.commit()


def test_risk_rule_baseline_installation_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    organization = _seed_organization(session_factory, "基线组织")
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        install_risk_rule_baseline(session, organization_id=organization.id)
        install_risk_rule_baseline(session, organization_id=organization.id)
        unit_of_work.commit()

    with session_factory() as session:
        bundle = session.scalar(
            select(RiskRuleBundle).where(RiskRuleBundle.organization_id == organization.id)
        )
        assert bundle is not None
        assert bundle.is_default is True
        assert (
            session.scalar(
                select(func.count(RiskRule.id)).where(RiskRule.organization_id == organization.id)
            )
            == 11
        )
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.organization_id == organization.id,
                AuditLog.action == "risk_rule_version.published",
            )
        )
        assert audit is not None
        assert audit.request_id == "system-risk-rule-baseline"
        assert audit.after_summary_json is not None
        assert audit.after_summary_json["source"] == "system_baseline"


def test_risk_rule_openapi_projects_phase8a_paths(auth_client: TestClient) -> None:
    openapi = auth_client.app.openapi()
    paths = openapi["paths"]
    expected_methods = {
        "/api/v1/risk-rule-bundles": {"get", "post"},
        "/api/v1/risk-rule-bundles/{bundle_id}": {"get", "patch"},
        "/api/v1/risk-rule-bundles/{bundle_id}/versions": {"post"},
        "/api/v1/risk-rule-bundle-versions/{version_id}": {"get", "patch"},
        "/api/v1/risk-rule-bundle-versions/{version_id}/publish": {"post"},
    }
    for path, methods in expected_methods.items():
        assert path in paths
        assert methods <= set(paths[path])

    expected_contract_projection = {
        ("/api/v1/risk-rule-bundles", "get"): ("200", "CursorPageResponse"),
        ("/api/v1/risk-rule-bundles", "post"): ("201", "RiskRuleBundleResponse"),
        ("/api/v1/risk-rule-bundles/{bundle_id}", "get"): (
            "200",
            "RiskRuleBundleDetailResponse",
        ),
        ("/api/v1/risk-rule-bundles/{bundle_id}", "patch"): ("200", "RiskRuleBundleResponse"),
        ("/api/v1/risk-rule-bundles/{bundle_id}/versions", "post"): (
            "201",
            "RiskRuleVersionResponse",
        ),
        ("/api/v1/risk-rule-bundle-versions/{version_id}", "get"): (
            "200",
            "RiskRuleVersionResponse",
        ),
        ("/api/v1/risk-rule-bundle-versions/{version_id}", "patch"): (
            "200",
            "RiskRuleVersionResponse",
        ),
        ("/api/v1/risk-rule-bundle-versions/{version_id}/publish", "post"): (
            "200",
            "RiskRuleVersionResponse",
        ),
    }
    for (path, method), (status_code, schema_name) in expected_contract_projection.items():
        operation = paths[path][method]
        assert (
            operation["responses"][status_code]["content"]["application/json"]["schema"]["$ref"]
            == f"#/components/schemas/{schema_name}"
        )

    write_operations = {
        ("/api/v1/risk-rule-bundles", "post"): "CreateRiskRuleBundleRequest",
        ("/api/v1/risk-rule-bundles/{bundle_id}", "patch"): "UpdateRiskRuleBundleRequest",
        ("/api/v1/risk-rule-bundles/{bundle_id}/versions", "post"): "CreateRiskRuleVersionRequest",
        ("/api/v1/risk-rule-bundle-versions/{version_id}", "patch"): "UpdateRiskRuleVersionRequest",
        (
            "/api/v1/risk-rule-bundle-versions/{version_id}/publish",
            "post",
        ): "PublishRiskRuleVersionRequest",
    }
    for (path, method), schema_name in write_operations.items():
        operation = paths[path][method]
        assert operation["requestBody"]["required"] is True
        assert (
            operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            == f"#/components/schemas/{schema_name}"
        )
        parameter_names = {parameter["name"] for parameter in operation.get("parameters", [])}
        if (path, method) == ("/api/v1/risk-rule-bundles", "post"):
            assert "X-Organization-ID" in parameter_names
        else:
            assert "X-Organization-ID" not in parameter_names
        if (path, method) in {
            ("/api/v1/risk-rule-bundles", "post"),
            ("/api/v1/risk-rule-bundles/{bundle_id}/versions", "post"),
        }:
            idempotency_parameter = next(
                parameter
                for parameter in operation["parameters"]
                if parameter["name"] == "Idempotency-Key"
            )
            assert idempotency_parameter["required"] is True

    assert {"200", "401", "403", "404"} <= set(
        paths["/api/v1/risk-rule-bundle-versions/{version_id}"]["get"]["responses"]
    )
    assert {"200", "401", "403", "404", "409", "422"} <= set(
        paths["/api/v1/risk-rule-bundle-versions/{version_id}/publish"]["post"]["responses"]
    )
    publish_request = paths["/api/v1/risk-rule-bundle-versions/{version_id}/publish"]["post"][
        "requestBody"
    ]
    assert publish_request["required"] is True
    assert publish_request["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublishRiskRuleVersionRequest"
    }

    schemas = openapi["components"]["schemas"]
    assert schemas["PublishRiskRuleVersionRequest"]["additionalProperties"] is False
    assert schemas["PublishRiskRuleVersionRequest"]["properties"] == {}
    condition_schema = schemas["RiskRuleCondition-Input"]
    assert condition_schema["discriminator"]["propertyName"] == "operator"
    assert len(condition_schema["oneOf"]) == 10
    assert schemas["KeywordCondition"]["properties"]["field"]["const"] == "contract_text"
    assert (
        schemas["AmountThresholdCondition"]["properties"]["field"]["const"]
        == "contract_amount"
    )
    assert "data_compliance" in schemas["FieldExistsCondition"]["properties"]["field"]["enum"]
    rules_schema = schemas["CreateRiskRuleVersionRequest"]["properties"]["rules"]
    assert rules_schema["minItems"] == 1
    assert rules_schema["maxItems"] == 200
