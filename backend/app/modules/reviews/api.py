from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from sqlalchemy import select

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.contracts.models import Contract
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.identity.organization import (
    require_organization_member,
    require_platform_admin,
)
from backend.app.modules.identity.support_access import authorize_support_access
from backend.app.modules.reviews.models import ReviewTask
from backend.app.modules.reviews.results.models import (
    ClauseComparison,
    ContractClassification,
    ExtractedField,
    RiskFinding,
)
from backend.app.modules.reviews.results.schemas import ReviewResultsResponse
from backend.app.modules.reviews.results.service import get_review_results
from backend.app.modules.reviews.revisions.schemas import (
    ClauseComparisonRevisionRequest,
    CompleteReviewRequest,
    ContractClassificationRevisionRequest,
    ExtractedFieldRevisionRequest,
    RevisionedClauseComparisonResponse,
    RevisionedContractClassificationResponse,
    RevisionedExtractedFieldResponse,
    RevisionedRiskFindingResponse,
    RiskFindingRevisionRequest,
)
from backend.app.modules.reviews.revisions.service import (
    revise_classification,
    revise_clause_comparison,
    revise_extracted_field,
    revise_risk_finding,
)
from backend.app.modules.reviews.schemas import (
    CreateReviewTaskRequest,
    RetryReviewTaskRequest,
    RetryReviewTaskResponse,
    ReviewStage,
    ReviewTaskResponse,
)
from backend.app.modules.reviews.service import (
    complete_review_task,
    create_review_task,
    get_review_task,
    retry_review_task,
    review_task_payload,
)
from backend.app.shared.errors import ApplicationError, ForbiddenError
from backend.app.shared.tenant import TenantContext

contract_reviews_router = APIRouter(prefix="/contracts", tags=["review tasks"])
router = APIRouter(prefix="/review-tasks", tags=["review tasks"])
result_router = APIRouter(tags=["review results"])


def _writer(role: str) -> None:
    if role not in {"org_admin", "reviewer"}:
        raise ForbiddenError()


def _contract_tenant(
    database: DatabaseSession, *, contract_id: UUID, user_id: UUID
) -> tuple[TenantContext, str]:
    organization_id = database.scalar(
        select(Contract.organization_id).where(Contract.id == contract_id)
    )
    database.commit()
    if organization_id is None:
        raise ApplicationError(status_code=404, code="CONTRACT_NOT_FOUND", message="合同不存在。")
    try:
        _, tenant, role = require_organization_member(
            database, organization_id=organization_id, user_id=user_id
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise ApplicationError(
                status_code=404, code="CONTRACT_NOT_FOUND", message="合同不存在。"
            ) from exc
        raise
    return tenant, role


def _task_organization(database: DatabaseSession, *, task_id: UUID) -> UUID:
    organization_id = database.scalar(
        select(ReviewTask.organization_id).where(ReviewTask.id == task_id)
    )
    database.commit()
    if organization_id is None:
        raise ApplicationError(
            status_code=404, code="REVIEW_TASK_NOT_FOUND", message="审核任务不存在。"
        )
    return organization_id


def _task_tenant(
    database: DatabaseSession, *, task_id: UUID, user_id: UUID
) -> tuple[TenantContext, str]:
    organization_id = _task_organization(database, task_id=task_id)
    try:
        _, tenant, role = require_organization_member(
            database, organization_id=organization_id, user_id=user_id
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise ApplicationError(
                status_code=404, code="REVIEW_TASK_NOT_FOUND", message="审核任务不存在。"
            ) from exc
        raise
    return tenant, role


def _result_tenant(
    database: DatabaseSession,
    *,
    subject_model: type[object],
    subject_id: UUID,
    user_id: UUID,
    not_found_code: str,
) -> tuple[TenantContext, str]:
    organization_id = database.scalar(
        select(subject_model.organization_id).where(subject_model.id == subject_id)  # type: ignore[attr-defined]
    )
    database.commit()
    if organization_id is None:
        raise ApplicationError(status_code=404, code=not_found_code, message="审核结果不存在。")
    try:
        _, tenant, role = require_organization_member(
            database, organization_id=organization_id, user_id=user_id
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            raise ApplicationError(
                status_code=404, code=not_found_code, message="审核结果不存在。"
            ) from exc
        raise
    return tenant, role


@contract_reviews_router.post(
    "/{contract_id}/reviews",
    response_model=ReviewTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def post_review_task(
    contract_id: UUID,
    body: CreateReviewTaskRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> ReviewTaskResponse:
    tenant, role = _contract_tenant(
        database, contract_id=contract_id, user_id=authenticated.user.id
    )
    _writer(role)
    task = create_review_task(
        database,
        actor=tenant,
        contract_id=contract_id,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
        settings=request.app.state.settings,
    )
    from backend.app.modules.reviews.service import review_task_payload

    return ReviewTaskResponse.model_validate(review_task_payload(database, task))


@router.get(
    "/{review_task_id}",
    response_model=ReviewTaskResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def get_review_task_endpoint(
    review_task_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
    include_stage_runs: bool = Query(False),
) -> ReviewTaskResponse:
    if support_grant_id is not None:
        require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
        grant = authorize_support_access(
            database,
            grant_id=support_grant_id,
            platform_admin_user_id=authenticated.user.id,
            request_id="review-read",
        )
        resolved_organization_id = grant.organization_id
        viewer_user_id = None
    else:
        tenant, role = _task_tenant(database, task_id=review_task_id, user_id=authenticated.user.id)
        resolved_organization_id = tenant.organization_id
        viewer_user_id = authenticated.user.id if role == "viewer" else None
    payload = get_review_task(
        database,
        organization_id=resolved_organization_id,
        task_id=review_task_id,
        viewer_user_id=viewer_user_id,
        include_stage_runs=include_stage_runs,
    )
    return ReviewTaskResponse.model_validate(payload)


@router.get(
    "/{review_task_id}/results",
    response_model=ReviewResultsResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def get_review_results_endpoint(
    review_task_id: UUID,
    database: DatabaseSession,
    authenticated: Authenticated,
    support_grant_id: Annotated[UUID | None, Header(alias="X-Support-Access-Grant")] = None,
    _risk_severity: Annotated[
        Literal["high", "medium", "low"] | None, Query(alias="risk_severity")
    ] = None,
    _risk_status: Annotated[
        Literal["pending_review", "confirmed", "false_positive", "processed"] | None,
        Query(alias="risk_status"),
    ] = None,
    _clause_status: Annotated[
        Literal["matched", "deviated", "missing", "uncertain"] | None,
        Query(alias="clause_status"),
    ] = None,
    include_evidence: Annotated[bool, Query()] = True,
) -> ReviewResultsResponse:
    if support_grant_id is not None:
        require_platform_admin(authenticated.user.id, authenticated.user.is_platform_admin)
        grant = authorize_support_access(
            database,
            grant_id=support_grant_id,
            platform_admin_user_id=authenticated.user.id,
            request_id="review-results-read",
        )
        resolved_organization_id = grant.organization_id
        viewer_user_id = None
    else:
        tenant, role = _task_tenant(database, task_id=review_task_id, user_id=authenticated.user.id)
        resolved_organization_id = tenant.organization_id
        viewer_user_id = authenticated.user.id if role == "viewer" else None
    payload = get_review_results(
        database,
        organization_id=resolved_organization_id,
        task_id=review_task_id,
        viewer_user_id=viewer_user_id,
        risk_severity=_risk_severity,
        risk_status=_risk_status,
        clause_status=_clause_status,
        include_evidence=include_evidence,
    )
    return ReviewResultsResponse.model_validate(payload)


@router.post(
    "/{review_task_id}/complete",
    response_model=ReviewTaskResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def complete_review_task_endpoint(
    review_task_id: UUID,
    body: CompleteReviewRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> ReviewTaskResponse:
    tenant, role = _task_tenant(database, task_id=review_task_id, user_id=authenticated.user.id)
    _writer(role)
    task = complete_review_task(
        database,
        actor=tenant,
        task_id=review_task_id,
        note=body.note,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
    )
    return ReviewTaskResponse.model_validate(review_task_payload(database, task))


@result_router.patch(
    "/contract-classifications/{classification_id}",
    response_model=RevisionedContractClassificationResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def revise_classification_endpoint(
    classification_id: UUID,
    body: ContractClassificationRevisionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RevisionedContractClassificationResponse:
    tenant, role = _result_tenant(
        database,
        subject_model=ContractClassification,
        subject_id=classification_id,
        user_id=authenticated.user.id,
        not_found_code="CLASSIFICATION_NOT_FOUND",
    )
    _writer(role)
    return RevisionedContractClassificationResponse.model_validate(
        revise_classification(
            database,
            actor=tenant,
            subject_id=classification_id,
            body=body,
            request_id=request.state.request_id,
        )
    )


@result_router.patch(
    "/extracted-fields/{field_id}",
    response_model=RevisionedExtractedFieldResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def revise_extracted_field_endpoint(
    field_id: UUID,
    body: ExtractedFieldRevisionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RevisionedExtractedFieldResponse:
    tenant, role = _result_tenant(
        database,
        subject_model=ExtractedField,
        subject_id=field_id,
        user_id=authenticated.user.id,
        not_found_code="FIELD_NOT_FOUND",
    )
    _writer(role)
    return RevisionedExtractedFieldResponse.model_validate(
        revise_extracted_field(
            database,
            actor=tenant,
            subject_id=field_id,
            body=body,
            request_id=request.state.request_id,
        )
    )


@result_router.patch(
    "/risk-findings/{finding_id}",
    response_model=RevisionedRiskFindingResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def revise_risk_finding_endpoint(
    finding_id: UUID,
    body: RiskFindingRevisionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RevisionedRiskFindingResponse:
    tenant, role = _result_tenant(
        database,
        subject_model=RiskFinding,
        subject_id=finding_id,
        user_id=authenticated.user.id,
        not_found_code="RISK_FINDING_NOT_FOUND",
    )
    _writer(role)
    return RevisionedRiskFindingResponse.model_validate(
        revise_risk_finding(
            database,
            actor=tenant,
            subject_id=finding_id,
            body=body,
            request_id=request.state.request_id,
        )
    )


@result_router.patch(
    "/clause-comparisons/{comparison_id}",
    response_model=RevisionedClauseComparisonResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def revise_clause_comparison_endpoint(
    comparison_id: UUID,
    body: ClauseComparisonRevisionRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
) -> RevisionedClauseComparisonResponse:
    tenant, role = _result_tenant(
        database,
        subject_model=ClauseComparison,
        subject_id=comparison_id,
        user_id=authenticated.user.id,
        not_found_code="CLAUSE_COMPARISON_NOT_FOUND",
    )
    _writer(role)
    return RevisionedClauseComparisonResponse.model_validate(
        revise_clause_comparison(
            database,
            actor=tenant,
            subject_id=comparison_id,
            body=body,
            request_id=request.state.request_id,
        )
    )


@router.post(
    "/{review_task_id}/retry",
    response_model=RetryReviewTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def retry_review_task_endpoint(
    review_task_id: UUID,
    body: RetryReviewTaskRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> RetryReviewTaskResponse:
    tenant, role = _task_tenant(database, task_id=review_task_id, user_id=authenticated.user.id)
    _writer(role)
    task, resumed_stage = retry_review_task(
        database,
        actor=tenant,
        task_id=review_task_id,
        body=body,
        idempotency_key=idempotency_key,
        request_id=request.state.request_id,
        settings=request.app.state.settings,
    )
    return RetryReviewTaskResponse(
        review_task_id=task.id,
        status="pending",
        resumed_from_stage=cast(ReviewStage, resumed_stage),
    )
