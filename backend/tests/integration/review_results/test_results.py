from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.integrations.model.fake import FakeModelGateway, FakeResponse
from backend.app.modules.clauses.templates.models import ClauseTemplateVersion, StandardClause
from backend.app.modules.reviews.models import ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import (
    ClauseComparison,
    ClauseComparisonEvidence,
    RiskFinding,
)
from backend.app.modules.reviews.results.service import (
    ResultExecutionError,
    execute_clause_comparison,
    execute_risk_analysis,
    get_review_results,
)
from backend.app.modules.risks.rules.models import RiskRule, RiskRuleBundleVersion
from backend.app.shared.db import UnitOfWork
from backend.tests.integration.classification_extraction.test_results import (
    _seed,
    _task_and_runs,
)


def _analysis_facts(
    session_factory: sessionmaker[Session], facts: dict[str, UUID]
) -> tuple[ReviewTask, ReviewStageRun, ReviewStageRun]:
    with session_factory() as session, UnitOfWork(session) as unit_of_work:
        task = session.get(ReviewTask, facts["task_id"])
        assert task is not None
        rule_version = session.get(RiskRuleBundleVersion, task.rule_bundle_version_id)
        assert rule_version is not None
        analysis_rule_version = RiskRuleBundleVersion(
            id=uuid4(),
            organization_id=task.organization_id,
            bundle_id=rule_version.bundle_id,
            version_no=2,
            status="draft",
            change_note="Phase 10 test version",
            published_by=rule_version.published_by,
        )
        session.add(analysis_rule_version)
        session.flush()
        task.rule_bundle_version_id = analysis_rule_version.id
        template_version = session.get(ClauseTemplateVersion, task.clause_template_version_id)
        assert template_version is not None
        analysis_template_version = ClauseTemplateVersion(
            id=uuid4(),
            organization_id=task.organization_id,
            template_id=template_version.template_id,
            version_no=2,
            status="draft",
            change_note="Phase 10 test version",
            published_by=template_version.published_by,
        )
        session.add(analysis_template_version)
        session.flush()
        task.clause_template_version_id = analysis_template_version.id
        session.add(
            RiskRule(
                id=uuid4(),
                organization_id=task.organization_id,
                bundle_version_id=analysis_rule_version.id,
                rule_key="purchase_keyword",
                risk_type="purchase_keyword",
                engine="deterministic",
                condition_json={
                    "operator": "keyword",
                    "field": "contract_text",
                    "value": "采购合同",
                },
                severity="high",
                suggestion="请复核采购合同风险。",
                enabled=True,
            )
        )
        session.add(
            StandardClause(
                id=uuid4(),
                organization_id=task.organization_id,
                template_version_id=analysis_template_version.id,
                clause_key="payment",
                name="付款",
                standard_text="付款条件应当明确。",
                allowed_deviation="允许按业务约定调整。",
                severity="medium",
                applicability_json={},
                suggestion="请补充付款期限。",
                enabled=True,
                order_no=1,
            )
        )
        session.flush()
        analysis_rule_version.status = "published"
        analysis_template_version.status = "published"
        risk_run = ReviewStageRun(
            id=uuid4(),
            organization_id=task.organization_id,
            review_task_id=task.id,
            stage="risk_analysis",
            attempt_no=1,
            status="running",
            input_fingerprint="f" * 64,
        )
        clause_run = ReviewStageRun(
            id=uuid4(),
            organization_id=task.organization_id,
            review_task_id=task.id,
            stage="clause_comparison",
            attempt_no=1,
            status="running",
            input_fingerprint="1" * 64,
        )
        session.add_all([risk_run, clause_run])
        unit_of_work.commit()
    with session_factory() as session:
        task = session.get(ReviewTask, facts["task_id"])
        risk_run = session.get(ReviewStageRun, risk_run.id)
        clause_run = session.get(ReviewStageRun, clause_run.id)
        assert task is not None and risk_run is not None and clause_run is not None
        return task, risk_run, clause_run


def test_phase10_persists_deduplicated_findings_and_filtered_results(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    task, classification_run, extraction_run = _task_and_runs(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "risk_analysis": [
                FakeResponse(
                    {
                        "findings": [
                            {
                                "risk_type": "purchase_keyword",
                                "severity": "high",
                                "title": "重复风险",
                                "basis": "模型与规则命中了相同风险。",
                                "evidence": [
                                    {
                                        "source_span_id": str(facts["span_id"]),
                                        "quote": "采购合同",
                                    }
                                ],
                            },
                            {
                                "risk_type": "model_only",
                                "severity": "medium",
                                "title": "模型风险",
                                "basis": "模型发现需要复核的事项。",
                                "evidence": [
                                    {
                                        "source_span_id": str(facts["span_id"]),
                                        "quote": "甲方与乙方签订采购合同",
                                    }
                                ],
                            },
                        ],
                        "evidence": [
                            {
                                "source_span_id": str(facts["span_id"]),
                                "quote": "采购合同",
                            }
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
                                "explanation": "缺少付款期限。",
                                "evidence": [
                                    {
                                        "source_span_id": str(facts["span_id"]),
                                        "quote": "采购合同",
                                    }
                                ],
                            }
                        ],
                        "evidence": [
                            {
                                "source_span_id": str(facts["span_id"]),
                                "quote": "采购合同",
                            }
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
        assert (
            session_task is not None
            and session_classification_run is not None
            and session_extraction_run is not None
        )
        from backend.app.modules.reviews.results.service import (
            execute_classification,
            execute_extraction,
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
    task, risk_run, clause_run = _analysis_facts(session_factory, facts)
    with session_factory() as session:
        session_task = session.get(ReviewTask, task.id)
        session_risk_run = session.get(ReviewStageRun, risk_run.id)
        session_clause_run = session.get(ReviewStageRun, clause_run.id)
        assert (
            session_task is not None
            and session_risk_run is not None
            and session_clause_run is not None
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
        execute_risk_analysis(
            session,
            task=session_task,
            stage_run=session_risk_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        payload = get_review_results(
            session,
            organization_id=facts["organization_id"],
            task_id=facts["task_id"],
            viewer_user_id=None,
            risk_severity="high",
            include_evidence=True,
        )
        assert len(gateway.calls) == 4
        assert len(session.scalars(select(RiskFinding)).all()) == 2
        assert len(session.scalars(select(ClauseComparison)).all()) == 1
        findings = list(session.scalars(select(RiskFinding)))
        comparison = session.scalar(select(ClauseComparison))
        assert comparison is not None
        assert any(finding.rule_id is not None for finding in findings)
        assert any(finding.model_call_id is not None for finding in findings)
        assert comparison.standard_clause_id is not None
        assert comparison.model_call_id is not None
        assert len(payload["risk_findings"]) == 1
        assert payload["risk_findings"][0]["evidence"]
        assert payload["summary"]["risk_total"] == 1
        assert payload["summary"]["unresolved_count"] == 2


def test_phase10_rejects_cross_document_evidence_without_persisting_result(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    task, _, _ = _analysis_facts(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "risk_analysis": [
                FakeResponse(
                    {
                        "findings": [
                            {
                                "risk_type": "cross_document",
                                "severity": "high",
                                "title": "非法证据",
                                "basis": "证据不属于当前文档。",
                                "evidence": [
                                    {"source_span_id": str(uuid4()), "quote": "采购合同"}
                                ],
                            }
                        ],
                        "evidence": [],
                    }
                )
            ]
        }
    )
    with session_factory() as session:
        session_task = session.get(ReviewTask, task.id)
        risk_run = session.scalar(
            select(ReviewStageRun).where(
                ReviewStageRun.review_task_id == task.id,
                ReviewStageRun.stage == "risk_analysis",
            )
        )
        assert session_task is not None and risk_run is not None
        with pytest.raises(ResultExecutionError) as error_info:
            execute_risk_analysis(
                session,
                task=session_task,
                stage_run=risk_run,
                gateway=gateway,
                heartbeat=lambda: None,
            )
        assert error_info.value.code == "MODEL_EVIDENCE_INVALID"
        assert session.scalar(select(RiskFinding)) is None


def test_phase10_allows_missing_clause_without_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    task, _, clause_run = _analysis_facts(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "clause_comparison": [
                FakeResponse(
                    {
                        "comparisons": [
                            {
                                "clause_key": "payment",
                                "result": "missing",
                                "explanation": "未找到付款条款。",
                                "evidence": [],
                            }
                        ],
                        "evidence": [],
                    }
                )
            ]
        }
    )
    with session_factory() as session:
        session_task = session.get(ReviewTask, task.id)
        session_clause_run = session.get(ReviewStageRun, clause_run.id)
        assert session_task is not None and session_clause_run is not None
        execute_clause_comparison(
            session,
            task=session_task,
            stage_run=session_clause_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        comparison = session.scalar(select(ClauseComparison))
        assert comparison is not None
        assert comparison.status == "missing"
        assert comparison.evidence_span_id is None
        assert session.scalar(select(ClauseComparisonEvidence.source_span_id)) is None


def test_phase10_preserves_uncertain_clause_status(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    task, _, clause_run = _analysis_facts(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "clause_comparison": [
                FakeResponse(
                    {
                        "comparisons": [
                            {
                                "clause_key": "payment",
                                "result": "uncertain",
                                "explanation": "原文不足以判断付款条件。",
                                "evidence": [
                                    {
                                        "source_span_id": str(facts["span_id"]),
                                        "quote": "采购合同",
                                    }
                                ],
                            }
                        ],
                        "evidence": [
                            {
                                "source_span_id": str(facts["span_id"]),
                                "quote": "采购合同",
                            }
                        ],
                    }
                )
            ]
        }
    )
    with session_factory() as session:
        session_task = session.get(ReviewTask, task.id)
        session_clause_run = session.get(ReviewStageRun, clause_run.id)
        assert session_task is not None and session_clause_run is not None
        execute_clause_comparison(
            session,
            task=session_task,
            stage_run=session_clause_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        comparison = session.scalar(select(ClauseComparison))
        assert comparison is not None and comparison.status == "uncertain"


def test_phase10_reuses_successful_empty_risk_stage(
    session_factory: sessionmaker[Session],
) -> None:
    facts = _seed(session_factory)
    task, _, _ = _analysis_facts(session_factory, facts)
    gateway = FakeModelGateway(
        fixtures={
            "risk_analysis": [
                FakeResponse({"findings": [], "evidence": []}),
            ]
        }
    )
    with session_factory() as session:
        session_task = session.get(ReviewTask, task.id)
        risk_run = session.scalar(
            select(ReviewStageRun).where(
                ReviewStageRun.review_task_id == task.id,
                ReviewStageRun.stage == "risk_analysis",
            )
        )
        rule_version = session.get(RiskRuleBundleVersion, task.rule_bundle_version_id)
        assert session_task is not None and risk_run is not None and rule_version is not None
        empty_rule_version = RiskRuleBundleVersion(
            id=uuid4(),
            organization_id=task.organization_id,
            bundle_id=rule_version.bundle_id,
            version_no=3,
            status="published",
            change_note="Phase 10 empty rule version",
            published_by=rule_version.published_by,
        )
        session.add(empty_rule_version)
        session.flush()
        session_task.rule_bundle_version_id = empty_rule_version.id
        session.commit()
        execute_risk_analysis(
            session,
            task=session_task,
            stage_run=risk_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )
        risk_run.status = "succeeded"
        retry_run = ReviewStageRun(
            id=uuid4(),
            organization_id=task.organization_id,
            review_task_id=task.id,
            stage="risk_analysis",
            attempt_no=2,
            status="running",
            input_fingerprint="2" * 64,
        )
        session.add(retry_run)
        session.commit()
        execute_risk_analysis(
            session,
            task=session_task,
            stage_run=retry_run,
            gateway=gateway,
            heartbeat=lambda: None,
        )

        assert gateway.calls == [("risk_analysis", False)]
        assert session.scalars(select(RiskFinding)).all() == []
