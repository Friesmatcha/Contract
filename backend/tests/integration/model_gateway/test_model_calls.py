from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.modules.clauses.templates.models import ClauseTemplate, ClauseTemplateVersion
from backend.app.modules.contracts.models import Contract, ContractFile, FileObject
from backend.app.modules.identity.models import Organization, OrganizationMembership, User
from backend.app.modules.reviews.models import ModelCall, ReviewStageRun, ReviewTask
from backend.app.modules.risks.rules.models import RiskRuleBundle, RiskRuleBundleVersion
from backend.app.shared.model_telemetry import (
    ModelCallContext,
    ModelCallTelemetry,
    model_fingerprint,
    persist_model_call,
)


def _seed_facts(session: Session) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    organization_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    contract_id = uuid4()
    file_id = uuid4()
    now = datetime.now(UTC)

    organization = Organization(
        id=organization_id,
        name=f"Org {organization_id}",
        normalized_name=f"org {organization_id}".lower(),
    )
    user = User(
        id=user_id,
        email=f"{user_id}@example.test",
        normalized_email=f"{user_id}@example.test",
        display_name="Phase 9B test user",
    )
    membership = OrganizationMembership(
        id=membership_id,
        organization_id=organization_id,
        user_id=user_id,
        email=user.email,
        normalized_email=user.normalized_email,
        role="reviewer",
        status="active",
    )
    contract = Contract(
        id=contract_id,
        organization_id=organization_id,
        display_no=f"CTR-{str(contract_id)[:8]}",
        title="Phase 9B test contract",
        declared_type="purchase",
        owner_id=user_id,
    )
    file_object = FileObject(
        id=file_id,
        organization_id=organization_id,
        storage_key=f"org/{organization_id}/file/{file_id}",
        original_name="redacted.txt",
        media_type="text/plain",
        size_bytes=10,
        sha256="a" * 64,
        scan_status="clean",
        storage_status="stored",
    )
    contract_file = ContractFile(
        id=uuid4(),
        organization_id=organization_id,
        contract_id=contract_id,
        file_object_id=file_id,
        version_no=1,
        external_model_notice_acknowledged_at=now,
        external_model_notice_acknowledged_by=user_id,
    )
    session.add_all([organization, user])
    session.flush()
    session.add(membership)
    session.flush()
    session.add_all([contract, file_object])
    session.flush()
    session.add(contract_file)
    session.flush()

    rule_bundle_id = uuid4()
    rule_version_id = uuid4()
    rule_bundle = RiskRuleBundle(
        id=rule_bundle_id,
        organization_id=organization_id,
        name="Test rules",
        normalized_name="test rules",
        is_default=False,
    )
    rule_version = RiskRuleBundleVersion(
        id=rule_version_id,
        organization_id=organization_id,
        bundle_id=rule_bundle_id,
        version_no=1,
        status="published",
        change_note="Test version",
        effective_at=now,
        published_by=user_id,
    )
    session.add_all([rule_bundle, rule_version])
    session.flush()
    rule_bundle.current_published_version_id = rule_version_id
    rule_bundle.is_default = True

    template_id = uuid4()
    template_version_id = uuid4()
    template = ClauseTemplate(
        id=template_id,
        organization_id=organization_id,
        name="Test template",
        normalized_name="test template",
        contract_type="purchase",
        business_scenario="standard",
        is_default=False,
    )
    template_version = ClauseTemplateVersion(
        id=template_version_id,
        organization_id=organization_id,
        template_id=template_id,
        version_no=1,
        status="published",
        change_note="Test version",
        effective_at=now,
        published_by=user_id,
    )
    session.add_all([template, template_version])
    session.flush()
    template.current_published_version_id = template_version_id
    template.is_default = True
    session.flush()

    task = ReviewTask(
        id=uuid4(),
        organization_id=organization_id,
        contract_id=contract_id,
        contract_file_id=contract_file.id,
        document_version_id=None,
        rule_bundle_version_id=rule_version_id,
        clause_template_version_id=template_version_id,
        created_by=user_id,
        display_no=f"REV-{str(contract_id)[:8]}",
        business_scenario="standard",
        prompt_bundle_version="platform-baseline-v1",
        model_config_json={"organization_overrides_allowed": False},
        input_snapshot_json={"file_sha256": "a" * 64},
        input_fingerprint="b" * 64,
    )
    stage_run = ReviewStageRun(
        id=uuid4(),
        organization_id=organization_id,
        review_task_id=task.id,
        stage="classification",
        attempt_no=1,
        input_fingerprint="c" * 64,
    )
    session.add(task)
    session.flush()
    session.add(stage_run)
    session.flush()
    return organization_id, task.id, stage_run.id, user_id, contract_id


def _telemetry() -> ModelCallTelemetry:
    return ModelCallTelemetry(
        organization_id=None,
        review_task_id=None,
        stage_run_id=None,
        capability="classification",
        provider="fake",
        model="fake-model-v1",
        model_fingerprint=model_fingerprint(
            provider="fake",
            model="fake-model-v1",
            prompt_version="platform-baseline-v1",
            schema_version="model-schema-v1",
        ),
        prompt_version="platform-baseline-v1",
        response_schema_version="model-schema-v1",
        sanitization_policy_version="sanitization-v1",
        request_fingerprint="d" * 64,
        provider_request_id="fake-provider-request-1",
        status="succeeded",
        token_input=10,
        token_output=5,
        cost=0.001,
        latency_ms=12,
    )


def test_model_call_persists_safe_telemetry_with_tenant_and_stage_links(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        organization_id, task_id, stage_run_id, _, _ = _seed_facts(session)
        context = ModelCallContext(
            organization_id=organization_id,
            review_task_id=task_id,
            stage_run_id=stage_run_id,
            capability="classification",
        )
        row = persist_model_call(session, _telemetry(), context=context)
        session.commit()
        session.refresh(row)
        assert row.organization_id == organization_id
        assert row.review_task_id == task_id
        assert row.stage_run_id == stage_run_id
        assert row.provider_request_id == "fake-provider-request-1"
        assert str(row.cost) == "0.00100000"

        column_names = set(ModelCall.__table__.columns.keys())
        assert not {"prompt", "response", "api_key", "secret_ref"} & column_names


def test_model_call_stage_composite_fk_blocks_cross_task_association(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        organization_id, task_id, stage_run_id, _, _ = _seed_facts(session)
        other_org, other_task, other_stage, _, _ = _seed_facts(session)
        session.commit()
        row = ModelCall(
            organization_id=organization_id,
            review_task_id=task_id,
            stage_run_id=other_stage,
            capability="classification",
            provider="fake",
            model="fake-model-v1",
            model_fingerprint="e" * 64,
            prompt_version="platform-baseline-v1",
            response_schema_version="model-schema-v1",
            sanitization_policy_version="sanitization-v1",
            request_fingerprint="f" * 64,
            status="succeeded",
            latency_ms=1,
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert other_org != organization_id
        assert other_task != task_id
        assert stage_run_id != other_stage


def test_model_call_is_rolled_back_with_business_transaction(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        organization_id, task_id, stage_run_id, _, _ = _seed_facts(session)
        context = ModelCallContext(
            organization_id=organization_id,
            review_task_id=task_id,
            stage_run_id=stage_run_id,
            capability="classification",
        )
        persist_model_call(session, _telemetry(), context=context)
        session.rollback()

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 0
