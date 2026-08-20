import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from backend.app.integrations.model.gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelInvocationResult,
)
from backend.app.integrations.model.schemas import (
    ClassificationRequest,
    ClassificationResult,
    ClauseComparisonRequest,
    ExtractionRequest,
    ExtractionResult,
    RiskAnalysisRequest,
)
from backend.app.integrations.model.schemas import (
    ClauseComparisonResult as ModelClauseComparisonResult,
)
from backend.app.integrations.model.schemas import ExtractedField as ModelExtractedField
from backend.app.integrations.model.schemas import (
    RiskAnalysisResult as ModelRiskAnalysisResult,
)
from backend.app.modules.clauses.templates.models import StandardClause
from backend.app.modules.contracts.models import ContractAccessGrant
from backend.app.modules.documents.models import (
    DocumentBlock,
    DocumentPage,
    DocumentVersion,
    SourceSpan,
)
from backend.app.modules.reviews.models import ModelCall, ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import (
    CONTRACT_CATEGORIES,
    CORE_EXTRACTED_FIELD_KEYS,
    ClauseComparisonEvidence,
    ContractClassification,
    ContractClassificationEvidence,
    ExtractedField,
    ExtractedFieldEvidence,
    RiskFinding,
    RiskFindingEvidence,
)
from backend.app.modules.reviews.results.models import (
    ClauseComparison as ClauseComparisonRow,
)
from backend.app.modules.risks.rules.models import RiskRule
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError
from backend.app.shared.model_telemetry import (
    ModelCallContext,
    model_fingerprint,
    model_request_fingerprint,
    persist_invocation,
)


class ResultExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DocumentInput:
    document: DocumentVersion
    text: str
    spans: dict[UUID, SourceSpan]


def _canonical_fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _load_document_input(session: Session, task: ReviewTask) -> DocumentInput:
    if task.document_version_id is None:
        raise ResultExecutionError("DOCUMENT_NOT_READY", "文档尚未解析完成。")
    document = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.organization_id == task.organization_id,
            DocumentVersion.id == task.document_version_id,
            DocumentVersion.status == "succeeded",
        )
    )
    if document is None:
        raise ResultExecutionError("DOCUMENT_NOT_READY", "文档尚未解析完成。")
    blocks = list(
        session.scalars(
            select(DocumentBlock)
            .where(
                DocumentBlock.organization_id == task.organization_id,
                DocumentBlock.document_version_id == document.id,
            )
            .order_by(DocumentBlock.order_no)
        )
    )
    spans = list(
        session.scalars(
            select(SourceSpan)
            .where(
                SourceSpan.organization_id == task.organization_id,
                SourceSpan.document_version_id == document.id,
            )
            .order_by(SourceSpan.created_at, SourceSpan.id)
        )
    )
    text = "\n".join(block.text for block in blocks)
    if not text or not spans:
        raise ResultExecutionError("DOCUMENT_NOT_READY", "文档没有可用的文本证据。")
    if len(text) > 5_000_000:
        raise ResultExecutionError("MODEL_INPUT_TOO_LARGE", "合同内容超过模型输入限制。")
    return DocumentInput(document=document, text=text, spans={span.id: span for span in spans})


def _request_context(document_input: DocumentInput) -> dict[str, str]:
    first_span = next(iter(document_input.spans.values()))
    return {
        "document_version_id": str(document_input.document.id),
        "source_span_id": str(first_span.id),
        "source_quote": first_span.quote,
    }


def _model_fingerprint_for(gateway: ModelGateway, request: Any) -> str:
    return model_fingerprint(
        provider=gateway.provider,
        model=gateway.model,
        prompt_version=request.prompt_version,
        schema_version=request.schema_version,
    )


def _has_reusable_empty_stage(
    session: Session,
    *,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    capability: str,
    input_fingerprint: str,
    model_fingerprint_value: str,
) -> bool:
    """Reuse a completed analysis whose valid output contained no rows."""
    return (
        session.scalar(
            select(ReviewStageRun.id)
            .join(
                ModelCall,
                and_(
                    ModelCall.organization_id == ReviewStageRun.organization_id,
                    ModelCall.review_task_id == ReviewStageRun.review_task_id,
                    ModelCall.stage_run_id == ReviewStageRun.id,
                ),
            )
            .where(
                ReviewStageRun.organization_id == task.organization_id,
                ReviewStageRun.review_task_id == task.id,
                ReviewStageRun.id != stage_run.id,
                ReviewStageRun.stage == stage_run.stage,
                ReviewStageRun.status == "succeeded",
                ReviewStageRun.input_fingerprint == input_fingerprint,
                ModelCall.capability == capability,
                ModelCall.status == "succeeded",
                ModelCall.model_fingerprint == model_fingerprint_value,
            )
            .limit(1)
        )
        is not None
    )


def _persist_telemetry(
    session: Session,
    invocation: tuple[Any, ...],
    *,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    capability: str,
) -> None:
    if not invocation:
        return
    with UnitOfWork(session) as unit_of_work:
        persist_invocation(
            session,
            invocation,
            context=ModelCallContext(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=stage_run.id,
                capability=capability,
            ),
        )
        unit_of_work.commit()


def _invoke_or_fail(
    gateway: ModelGateway,
    request: Any,
    *,
    capability: str,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    session: Session,
) -> ModelInvocationResult[Any]:
    invocation: ModelInvocationResult[Any]
    try:
        if capability == "classification":
            invocation = gateway.classify(
                request,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability=capability,
                ),
            )
        elif capability == "extraction":
            invocation = gateway.extract(
                request,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability=capability,
                ),
            )
        elif capability == "risk_analysis":
            invocation = gateway.analyze_risk(
                request,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability=capability,
                ),
            )
        elif capability == "clause_comparison":
            invocation = gateway.compare_clauses(
                request,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability=capability,
                ),
            )
        else:
            raise ResultExecutionError("MODEL_CAPABILITY_INVALID", "模型能力不受支持。")
    except ModelGatewayError as exc:
        _persist_telemetry(
            session,
            exc.telemetry,
            task=task,
            stage_run=stage_run,
            capability=capability,
        )
        raise ResultExecutionError(exc.code, "模型处理失败，请重试。") from None
    return invocation


def _source_span_ids(
    evidence: list[Any],
    *,
    document_input: DocumentInput,
    required: bool,
) -> list[UUID]:
    if required and not evidence:
        raise ResultExecutionError("MODEL_EVIDENCE_MISSING", "模型结果缺少合法证据。")
    ids: list[UUID] = []
    for item in evidence:
        try:
            span_id = UUID(item.source_span_id)
        except (TypeError, ValueError):
            raise ResultExecutionError(
                "MODEL_EVIDENCE_INVALID", "模型结果包含无效证据定位。"
            ) from None
        span = document_input.spans.get(span_id)
        if span is None:
            raise ResultExecutionError(
                "MODEL_EVIDENCE_INVALID", "模型结果包含不属于当前文档的证据。"
            )
        quote = item.quote.strip()
        if not quote or quote not in span.quote:
            raise ResultExecutionError("MODEL_EVIDENCE_INVALID", "模型证据引用与原文定位不匹配。")
        if span_id not in ids:
            ids.append(span_id)
    if required and not ids:
        raise ResultExecutionError("MODEL_EVIDENCE_MISSING", "模型结果缺少合法证据。")
    return ids


def _replace_classification_evidence(
    session: Session,
    *,
    classification: ContractClassification,
    document_version_id: UUID,
    span_ids: list[UUID],
) -> None:
    session.execute(
        delete(ContractClassificationEvidence).where(
            ContractClassificationEvidence.organization_id == classification.organization_id,
            ContractClassificationEvidence.classification_id == classification.id,
        )
    )
    for position_no, span_id in enumerate(span_ids):
        session.add(
            ContractClassificationEvidence(
                organization_id=classification.organization_id,
                classification_id=classification.id,
                document_version_id=document_version_id,
                source_span_id=span_id,
                position_no=position_no,
                is_primary=position_no == 0,
            )
        )
    classification.evidence_span_id = span_ids[0]
    classification.document_version_id = document_version_id


def execute_classification(
    session: Session,
    *,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    gateway: ModelGateway,
    heartbeat: Any,
) -> None:
    document_input = _load_document_input(session, task)
    request = ClassificationRequest(
        input_text=document_input.text,
        input_version=f"document-{document_input.document.parse_fingerprint}",
        context=_request_context(document_input),
    )
    input_fingerprint = model_request_fingerprint(request, capability="classification")
    gateway_model_fingerprint = _model_fingerprint_for(gateway, request)
    existing = session.scalar(
        select(ContractClassification).where(
            ContractClassification.organization_id == task.organization_id,
            ContractClassification.review_task_id == task.id,
        )
    )
    session.commit()
    if (
        existing is not None
        and existing.input_fingerprint == input_fingerprint
        and existing.model_fingerprint == gateway_model_fingerprint
    ):
        with UnitOfWork(session) as unit_of_work:
            existing.stage_run_id = stage_run.id
            unit_of_work.commit()
        return
    heartbeat()

    invocation: ModelInvocationResult[Any] = _invoke_or_fail(
        gateway,
        request,
        capability="classification",
        task=task,
        stage_run=stage_run,
        session=session,
    )
    try:
        output: ClassificationResult = invocation.output
        if output.category not in CONTRACT_CATEGORIES:
            raise ResultExecutionError("MODEL_CATEGORY_INVALID", "模型返回了不支持的合同分类。")
        span_ids = _source_span_ids(output.evidence, document_input=document_input, required=True)
    except ResultExecutionError:
        _persist_telemetry(
            session,
            invocation.telemetry,
            task=task,
            stage_run=stage_run,
            capability="classification",
        )
        raise
    result_fingerprint = _canonical_fingerprint(
        {
            "capability": "classification",
            "input": input_fingerprint,
            "model": gateway_model_fingerprint,
            "output": output.model_dump(mode="json"),
        }
    )
    with UnitOfWork(session) as unit_of_work:
        persist_invocation(
            session,
            invocation.telemetry,
            context=ModelCallContext(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=stage_run.id,
                capability="classification",
            ),
        )
        if existing is None:
            existing = ContractClassification(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=stage_run.id,
                document_version_id=document_input.document.id,
                evidence_span_id=span_ids[0],
                model_value=output.category,
                current_value=output.category,
                confidence=output.confidence,
                status="detected",
                input_fingerprint=input_fingerprint,
                model_fingerprint=gateway_model_fingerprint,
                result_fingerprint=result_fingerprint,
            )
            session.add(existing)
            session.flush()
        else:
            existing.stage_run_id = stage_run.id
            existing.model_value = output.category
            if existing.status not in {"confirmed", "corrected"}:
                existing.current_value = output.category
                existing.status = "detected"
            existing.confidence = output.confidence
            existing.input_fingerprint = input_fingerprint
            existing.model_fingerprint = gateway_model_fingerprint
            existing.result_fingerprint = result_fingerprint
        _replace_classification_evidence(
            session,
            classification=existing,
            document_version_id=document_input.document.id,
            span_ids=span_ids,
        )
        unit_of_work.commit()
    heartbeat()


def _replace_field_evidence(
    session: Session,
    *,
    field: ExtractedField,
    document_version_id: UUID,
    span_ids: list[UUID],
) -> None:
    session.execute(
        delete(ExtractedFieldEvidence).where(
            ExtractedFieldEvidence.organization_id == field.organization_id,
            ExtractedFieldEvidence.extracted_field_id == field.id,
        )
    )
    for position_no, span_id in enumerate(span_ids):
        session.add(
            ExtractedFieldEvidence(
                organization_id=field.organization_id,
                extracted_field_id=field.id,
                document_version_id=document_version_id,
                source_span_id=span_id,
                position_no=position_no,
                is_primary=position_no == 0,
            )
        )
    field.evidence_span_id = span_ids[0] if span_ids else None


def _validate_extracted_fields(
    output: ExtractionResult,
    *,
    document_input: DocumentInput,
) -> dict[str, tuple[ModelExtractedField, list[UUID]]]:
    fields = {field.field_key: field for field in output.fields}
    if len(fields) != len(output.fields):
        raise ResultExecutionError("MODEL_FIELDS_DUPLICATED", "模型结果包含重复抽取字段。")
    unknown = set(fields) - set(CORE_EXTRACTED_FIELD_KEYS)
    if unknown:
        raise ResultExecutionError("MODEL_FIELDS_UNKNOWN", "模型结果包含不支持的抽取字段。")
    missing = set(CORE_EXTRACTED_FIELD_KEYS) - set(fields)
    if missing:
        raise ResultExecutionError("MODEL_FIELDS_INCOMPLETE", "模型结果未覆盖全部核心抽取字段。")
    validated: dict[str, tuple[ModelExtractedField, list[UUID]]] = {}
    for field in fields.values():
        span_ids = _source_span_ids(
            field.evidence,
            document_input=document_input,
            required=field.value is not None,
        )
        validated[field.field_key] = (field, span_ids)
    return validated


def execute_extraction(
    session: Session,
    *,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    gateway: ModelGateway,
    heartbeat: Any,
) -> None:
    document_input = _load_document_input(session, task)
    request = ExtractionRequest(
        input_text=document_input.text,
        input_version=f"document-{document_input.document.parse_fingerprint}",
        context=_request_context(document_input),
    )
    input_fingerprint = model_request_fingerprint(request, capability="extraction")
    gateway_model_fingerprint = _model_fingerprint_for(gateway, request)
    existing_fields = {
        existing_field.field_key: existing_field
        for existing_field in session.scalars(
            select(ExtractedField).where(
                ExtractedField.organization_id == task.organization_id,
                ExtractedField.review_task_id == task.id,
            )
        )
    }
    session.commit()
    if len(existing_fields) == len(CORE_EXTRACTED_FIELD_KEYS) and all(
        existing_row.input_fingerprint == input_fingerprint
        and existing_row.model_fingerprint == gateway_model_fingerprint
        for existing_row in existing_fields.values()
    ):
        with UnitOfWork(session) as unit_of_work:
            for existing_row in existing_fields.values():
                existing_row.stage_run_id = stage_run.id
            unit_of_work.commit()
        return
    heartbeat()


    invocation: ModelInvocationResult[Any] = _invoke_or_fail(
        gateway,
        request,
        capability="extraction",
        task=task,
        stage_run=stage_run,
        session=session,
    )
    try:
        output: ExtractionResult = invocation.output
        validated = _validate_extracted_fields(output, document_input=document_input)
    except ResultExecutionError:
        _persist_telemetry(
            session,
            invocation.telemetry,
            task=task,
            stage_run=stage_run,
            capability="extraction",
        )
        raise
    with UnitOfWork(session) as unit_of_work:
        persist_invocation(
            session,
            invocation.telemetry,
            context=ModelCallContext(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=stage_run.id,
                capability="extraction",
            ),
        )
        for field_key in CORE_EXTRACTED_FIELD_KEYS:
            model_field, span_ids = validated[field_key]
            result_fingerprint = _canonical_fingerprint(
                {
                    "capability": "extraction",
                    "field_key": field_key,
                    "input": input_fingerprint,
                    "model": gateway_model_fingerprint,
                    "field": model_field.model_dump(mode="json"),
                }
            )
            field: ExtractedField | None = existing_fields.get(field_key)
            if field is None:
                field = ExtractedField(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    document_version_id=document_input.document.id,
                    evidence_span_id=span_ids[0] if span_ids else None,
                    field_key=field_key,
                    model_value_json=model_field.value,
                    current_value_json=model_field.value,
                    confidence=model_field.confidence,
                    status="not_found" if model_field.value is None else "detected",
                    input_fingerprint=input_fingerprint,
                    model_fingerprint=gateway_model_fingerprint,
                    result_fingerprint=result_fingerprint,
                )
                session.add(field)
                session.flush()
            else:
                field.stage_run_id = stage_run.id
                field.document_version_id = document_input.document.id
                field.model_value_json = model_field.value
                if field.status not in {"confirmed", "corrected"}:
                    field.current_value_json = model_field.value
                    field.status = "not_found" if model_field.value is None else "detected"
                field.confidence = model_field.confidence
                field.input_fingerprint = input_fingerprint
                field.model_fingerprint = gateway_model_fingerprint
                field.result_fingerprint = result_fingerprint
            assert field is not None
            _replace_field_evidence(
                session,
                field=field,
                document_version_id=document_input.document.id,
                span_ids=span_ids,
            )
        unit_of_work.commit()
    heartbeat()


def _field_context(
    session: Session, *, task: ReviewTask
) -> tuple[dict[str, Any], dict[str, list[UUID]]]:
    fields = list(
        session.scalars(
            select(ExtractedField).where(
                ExtractedField.organization_id == task.organization_id,
                ExtractedField.review_task_id == task.id,
            )
        )
    )
    values = {field.field_key: field.current_value_json for field in fields}
    evidence: dict[str, list[UUID]] = {}
    for field in fields:
        evidence[field.field_key] = [
            row.source_span_id
            for row in session.scalars(
                select(ExtractedFieldEvidence)
                .where(
                    ExtractedFieldEvidence.organization_id == task.organization_id,
                    ExtractedFieldEvidence.extracted_field_id == field.id,
                )
                .order_by(ExtractedFieldEvidence.position_no)
            )
        ]
    return values, evidence


def _presence_keywords(field: str) -> tuple[str, ...]:
    return {
        "acceptance_standard": ("验收",),
        "intellectual_property": ("知识产权", "著作权", "专利"),
        "data_compliance": ("数据合规", "个人信息", "数据保护"),
        "force_majeure": ("不可抗力",),
    }.get(field, ())


def _condition_value(
    condition: dict[str, Any],
    *,
    text: str,
    values: dict[str, Any],
    evidence: dict[str, list[UUID]],
    first_span: UUID,
) -> tuple[bool, list[UUID]]:
    operator = condition.get("operator")
    if operator == "keyword":
        keyword_value = str(condition.get("value", ""))
        matched = keyword_value in text
        return matched, [first_span] if matched else []
    if operator == "regex":
        try:
            matched = re.search(
                str(condition.get("pattern", "")), text, flags=re.DOTALL
            ) is not None
        except re.error:
            matched = False
        return matched, [first_span] if matched else []
    if operator in {"field_exists", "field_missing"}:
        field = str(condition.get("field"))
        field_value = values.get(field)
        if field in values:
            present = field_value is not None
            field_evidence = evidence.get(field, [])
        else:
            keywords = _presence_keywords(field)
            present = any(keyword in text for keyword in keywords)
            field_evidence = [first_span] if present else []
        matched = present if operator == "field_exists" else not present
        return matched, field_evidence or ([first_span] if matched else [])
    if operator in {"amount_threshold", "date_threshold"}:
        field = str(condition.get("field"))
        raw = values.get(field)
        raw_value: Any = raw.get("amount") if isinstance(raw, dict) else raw
        if operator == "amount_threshold":
            try:
                left_amount = Decimal(str(raw_value))
                right_amount = Decimal(str(condition.get("value")))
            except (InvalidOperation, TypeError, ValueError):
                return False, []
        else:
            try:
                left_date = date.fromisoformat(str(raw_value))
                right_date = date.fromisoformat(str(condition.get("value")))
            except (TypeError, ValueError):
                return False, []
        comparison = str(condition.get("comparison", ""))
        if operator == "amount_threshold":
            matched = {
                "gt": left_amount > right_amount,
                "gte": left_amount >= right_amount,
                "lt": left_amount < right_amount,
                "lte": left_amount <= right_amount,
                "eq": left_amount == right_amount,
            }.get(comparison, False)
        else:
            matched = {
                "gt": left_date > right_date,
                "gte": left_date >= right_date,
                "lt": left_date < right_date,
                "lte": left_date <= right_date,
                "eq": left_date == right_date,
            }.get(comparison, False)
        return matched, evidence.get(field, []) or ([first_span] if matched else [])
    if operator in {"all", "any"}:
        results = [
            _condition_value(
                child,
                text=text,
                values=values,
                evidence=evidence,
                first_span=first_span,
            )
            for child in condition.get("conditions", [])
        ]
        matched = (
            all(item[0] for item in results)
            if operator == "all"
            else any(item[0] for item in results)
        )
        span_ids: list[UUID] = []
        for item_matched, item_spans in results:
            if item_matched:
                for span_id in item_spans:
                    if span_id not in span_ids:
                        span_ids.append(span_id)
        return matched, span_ids
    if operator == "not":
        matched, _ = _condition_value(
            condition.get("condition", {}),
            text=text,
            values=values,
            evidence=evidence,
            first_span=first_span,
        )
        return not matched, [first_span] if not matched else []
    return False, []


def _risk_input_fingerprint(
    document_input: DocumentInput, *, task: ReviewTask, values: dict[str, Any]
) -> str:
    return _canonical_fingerprint(
        {
            "document_parse_fingerprint": document_input.document.parse_fingerprint,
            "rule_bundle_version_id": str(task.rule_bundle_version_id),
            "fields": values,
        }
    )


def _replace_risk_evidence(
    session: Session, *, finding: RiskFinding, document_version_id: UUID, span_ids: list[UUID]
) -> None:
    session.execute(
        delete(RiskFindingEvidence).where(
            RiskFindingEvidence.organization_id == finding.organization_id,
            RiskFindingEvidence.finding_id == finding.id,
        )
    )
    for position_no, span_id in enumerate(span_ids):
        session.add(
            RiskFindingEvidence(
                organization_id=finding.organization_id,
                finding_id=finding.id,
                document_version_id=document_version_id,
                source_span_id=span_id,
                position_no=position_no,
            )
        )
    finding.evidence_span_id = span_ids[0] if span_ids else None


def _replace_clause_evidence(
    session: Session,
    *,
    comparison: ClauseComparisonRow,
    document_version_id: UUID,
    span_ids: list[UUID],
) -> None:
    session.execute(
        delete(ClauseComparisonEvidence).where(
            ClauseComparisonEvidence.organization_id == comparison.organization_id,
            ClauseComparisonEvidence.comparison_id == comparison.id,
        )
    )
    for position_no, span_id in enumerate(span_ids):
        session.add(
            ClauseComparisonEvidence(
                organization_id=comparison.organization_id,
                comparison_id=comparison.id,
                document_version_id=document_version_id,
                source_span_id=span_id,
                position_no=position_no,
            )
        )
    comparison.evidence_span_id = span_ids[0] if span_ids else None


def execute_risk_analysis(
    session: Session,
    *,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    gateway: ModelGateway,
    heartbeat: Any,
) -> None:
    document_input = _load_document_input(session, task)
    values, field_evidence = _field_context(session, task=task)
    rules = list(
        session.scalars(
            select(RiskRule)
            .where(
                RiskRule.organization_id == task.organization_id,
                RiskRule.bundle_version_id == task.rule_bundle_version_id,
                RiskRule.enabled.is_(True),
            )
            .order_by(RiskRule.rule_key, RiskRule.id)
        )
    )
    input_fingerprint = _risk_input_fingerprint(document_input, task=task, values=values)
    request = RiskAnalysisRequest(
        input_text=document_input.text,
        input_version=f"document-{document_input.document.parse_fingerprint}",
        context={
            **_request_context(document_input),
            "rule_bundle_version_id": str(task.rule_bundle_version_id),
        },
    )
    model_fp = _model_fingerprint_for(gateway, request)
    existing = list(
        session.scalars(
            select(RiskFinding).where(
                RiskFinding.organization_id == task.organization_id,
                RiskFinding.review_task_id == task.id,
            )
        )
    )
    stage_run.input_fingerprint = input_fingerprint
    reusable_empty = _has_reusable_empty_stage(
        session,
        task=task,
        stage_run=stage_run,
        capability="risk_analysis",
        input_fingerprint=input_fingerprint,
        model_fingerprint_value=model_fp,
    ) if not existing else False
    session.commit()
    if reusable_empty:
        return
    if existing and all(
        row.input_fingerprint == input_fingerprint and row.model_fingerprint == model_fp
        for row in existing
    ):
        with UnitOfWork(session) as unit_of_work:
            for row in existing:
                row.stage_run_id = stage_run.id
            unit_of_work.commit()
        return

    heartbeat()
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    first_span = next(iter(document_input.spans))
    for rule in rules:
        if rule.engine != "deterministic":
            continue
        matched, span_ids = _condition_value(
            rule.condition_json,
            text=document_input.text,
            values=values,
            evidence=field_evidence,
            first_span=first_span,
        )
        if not matched:
            continue
        if not span_ids:
            span_ids = [first_span]
        key = (rule.risk_type, rule.rule_key)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "risk_type": rule.risk_type,
                "severity": rule.severity,
                "title": rule.risk_type,
                "description": rule.suggestion,
                "basis": f"规则 {rule.rule_key} 命中合同文本或结构化字段。",
                "suggestion": rule.suggestion,
                "confidence": 1.0,
                "source": "rule",
                "rule_key": rule.rule_key,
                "rule_id": rule.id,
                "model_call_id": None,
                "span_ids": span_ids,
            }
        )

    invocation: ModelInvocationResult[Any] | None = None
    try:
        invocation = _invoke_or_fail(
            gateway,
            request,
            capability="risk_analysis",
            task=task,
            stage_run=stage_run,
            session=session,
        )
        output: ModelRiskAnalysisResult = invocation.output
        for item in output.findings:
            span_ids = _source_span_ids(item.evidence, document_input=document_input, required=True)
            key = (item.risk_type, item.title)
            if any(existing_key[0] == item.risk_type for existing_key in seen):
                continue
            seen.add(key)
            findings.append(
                {
                    "risk_type": item.risk_type,
                    "severity": item.severity,
                    "title": item.title,
                    "description": item.basis,
                    "basis": item.basis,
                    "suggestion": "请结合原文和组织政策复核该风险。",
                    "confidence": 0.5,
            "source": "model",
            "rule_key": None,
            "rule_id": None,
            "model_call_id": None,
            "span_ids": span_ids,
                }
            )
    except ResultExecutionError:
        if invocation is not None:
            _persist_telemetry(
                session,
                invocation.telemetry,
                task=task,
                stage_run=stage_run,
                capability="risk_analysis",
            )
        raise

    with UnitOfWork(session) as unit_of_work:
        model_call_id: UUID | None = None
        if invocation is not None:
            model_calls = persist_invocation(
                session,
                invocation.telemetry,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability="risk_analysis",
                ),
            )
            session.flush()
            model_call_id = next(
                (
                    model_call.id
                    for model_call in reversed(model_calls)
                    if model_call.status == "succeeded"
                ),
                None,
            )
        session.execute(
            delete(RiskFinding).where(
                RiskFinding.organization_id == task.organization_id,
                RiskFinding.review_task_id == task.id,
            )
        )
        for finding_data in findings:
            result_fingerprint = _canonical_fingerprint(
                {
                    "capability": "risk_analysis",
                    "input": input_fingerprint,
                    "model": model_fp,
                    "finding": {
                        key: value
                        for key, value in finding_data.items()
                        if key != "span_ids"
                    },
                }
            )
            row = RiskFinding(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=stage_run.id,
                rule_id=finding_data["rule_id"],
                model_call_id=(
                    model_call_id if finding_data["source"] == "model" else None
                ),
                document_version_id=document_input.document.id,
                rule_key=finding_data["rule_key"],
                risk_type=finding_data["risk_type"],
                severity=finding_data["severity"],
                title=finding_data["title"],
                description=finding_data["description"],
                basis=finding_data["basis"],
                suggestion=finding_data["suggestion"],
                confidence=finding_data["confidence"],
                source=finding_data["source"],
                status="pending_review",
                input_fingerprint=input_fingerprint,
                model_fingerprint=model_fp,
                result_fingerprint=result_fingerprint,
            )
            session.add(row)
            session.flush()
            _replace_risk_evidence(
                session,
                finding=row,
                document_version_id=document_input.document.id,
                span_ids=finding_data["span_ids"],
            )
        unit_of_work.commit()
    heartbeat()


def execute_clause_comparison(
    session: Session,
    *,
    task: ReviewTask,
    stage_run: ReviewStageRun,
    gateway: ModelGateway,
    heartbeat: Any,
) -> None:
    document_input = _load_document_input(session, task)
    clauses = list(
        session.scalars(
            select(StandardClause)
            .where(
                StandardClause.organization_id == task.organization_id,
                StandardClause.template_version_id == task.clause_template_version_id,
                StandardClause.enabled.is_(True),
            )
            .order_by(StandardClause.order_no, StandardClause.id)
        )
    )
    clause_by_key = {clause.clause_key: clause for clause in clauses}
    input_fingerprint = _canonical_fingerprint(
        {
            "document_parse_fingerprint": document_input.document.parse_fingerprint,
            "clause_template_version_id": str(task.clause_template_version_id),
        }
    )
    request = ClauseComparisonRequest(
        input_text=document_input.text,
        input_version=f"document-{document_input.document.parse_fingerprint}",
        context={
            **_request_context(document_input),
            "clause_template_version_id": str(task.clause_template_version_id),
        },
    )
    model_fp = _model_fingerprint_for(gateway, request)
    existing = list(
        session.scalars(
            select(ClauseComparisonRow).where(
                ClauseComparisonRow.organization_id == task.organization_id,
                ClauseComparisonRow.review_task_id == task.id,
            )
        )
    )
    stage_run.input_fingerprint = input_fingerprint
    reusable_empty = _has_reusable_empty_stage(
        session,
        task=task,
        stage_run=stage_run,
        capability="clause_comparison",
        input_fingerprint=input_fingerprint,
        model_fingerprint_value=model_fp,
    ) if not existing else False
    session.commit()
    if reusable_empty:
        return
    if existing and all(
        row.input_fingerprint == input_fingerprint and row.model_fingerprint == model_fp
        for row in existing
    ):
        with UnitOfWork(session) as unit_of_work:
            for row in existing:
                row.stage_run_id = stage_run.id
            unit_of_work.commit()
        return

    heartbeat()
    invocation: ModelInvocationResult[Any] | None = None
    comparisons: list[dict[str, Any]] = []
    try:
        invocation = _invoke_or_fail(
            gateway,
            request,
            capability="clause_comparison",
            task=task,
            stage_run=stage_run,
            session=session,
        )
        output: ModelClauseComparisonResult = invocation.output
        seen: set[str] = set()
        for item in output.comparisons:
            if item.clause_key not in clause_by_key:
                if item.result == "not_applicable":
                    continue
                raise ResultExecutionError("MODEL_CLAUSE_UNKNOWN", "模型返回了未配置的条款。")
            if item.clause_key in seen:
                raise ResultExecutionError(
                    "MODEL_CLAUSE_DUPLICATED", "模型返回了重复条款比对结果。"
                )
            seen.add(item.clause_key)
            if item.result == "not_applicable":
                continue
            status = {
                "match": "matched",
                "deviation": "deviated",
                "missing": "missing",
                "uncertain": "uncertain",
            }.get(item.result)
            if status is None:
                raise ResultExecutionError(
                    "MODEL_CLAUSE_STATUS_INVALID", "模型返回了不支持的条款状态。"
                )
            span_ids = _source_span_ids(
                item.evidence,
                document_input=document_input,
                required=status != "missing",
            )
            clause = clause_by_key[item.clause_key]
            comparisons.append(
                {
                    "clause_key": item.clause_key,
                    "standard_clause_id": clause.id,
                    "status": status,
                    "contract_text": document_input.spans[span_ids[0]].quote if span_ids else None,
                    "difference_summary": item.explanation,
                    "severity": clause.severity,
                    "suggestion": clause.suggestion,
                    "confidence": 0.5,
                    "span_ids": span_ids,
                }
            )
    except ResultExecutionError:
        if invocation is not None:
            _persist_telemetry(
                session,
                invocation.telemetry,
                task=task,
                stage_run=stage_run,
                capability="clause_comparison",
            )
        raise

    with UnitOfWork(session) as unit_of_work:
        model_call_id: UUID | None = None
        if invocation is not None:
            model_calls = persist_invocation(
                session,
                invocation.telemetry,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability="clause_comparison",
                ),
            )
            session.flush()
            model_call_id = next(
                (
                    model_call.id
                    for model_call in reversed(model_calls)
                    if model_call.status == "succeeded"
                ),
                None,
            )
        session.execute(
            delete(ClauseComparisonRow).where(
                ClauseComparisonRow.organization_id == task.organization_id,
                ClauseComparisonRow.review_task_id == task.id,
            )
        )
        for comparison_data in comparisons:
            result_fingerprint = _canonical_fingerprint(
                {
                    "capability": "clause_comparison",
                    "input": input_fingerprint,
                    "model": model_fp,
                    "comparison": {
                        key: value for key, value in comparison_data.items() if key != "span_ids"
                    },
                }
            )
            row = ClauseComparisonRow(
                organization_id=task.organization_id,
                review_task_id=task.id,
                stage_run_id=stage_run.id,
                standard_clause_id=comparison_data["standard_clause_id"],
                model_call_id=model_call_id,
                document_version_id=document_input.document.id,
                clause_key=comparison_data["clause_key"],
                status=comparison_data["status"],
                contract_text=comparison_data["contract_text"],
                difference_summary=comparison_data["difference_summary"],
                severity=comparison_data["severity"],
                suggestion=comparison_data["suggestion"],
                confidence=comparison_data["confidence"],
                input_fingerprint=input_fingerprint,
                model_fingerprint=model_fp,
                result_fingerprint=result_fingerprint,
            )
            session.add(row)
            session.flush()
            _replace_clause_evidence(
                session,
                comparison=row,
                document_version_id=document_input.document.id,
                span_ids=comparison_data["span_ids"],
            )
        unit_of_work.commit()
    heartbeat()


def _results_not_ready() -> ApplicationError:
    return ApplicationError(
        status_code=409,
        code="RESULTS_NOT_READY",
        message="分类和字段抽取结果尚未准备完成。",
    )


def _source_locator_payload(
    session: Session,
    *,
    organization_id: UUID,
    document: DocumentVersion,
    source_span_id: UUID,
) -> dict[str, Any]:
    row = session.execute(
        select(SourceSpan, DocumentBlock, DocumentPage.page_no)
        .outerjoin(
            DocumentBlock,
            and_(
                DocumentBlock.organization_id == SourceSpan.organization_id,
                DocumentBlock.id == SourceSpan.block_id,
            ),
        )
        .outerjoin(
            DocumentPage,
            and_(
                DocumentPage.organization_id == SourceSpan.organization_id,
                DocumentPage.id == SourceSpan.page_id,
            ),
        )
        .where(
            SourceSpan.organization_id == organization_id,
            SourceSpan.document_version_id == document.id,
            SourceSpan.id == source_span_id,
        )
    ).one_or_none()
    if row is None:
        raise _results_not_ready()
    span, block, page_no = row
    if block is None:
        kind = "image_page" if document.parser_name == "image" else "pdf_page"
        paragraph_no = None
        table_path = None
    elif block.table_path:
        kind = "docx_table_cell"
        paragraph_no = block.paragraph_no
        table_path = block.table_path
    elif block.page_id is None:
        kind = "docx_paragraph"
        paragraph_no = block.paragraph_no
        table_path = block.table_path
    else:
        kind = "image_page" if document.parser_name == "image" else "pdf_page"
        paragraph_no = block.paragraph_no
        table_path = block.table_path
    return {
        "source_span_id": span.id,
        "document_version_id": span.document_version_id,
        "kind": kind,
        "page_no": page_no,
        "paragraph_no": paragraph_no,
        "table_path": table_path,
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
        "bbox": span.bbox_json,
        "quote": span.quote,
    }


def _evidence_payloads(
    session: Session,
    *,
    organization_id: UUID,
    document: DocumentVersion,
    association_rows: list[Any],
) -> list[dict[str, Any]]:
    return [
        _source_locator_payload(
            session,
            organization_id=organization_id,
            document=document,
            source_span_id=row.source_span_id,
        )
        for row in association_rows
    ]


def get_review_results(
    session: Session,
    *,
    organization_id: UUID,
    task_id: UUID,
    viewer_user_id: UUID | None,
    risk_severity: str | None = None,
    risk_status: str | None = None,
    clause_status: str | None = None,
    include_evidence: bool = True,
) -> dict[str, Any]:
    statement = select(ReviewTask).where(
        ReviewTask.organization_id == organization_id,
        ReviewTask.id == task_id,
    )
    if viewer_user_id is not None:
        statement = statement.join(
            ContractAccessGrant,
            and_(
                ContractAccessGrant.organization_id == ReviewTask.organization_id,
                ContractAccessGrant.contract_id == ReviewTask.contract_id,
                ContractAccessGrant.user_id == viewer_user_id,
                ContractAccessGrant.access_level == "read",
            ),
        )
    task = session.scalar(statement)
    if task is None:
        raise ApplicationError(
            status_code=404,
            code="REVIEW_TASK_NOT_FOUND",
            message="审核任务不存在。",
        )
    classification = session.scalar(
        select(ContractClassification).where(
            ContractClassification.organization_id == organization_id,
            ContractClassification.review_task_id == task.id,
        )
    )
    fields = list(
        session.scalars(
            select(ExtractedField)
            .where(
                ExtractedField.organization_id == organization_id,
                ExtractedField.review_task_id == task.id,
            )
            .order_by(ExtractedField.field_key)
        )
    )
    if classification is None or {field.field_key for field in fields} != set(
        CORE_EXTRACTED_FIELD_KEYS
    ):
        raise _results_not_ready()
    if task.document_version_id is None:
        raise _results_not_ready()
    document = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.organization_id == organization_id,
            DocumentVersion.id == task.document_version_id,
            DocumentVersion.status == "succeeded",
        )
    )
    if document is None:
        raise _results_not_ready()
    classification_evidence = list(
        session.scalars(
            select(ContractClassificationEvidence)
            .where(
                ContractClassificationEvidence.organization_id == organization_id,
                ContractClassificationEvidence.classification_id == classification.id,
            )
            .order_by(ContractClassificationEvidence.position_no)
        )
    )
    extracted_evidence = {
        field.id: list(
            session.scalars(
                select(ExtractedFieldEvidence)
                .where(
                    ExtractedFieldEvidence.organization_id == organization_id,
                    ExtractedFieldEvidence.extracted_field_id == field.id,
                )
                .order_by(ExtractedFieldEvidence.position_no)
            )
        )
        for field in fields
    }
    risk_statement = select(RiskFinding).where(
        RiskFinding.organization_id == organization_id,
        RiskFinding.review_task_id == task.id,
    )
    if risk_severity is not None:
        risk_statement = risk_statement.where(RiskFinding.severity == risk_severity)
    if risk_status is not None:
        risk_statement = risk_statement.where(RiskFinding.status == risk_status)
    risk_findings = list(
        session.scalars(
            risk_statement.order_by(
                RiskFinding.severity, RiskFinding.created_at, RiskFinding.id
            )
        )
    )
    clause_statement = select(ClauseComparisonRow).where(
        ClauseComparisonRow.organization_id == organization_id,
        ClauseComparisonRow.review_task_id == task.id,
    )
    if clause_status is not None:
        clause_statement = clause_statement.where(ClauseComparisonRow.status == clause_status)
    clause_comparisons = list(
        session.scalars(
            clause_statement.order_by(ClauseComparisonRow.clause_key, ClauseComparisonRow.id)
        )
    )
    risk_evidence = {
        finding.id: list(
            session.scalars(
                select(RiskFindingEvidence)
                .where(
                    RiskFindingEvidence.organization_id == organization_id,
                    RiskFindingEvidence.finding_id == finding.id,
                )
                .order_by(RiskFindingEvidence.position_no)
            )
        )
        for finding in risk_findings
    }
    clause_evidence = {
        comparison.id: list(
            session.scalars(
                select(ClauseComparisonEvidence)
                .where(
                    ClauseComparisonEvidence.organization_id == organization_id,
                    ClauseComparisonEvidence.comparison_id == comparison.id,
                )
                .order_by(ClauseComparisonEvidence.position_no)
            )
        )
        for comparison in clause_comparisons
    }
    classification_payload = {
        "id": classification.id,
        "model_value": classification.model_value,
        "current_value": classification.current_value,
        "confidence": classification.confidence,
        "status": classification.status,
        "evidence": (
            _evidence_payloads(
                session,
                organization_id=organization_id,
                document=document,
                association_rows=classification_evidence,
            )
            if include_evidence
            else []
        ),
        "version": classification.version,
    }
    unresolved_count = sum(
        finding.status == "pending_review" for finding in risk_findings
    ) + sum(
        comparison.status in {"deviated", "missing", "uncertain"}
        for comparison in clause_comparisons
    )
    risk_counts = {
        severity: sum(finding.severity == severity for finding in risk_findings)
        for severity in ("high", "medium", "low")
    }
    return {
        "review_task_id": task.id,
        "classification": classification_payload,
        "extracted_fields": [
            {
                "id": field.id,
                "field_key": field.field_key,
                "model_value": field.model_value_json,
                "current_value": field.current_value_json,
                "status": field.status,
                "confidence": field.confidence,
                "evidence": (
                    _evidence_payloads(
                        session,
                        organization_id=organization_id,
                        document=document,
                        association_rows=extracted_evidence[field.id],
                    )
                    if include_evidence
                    else []
                ),
                "version": field.version,
            }
            for field in fields
        ],
        "risk_findings": [
            {
                "id": finding.id,
                "risk_type": finding.risk_type,
                "severity": finding.severity,
                "title": finding.title,
                "description": finding.description,
                "basis": finding.basis,
                "suggestion": finding.suggestion,
                "confidence": finding.confidence,
                "source": finding.source,
                "status": finding.status,
                "evidence": (
                    _evidence_payloads(
                        session,
                        organization_id=organization_id,
                        document=document,
                        association_rows=risk_evidence[finding.id],
                    )
                    if include_evidence
                    else []
                ),
                "version": finding.version,
            }
            for finding in risk_findings
        ],
        "clause_comparisons": [
            {
                "id": comparison.id,
                "clause_key": comparison.clause_key,
                "status": comparison.status,
                "contract_text": comparison.contract_text,
                "difference_summary": comparison.difference_summary,
                "severity": comparison.severity,
                "suggestion": comparison.suggestion,
                "evidence": (
                    _evidence_payloads(
                        session,
                        organization_id=organization_id,
                        document=document,
                        association_rows=clause_evidence[comparison.id],
                    )
                    if include_evidence
                    else []
                ),
                "version": comparison.version,
            }
            for comparison in clause_comparisons
        ],
        "summary": {
            "risk_total": len(risk_findings),
            "high": risk_counts["high"],
            "medium": risk_counts["medium"],
            "low": risk_counts["low"],
            "warning_total": 0,
            "unresolved_count": unresolved_count,
        },
    }
__all__ = [
    "DocumentInput",
    "ResultExecutionError",
    "execute_classification",
    "execute_extraction",
    "execute_risk_analysis",
    "execute_clause_comparison",
    "get_review_results",
]
