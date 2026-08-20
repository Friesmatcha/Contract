from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.model.fake import FakeModelGateway, FakeResponse
from backend.app.modules.clauses.templates.models import ClauseTemplate, ClauseTemplateVersion
from backend.app.modules.contracts.models import Contract, ContractFile, FileObject
from backend.app.modules.documents.models import DocumentBlock, DocumentVersion, SourceSpan
from backend.app.modules.identity.models import Organization, OrganizationMembership, User
from backend.app.modules.reviews.models import ModelCall, ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import (
    CORE_EXTRACTED_FIELD_KEYS,
    ContractClassification,
    ExtractedField,
    ExtractedFieldEvidence,
)
from backend.app.modules.reviews.results.service import (
    ResultExecutionError,
    execute_classification,
    execute_extraction,
    get_review_results,
)
from backend.app.modules.risks.rules.models import RiskRuleBundle, RiskRuleBundleVersion
from backend.app.shared.db import UnitOfWork


def _seed(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    organization_id = uuid4()
    user_id = uuid4()
    contract_id = uuid4()
    file_id = uuid4()
    contract_file_id = uuid4()
    document_id = uuid4()
    block_id = uuid4()
    span_id = uuid4()
    task_id = uuid4()
    now = datetime.now(UTC)
    organization = Organization(id=organization_id, name="Phase 9C Org")
    user = User(
        id=user_id,
        email=f"{user_id}@example.test",
        normalized_email=f"{user_id}@example.test",
        display_name="Phase 9C Reviewer",
    )
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        email=user.email,
        normalized_email=user.normalized_email,
        display_name=user.display_name,
        role="reviewer",
        status="active",
    )
    contract = Contract(
        id=contract_id,
        organization_id=organization_id,
        display_no=f"CTR-{str(contract_id)[:8]}",
        title="Phase 9C contract",
        declared_type="purchase",
        owner_id=user_id,
    )
    file_object = FileObject(
        id=file_id,
        organization_id=organization_id,
        storage_key=f"phase9c/{file_id}",
        original_name="contract.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=10,
        sha256="a" * 64,
        scan_status="clean",
        storage_status="stored",
    )
    contract_file = ContractFile(
        id=contract_file_id,
        organization_id=organization_id,
        contract_id=contract_id,
        file_object_id=file_id,
        version_no=1,
        external_model_notice_acknowledged_at=now,
        external_model_notice_acknowledged_by=user_id,
    )
    document = DocumentVersion(
        id=document_id,
        organization_id=organization_id,
        contract_file_id=contract_file_id,
        parser_name="docx",
        parser_version="test",
        parse_fingerprint="b" * 64,
        text_sha256=sha256("甲方与乙方签订采购合同".encode()).hexdigest(),
        ocr_status="not_required",
        page_count=0,
        status="succeeded",
    )
    block = DocumentBlock(
        id=block_id,
        organization_id=organization_id,
        document_version_id=document_id,
        page_id=None,
        order_no=1,
        block_type="paragraph",
        paragraph_no=1,
        text="甲方与乙方签订采购合同",
    )
    source_span = SourceSpan(
        id=span_id,
        organization_id=organization_id,
        document_version_id=document_id,
        block_id=block_id,
        page_id=None,
        start_offset=0,
        end_offset=len(block.text),
        quote=block.text,
        quote_sha256=sha256(block.text.encode()).hexdigest(),
    )
    rule_bundle = RiskRuleBundle(
        id=uuid4(),
        organization_id=organization_id,
        name="Phase 9C rules",
        normalized_name="phase 9c rules",
        is_default=False,
    )
    rule_version = RiskRuleBundleVersion(
        id=uuid4(),
        organization_id=organization_id,
        bundle_id=rule_bundle.id,
        version_no=1,
        status="published",
        change_note="test",
        published_by=user_id,
    )
    template = ClauseTemplate(
        id=uuid4(),
        organization_id=organization_id,
        name="Phase 9C template",
        normalized_name="phase 9c template",
        contract_type="purchase",
        business_scenario="standard",
        is_default=False,
    )
    template_version = ClauseTemplateVersion(
        id=uuid4(),
        organization_id=organization_id,
        template_id=template.id,
        version_no=1,
        status="published",
        change_note="test",
        published_by=user_id,
    )
    task = ReviewTask(
        id=task_id,
        organization_id=organization_id,
        contract_id=contract_id,
        contract_file_id=contract_file_id,
        document_version_id=document_id,
        rule_bundle_version_id=rule_version.id,
        clause_template_version_id=template_version.id,
        created_by=user_id,
        display_no=f"REV-{str(task_id)[:8]}",
        business_scenario="standard",
        prompt_bundle_version="platform-baseline-v1",
        model_config_json={},
        input_snapshot_json={"file_sha256": "a" * 64},
        input_fingerprint="c" * 64,
    )
    classification_run = ReviewStageRun(
        id=uuid4(),
        organization_id=organization_id,
        review_task_id=task_id,
        stage="classification",
        attempt_no=1,
        status="running",
        input_fingerprint="d" * 64,
    )
    extraction_run = ReviewStageRun(
        id=uuid4(),
        organization_id=organization_id,
        review_task_id=task_id,
        stage="extraction",
        attempt_no=1,
        status="running",
        input_fingerprint="e" * 64,
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
        session.add(document)
        session.flush()
        session.add(block)
        session.flush()
        session.add(source_span)
        session.flush()
        session.add_all([rule_bundle, rule_version, template, template_version])
        session.flush()
        rule_bundle.current_published_version_id = rule_version.id
        template.current_published_version_id = template_version.id
        rule_bundle.is_default = True
        template.is_default = True
        session.add(task)
        session.flush()
        session.add_all([classification_run, extraction_run])
        unit_of_work.commit()
    return {
        "organization_id": organization_id,
        "user_id": user_id,
        "task_id": task_id,
        "document_id": document_id,
        "span_id": span_id,
        "classification_run_id": classification_run.id,
        "extraction_run_id": extraction_run.id,
    }


def _task_and_runs(
    session_factory: sessionmaker[Session], facts: dict[str, UUID]
) -> tuple[ReviewTask, ReviewStageRun, ReviewStageRun]:
    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        classification_run = session.get(ReviewStageRun, facts["classification_run_id"])
        extraction_run = session.get(ReviewStageRun, facts["extraction_run_id"])
        assert task is not None and classification_run is not None and extraction_run is not None
        return task, classification_run, extraction_run


def test_classification_extraction_persists_evidence_and_reuses_fingerprints(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    gateway = FakeModelGateway()
    task, classification_run, extraction_run = _task_and_runs(session_factory, facts)
    with session_factory() as session:
        execute_classification(
            session,
            task=task,
            stage_run=classification_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        execute_extraction(
            session,
            task=task,
            stage_run=extraction_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        assert len(gateway.calls) == 2
        execute_classification(
            session,
            task=task,
            stage_run=classification_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        execute_extraction(
            session,
            task=task,
            stage_run=extraction_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        assert len(gateway.calls) == 2
    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        fields = list(session.scalars(select(ExtractedField)))
        model_calls = list(session.scalars(select(ModelCall)))
        assert classification is not None
        assert classification.evidence_span_id == facts["span_id"]
        assert {field.field_key for field in fields} == set(CORE_EXTRACTED_FIELD_KEYS)
        assert all(field.status == "detected" for field in fields)
        assert len(model_calls) == 2
        payload = get_review_results(
            session,
            organization_id=facts["organization_id"],
            task_id=facts["task_id"],
            viewer_user_id=None,
            include_evidence=True,
        )
        assert payload["classification"]["evidence"][0]["source_span_id"] == facts["span_id"]
        assert len(payload["extracted_fields"]) == 7


def test_missing_values_are_json_null_and_have_no_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    missing_fields = [
        {"field_key": key, "value": None, "confidence": 0.2, "evidence": []}
        for key in CORE_EXTRACTED_FIELD_KEYS
    ]
    gateway = FakeModelGateway(
        fixtures={
            "extraction": [
                FakeResponse({"fields": missing_fields, "evidence": []})
            ]
        }
    )
    task, _, extraction_run = _task_and_runs(session_factory, facts)
    with session_factory() as session:
        execute_extraction(
            session,
            task=task,
            stage_run=extraction_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        fields = list(session.scalars(select(ExtractedField)))
        assert len(fields) == 7
        assert all(field.current_value_json is None for field in fields)
        assert all(field.status == "not_found" for field in fields)
        assert session.scalar(select(ExtractedFieldEvidence.id)) is None


def test_invalid_cross_document_evidence_never_creates_a_classification(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    task, classification_run, _ = _task_and_runs(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "classification": [
                FakeResponse(
                    {
                        "category": "purchase",
                        "confidence": 0.9,
                        "evidence": [
                            {"source_span_id": str(uuid4()), "quote": "甲方与乙方签订采购合同"}
                        ],
                    }
                )
            ]
        }
    )
    with session_factory() as session:
        with pytest.raises(ResultExecutionError) as error_info:
            execute_classification(
                session,
                task=task,
                stage_run=classification_run,
                gateway=gateway,
                heartbeat=lambda: None,
            )
        assert error_info.value.code == "MODEL_EVIDENCE_INVALID"
        assert session.scalar(select(ContractClassification)) is None
