import hashlib
import json
from dataclasses import dataclass
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
    ExtractionRequest,
    ExtractionResult,
)
from backend.app.integrations.model.schemas import ExtractedField as ModelExtractedField
from backend.app.modules.contracts.models import ContractAccessGrant
from backend.app.modules.documents.models import (
    DocumentBlock,
    DocumentPage,
    DocumentVersion,
    SourceSpan,
)
from backend.app.modules.reviews.models import ReviewStageRun, ReviewTask
from backend.app.modules.reviews.results.models import (
    CONTRACT_CATEGORIES,
    CORE_EXTRACTED_FIELD_KEYS,
    ContractClassification,
    ContractClassificationEvidence,
    ExtractedField,
    ExtractedFieldEvidence,
)
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
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
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
        else:
            invocation = gateway.extract(
                request,
                context=ModelCallContext(
                    organization_id=task.organization_id,
                    review_task_id=task.id,
                    stage_run_id=stage_run.id,
                    capability=capability,
                ),
            )
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
    include_evidence: bool,
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
    }
__all__ = [
    "DocumentInput",
    "ResultExecutionError",
    "execute_classification",
    "execute_extraction",
    "get_review_results",
]
