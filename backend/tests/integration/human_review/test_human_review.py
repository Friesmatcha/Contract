from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.model.fake import FakeModelGateway, FakeResponse
from backend.app.modules.contracts.models import ContractAccessGrant
from backend.app.modules.documents.models import DocumentBlock, DocumentVersion, SourceSpan
from backend.app.modules.feedback.schemas import FeedbackCreateRequest
from backend.app.modules.feedback.service import create_feedback, feedback_summary
from backend.app.modules.identity.models import Organization, OrganizationMembership, User
from backend.app.modules.reviews.models import ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import (
    ClauseComparison,
    ContractClassification,
    ExtractedField,
    RiskFinding,
    RiskFindingEvidence,
)
from backend.app.modules.reviews.results.service import (
    execute_classification,
    execute_clause_comparison,
    execute_extraction,
    execute_risk_analysis,
)
from backend.app.modules.reviews.revisions.models import ResultRevision
from backend.app.modules.reviews.revisions.schemas import (
    ClauseComparisonRevisionRequest,
    ContractClassificationRevisionRequest,
    ExtractedFieldRevisionRequest,
    RiskFindingRevisionRequest,
)
from backend.app.modules.reviews.revisions.service import (
    completion_blockers,
    revise_classification,
    revise_clause_comparison,
    revise_extracted_field,
    revise_risk_finding,
)
from backend.app.modules.reviews.service import complete_review_task
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, IdempotencyConflictError
from backend.app.shared.tenant import TenantContext
from backend.tests.integration.classification_extraction.test_results import (
    _seed,
    _task_and_runs,
)
from backend.tests.integration.review_results.test_results import _analysis_facts

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "correct-horse-battery"


def _prepare_results(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    facts = _seed(session_factory)
    with session_factory() as session:
        organization = session.get(Organization, facts["organization_id"])
        assert organization is not None
        organization.name = f"Phase 12 Org {uuid4()}"
        organization.normalized_name = organization.name.lower()
        session.commit()
    task, classification_run, extraction_run = _task_and_runs(session_factory, facts)
    task, risk_run, clause_run = _analysis_facts(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "risk_analysis": [
                FakeResponse(
                    {
                        "findings": [
                            {
                                "risk_type": "unlimited_liability",
                                "severity": "high",
                                "title": "Liability cap is missing",
                                "basis": "The contract has no cap.",
                                "evidence": [
                                    {
                                        "source_span_id": str(facts["span_id"]),
                                        "quote": "采购合同",
                                    }
                                ],
                            }
                        ],
                        "evidence": [
                            {"source_span_id": str(facts["span_id"]), "quote": "采购合同"}
                        ],
                    }
                )
            ],
            "clause_comparison": [
                FakeResponse(
                    {
                        "comparisons": [
                            {
                                "clause_key": "payment",
                                "result": "deviation",
                                "explanation": "Payment deadline is missing.",
                                "evidence": [
                                    {
                                        "source_span_id": str(facts["span_id"]),
                                        "quote": "采购合同",
                                    }
                                ],
                            }
                        ],
                        "evidence": [
                            {"source_span_id": str(facts["span_id"]), "quote": "采购合同"}
                        ],
                    }
                )
            ],
        }
    )
    with session_factory() as session:
        session_task = session.get(ReviewTask, task.id)
        session_classification_run = session.get(ReviewStageRun, classification_run.id)
        session_extraction_run = session.get(ReviewStageRun, extraction_run.id)
        session_risk_run = session.get(ReviewStageRun, risk_run.id)
        session_clause_run = session.get(ReviewStageRun, clause_run.id)
        assert (
            session_task is not None
            and session_classification_run is not None
            and session_extraction_run is not None
            and session_risk_run is not None
            and session_clause_run is not None
        )
        execute_classification(
            session,
            task=session_task,
            stage_run=session_classification_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        execute_extraction(
            session,
            task=session_task,
            stage_run=session_extraction_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        execute_risk_analysis(
            session,
            task=session_task,
            stage_run=session_risk_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        execute_clause_comparison(
            session,
            task=session_task,
            stage_run=session_clause_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        session_task.status = "pending_review"
        session_task.model_config_json = {"model": "fake-model-v1"}
        session.commit()
    with session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == facts["organization_id"],
                OrganizationMembership.user_id == facts["user_id"],
            )
        )
        assert membership is not None
        facts["membership_id"] = membership.id
    return facts


def _actor(session: Session, facts: dict[str, UUID]) -> TenantContext:
    return TenantContext(
        organization_id=facts["organization_id"],
        user_id=facts["user_id"],
        membership_id=facts["membership_id"],
    )


def test_completion_blockers_are_server_computed_and_completion_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _prepare_results(session_factory)
    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        field = session.scalar(select(ExtractedField).where(ExtractedField.field_key == "parties"))
        clause = session.scalar(select(ClauseComparison))
        assert classification is not None and field is not None and clause is not None
        classification.status = "needs_confirmation"
        field.status = "needs_confirmation"
        clause.status = "uncertain"
        session.commit()

    with session_factory() as session:
        blockers = completion_blockers(
            session, organization_id=facts["organization_id"], task_id=facts["task_id"]
        )
        assert {item["code"] for item in blockers} == {
            "CLASSIFICATION_NEEDS_CONFIRMATION",
            "FIELD_NEEDS_CONFIRMATION",
            "RISK_PENDING_REVIEW",
            "CLAUSE_UNCERTAIN",
        }
        session.rollback()
        with pytest.raises(ApplicationError) as error_info:
            complete_review_task(
                session,
                actor=_actor(session, facts),
                task_id=facts["task_id"],
                note="manual review",
                idempotency_key="complete-blocked",
                request_id="phase12-blocked",
            )
        assert error_info.value.status_code == 409
        assert error_info.value.code == "UNRESOLVED_REQUIRED_FINDINGS"
        assert {item["code"] for item in error_info.value.details["blockers"]} == {
            "CLASSIFICATION_NEEDS_CONFIRMATION",
            "FIELD_NEEDS_CONFIRMATION",
            "RISK_PENDING_REVIEW",
            "CLAUSE_UNCERTAIN",
        }

    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        task.status = "completed"
        session.commit()
        with pytest.raises(ApplicationError) as error_info:
            complete_review_task(
                session,
                actor=_actor(session, facts),
                task_id=facts["task_id"],
                note="repeat",
                idempotency_key="complete-invalid-state",
                request_id="phase12-invalid-state",
            )
        assert error_info.value.status_code == 409
        assert error_info.value.code == "INVALID_STATE_TRANSITION"
        task.status = "pending_review"
        session.commit()

    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        assert classification is not None
        classification_id = classification.id
        session.rollback()
        revise_classification(
            session,
            actor=_actor(session, facts),
            subject_id=classification_id,
            body=ContractClassificationRevisionRequest(
                current_value="purchase", status="corrected", reason="checked", version=1
            ),
            request_id="phase12-classification",
        )
    with session_factory() as session:
        actor = _actor(session, facts)
        field = session.scalar(select(ExtractedField).where(ExtractedField.field_key == "parties"))
        assert field is not None
        field_id = field.id
        session.rollback()
        revise_extracted_field(
            session,
            actor=actor,
            subject_id=field_id,
            body=ExtractedFieldRevisionRequest(
                current_value={"party_a": "A", "party_b": "B"},
                status="corrected",
                reason="checked",
                version=1,
            ),
            request_id="phase12-field",
        )
    with session_factory() as session:
        finding_ids = list(
            session.scalars(
                select(RiskFinding.id).where(
                    RiskFinding.organization_id == facts["organization_id"],
                    RiskFinding.review_task_id == facts["task_id"],
                )
            )
        )
        assert finding_ids
    for index, finding_id in enumerate(finding_ids):
        with session_factory() as session:
            revise_risk_finding(
                session,
                actor=_actor(session, facts),
                subject_id=finding_id,
                body=RiskFindingRevisionRequest(
                    status="confirmed", reason="checked", version=1
                ),
                request_id=f"phase12-risk-{index}",
            )
    with session_factory() as session:
        comparison = session.scalar(
            select(ClauseComparison).where(
                ClauseComparison.organization_id == facts["organization_id"],
                ClauseComparison.review_task_id == facts["task_id"],
            )
        )
        assert comparison is not None
        comparison_id = comparison.id
        session.rollback()
    with session_factory() as session:
        revise_clause_comparison(
            session,
            actor=_actor(session, facts),
            subject_id=comparison_id,
            body=ClauseComparisonRevisionRequest(
                status="deviated", reason="checked", version=1
            ),
            request_id="phase12-clause",
        )
    with session_factory() as session:
        session.rollback()
        completed = complete_review_task(
            session,
            actor=_actor(session, facts),
            task_id=facts["task_id"],
            note="manual review",
            idempotency_key="complete-success",
            request_id="phase12-complete",
        )
        replayed = complete_review_task(
            session,
            actor=_actor(session, facts),
            task_id=facts["task_id"],
            note="manual review",
            idempotency_key="complete-success",
            request_id="phase12-complete-replay",
        )
        assert completed.status == replayed.status == "completed"
        assert completed.completed_by == facts["user_id"]
        assert completed.completed_at is not None


def test_revision_conflict_preserves_model_value_and_writes_before_after(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _prepare_results(session_factory)
    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        assert classification is not None
        classification_id = classification.id
        session.rollback()
        revise_classification(
            session,
            actor=_actor(session, facts),
            subject_id=classification_id,
            body=ContractClassificationRevisionRequest(
                current_value="sales", status="corrected", reason="manual", version=1
            ),
            request_id="phase12-revision-1",
        )
    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        assert classification is not None
        classification_id = classification.id
        session.rollback()
        with pytest.raises(ApplicationError) as error_info:
            revise_classification(
                session,
                actor=_actor(session, facts),
                subject_id=classification_id,
                body=ContractClassificationRevisionRequest(
                    current_value="nda", status="corrected", reason="stale", version=1
                ),
                request_id="phase12-revision-stale",
            )
        assert error_info.value.code == "RESOURCE_VERSION_CONFLICT"
        assert error_info.value.details == {"current_version": 2}
    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        revision = session.scalar(select(ResultRevision))
        assert classification is not None and revision is not None
        assert classification.model_value == "other"
        assert classification.current_value == "sales"
        assert revision.before_json["model_value"] == "other"
        assert revision.before_json["current_value"] == "other"
        assert revision.after_json["current_value"] == "sales"
        assert revision.version_before == 1 and revision.version_after == 2


def test_invalid_document_evidence_blocks_confirmation(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _prepare_results(session_factory)
    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        finding = session.scalar(
            select(RiskFinding).where(
                RiskFinding.organization_id == task.organization_id,
                RiskFinding.review_task_id == task.id,
            )
        )
        assert finding is not None
        evidence = session.scalar(
            select(RiskFindingEvidence).where(
                RiskFindingEvidence.organization_id == task.organization_id,
                RiskFindingEvidence.finding_id == finding.id,
            )
        )
        assert evidence is not None
        other_document = DocumentVersion(
            id=uuid4(),
            organization_id=task.organization_id,
            contract_file_id=task.contract_file_id,
            parser_name="docx",
            parser_version="test",
            parse_fingerprint="d" * 64,
            text_sha256=sha256(b"other document").hexdigest(),
            ocr_status="not_required",
            page_count=0,
            status="succeeded",
        )
        other_block = DocumentBlock(
            id=uuid4(),
            organization_id=task.organization_id,
            document_version_id=other_document.id,
            page_id=None,
            order_no=1,
            block_type="paragraph",
            paragraph_no=1,
            text="other document",
        )
        other_span = SourceSpan(
            id=uuid4(),
            organization_id=task.organization_id,
            document_version_id=other_document.id,
            block_id=other_block.id,
            page_id=None,
            start_offset=0,
            end_offset=14,
            quote="other document",
            quote_sha256=sha256(b"other document").hexdigest(),
        )
        session.add(other_document)
        session.flush()
        session.add(other_block)
        session.flush()
        session.add(other_span)
        session.flush()
        evidence.document_version_id = other_document.id
        evidence.source_span_id = other_span.id
        finding.evidence_span_id = other_span.id
        session.commit()
    with session_factory() as session:
        finding = session.scalar(
            select(RiskFinding).where(
                RiskFinding.organization_id == facts["organization_id"],
                RiskFinding.review_task_id == facts["task_id"],
            )
        )
        assert finding is not None
        finding_id = finding.id
        session.rollback()
        with pytest.raises(ApplicationError) as error_info:
            revise_risk_finding(
                session,
                actor=_actor(session, facts),
                subject_id=finding_id,
                body=RiskFindingRevisionRequest(status="confirmed", version=1),
                request_id="phase12-invalid-evidence",
            )
        assert error_info.value.code == "EVIDENCE_REQUIRED"
        blockers = completion_blockers(
            session, organization_id=facts["organization_id"], task_id=facts["task_id"]
        )
        assert any(item["code"] == "RISK_EVIDENCE_REQUIRED" for item in blockers)
    with session_factory() as session:
        finding = session.get(RiskFinding, finding_id)
        assert finding is not None
        assert finding.status == "pending_review"
        assert finding.version == 1
        assert session.scalar(
            select(ResultRevision.id).where(ResultRevision.subject_id == finding_id)
        ) is None


def test_feedback_is_tenant_scoped_idempotent_and_filtered(
    session_factory: sessionmaker[Session],
) -> None:
    first = _prepare_results(session_factory)
    second = _prepare_results(session_factory)
    with session_factory() as session:
        first_classification = session.scalar(
            select(ContractClassification).where(
                ContractClassification.organization_id == first["organization_id"]
            )
        )
        second_classification = session.scalar(
            select(ContractClassification).where(
                ContractClassification.organization_id == second["organization_id"]
            )
        )
        first_finding = session.scalar(
            select(RiskFinding).where(
                RiskFinding.organization_id == first["organization_id"],
                RiskFinding.review_task_id == first["task_id"],
                RiskFinding.risk_type == "purchase_keyword",
            )
        )
        assert first_classification is not None and second_classification is not None
        assert first_finding is not None
        first_classification_id = first_classification.id
        second_classification_id = second_classification.id
        first_finding_id = first_finding.id
        session.rollback()
        first_body = FeedbackCreateRequest(
            review_task_id=first["task_id"],
            subject_type="classification",
            subject_id=first_classification_id,
            label="modified",
            corrected_value=None,
        )
        created = create_feedback(
            session,
            actor=_actor(session, first),
            body=first_body,
            idempotency_key="feedback-same",
            request_id="phase12-feedback-1",
        )
        replayed = create_feedback(
            session,
            actor=_actor(session, first),
            body=first_body,
            idempotency_key="feedback-same",
            request_id="phase12-feedback-replay",
        )
        assert created.id == replayed.id
        with pytest.raises(IdempotencyConflictError):
            create_feedback(
                session,
                actor=_actor(session, first),
                body=first_body.model_copy(update={"label": "incorrect"}),
                idempotency_key="feedback-same",
                request_id="phase12-feedback-conflict",
            )
        with pytest.raises(ApplicationError) as error_info:
            create_feedback(
                session,
                actor=_actor(session, first),
                body=FeedbackCreateRequest(
                    review_task_id=first["task_id"],
                    subject_type="classification",
                    subject_id=second_classification_id,
                    label="incorrect",
                ),
                idempotency_key="feedback-cross-tenant",
                request_id="phase12-feedback-cross-tenant",
            )
        assert error_info.value.code == "SUBJECT_ORGANIZATION_MISMATCH"
        create_feedback(
            session,
            actor=_actor(session, first),
            body=FeedbackCreateRequest(
                review_task_id=first["task_id"],
                subject_type="risk_finding",
                subject_id=first_finding_id,
                label="incorrect",
            ),
            idempotency_key="feedback-risk",
            request_id="phase12-feedback-risk",
        )
        second_body = FeedbackCreateRequest(
            review_task_id=second["task_id"],
            subject_type="classification",
            subject_id=second_classification_id,
            label="correct",
        )
        create_feedback(
            session,
            actor=_actor(session, second),
            body=second_body,
            idempotency_key="feedback-second-org",
            request_id="phase12-feedback-second-org",
        )
        summary = feedback_summary(
            session,
            organization_id=first["organization_id"],
            contract_type="purchase",
            rule_bundle_version_id=None,
            model_version="fake-model-v1",
            created_from=None,
            created_to=None,
        )
        assert summary["counts"] == {"correct": 0, "incorrect": 1, "modified": 1, "ignored": 0}
        assert summary["by_risk_type"] == [
            {
                    "risk_type": "purchase_keyword",
                "correct": 0,
                "incorrect": 1,
                "modified": 0,
                "ignored": 0,
            }
        ]


def test_viewer_can_read_results_but_cannot_revise(
    auth_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    facts = _prepare_results(session_factory)
    viewer = User(
        id=uuid4(),
        email="viewer-phase12@example.test",
        normalized_email="viewer-phase12@example.test",
        display_name="Viewer",
        password_hash=PasswordHasher().hash(PASSWORD),
    )
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        task = session.get(ReviewTask, facts["task_id"])
        classification = session.scalar(select(ContractClassification))
        assert task is not None and classification is not None
        session.add(viewer)
        session.flush()
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=facts["organization_id"],
                user_id=viewer.id,
                email=viewer.email,
                normalized_email=viewer.normalized_email,
                display_name=viewer.display_name,
                role="viewer",
                status="active",
            )
        )
        session.flush()
        session.add(
            ContractAccessGrant(
                id=uuid4(),
                organization_id=facts["organization_id"],
                contract_id=task.contract_id,
                user_id=viewer.id,
                access_level="read",
            )
        )
        unit_of_work.commit()
    login = auth_client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"email": viewer.email, "password": PASSWORD},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]
    readable = auth_client.get(f"/api/v1/review-tasks/{facts['task_id']}/results")
    assert readable.status_code == 200
    with session_factory() as session:
        classification = session.scalar(select(ContractClassification))
        assert classification is not None
        classification_id = classification.id
    forbidden = auth_client.patch(
        f"/api/v1/contract-classifications/{classification_id}",
        headers={**ORIGIN, "X-CSRF-Token": csrf_token},
        json={"current_value": "other", "status": "confirmed", "version": 1},
    )
    assert forbidden.status_code == 403


def test_phase12_openapi_projects_all_contract_routes(auth_client: TestClient) -> None:
    paths = auth_client.app.openapi()["paths"]
    expected = {
        "/api/v1/review-tasks/{review_task_id}/complete": "post",
        "/api/v1/contract-classifications/{classification_id}": "patch",
        "/api/v1/extracted-fields/{field_id}": "patch",
        "/api/v1/risk-findings/{finding_id}": "patch",
        "/api/v1/clause-comparisons/{comparison_id}": "patch",
        "/api/v1/feedback": "post",
        "/api/v1/feedback/summary": "get",
    }
    for path, method in expected.items():
        assert method in paths[path]
        assert "409" in paths[path][method]["responses"] or path.endswith("summary")
