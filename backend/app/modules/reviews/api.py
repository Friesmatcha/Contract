from typing import Annotated, cast
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
from backend.app.modules.reviews.schemas import (
    CreateReviewTaskRequest,
    RetryReviewTaskRequest,
    RetryReviewTaskResponse,
    ReviewStage,
    ReviewTaskResponse,
)
from backend.app.modules.reviews.service import (
    create_review_task,
    get_review_task,
    retry_review_task,
)
from backend.app.shared.errors import ApplicationError, ForbiddenError
from backend.app.shared.tenant import TenantContext

contract_reviews_router = APIRouter(prefix="/contracts", tags=["review tasks"])
router = APIRouter(prefix="/review-tasks", tags=["review tasks"])


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
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
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
    support_grant_id: Annotated[
        UUID | None, Header(alias="X-Support-Access-Grant")
    ] = None,
    include_stage_runs: bool = Query(False),
) -> ReviewTaskResponse:
    if support_grant_id is not None:
        require_platform_admin(
            authenticated.user.id, authenticated.user.is_platform_admin
        )
        grant = authorize_support_access(
            database,
            grant_id=support_grant_id,
            platform_admin_user_id=authenticated.user.id,
            request_id="review-read",
        )
        resolved_organization_id = grant.organization_id
        viewer_user_id = None
    else:
        tenant, role = _task_tenant(
            database, task_id=review_task_id, user_id=authenticated.user.id
        )
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
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
) -> RetryReviewTaskResponse:
    tenant, role = _task_tenant(
        database, task_id=review_task_id, user_id=authenticated.user.id
    )
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
