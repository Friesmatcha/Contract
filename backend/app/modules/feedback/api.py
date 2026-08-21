from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.contracts.api import _read_context
from backend.app.modules.contracts.schemas import ContractType
from backend.app.modules.feedback.schemas import (
    FeedbackCreateRequest,
    FeedbackResponse,
    FeedbackSummaryResponse,
)
from backend.app.modules.feedback.service import create_feedback, feedback_summary
from backend.app.modules.identity.api import Authenticated, CsrfProtected
from backend.app.modules.reviews.api import _task_tenant, _writer
from backend.app.shared.errors import ForbiddenError

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def post_feedback(
    body: FeedbackCreateRequest,
    request: Request,
    database: DatabaseSession,
    authenticated: CsrfProtected,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> FeedbackResponse:
    tenant, role = _task_tenant(
        database, task_id=body.review_task_id, user_id=authenticated.user.id
    )
    _writer(role)
    return FeedbackResponse.model_validate(
        create_feedback(
            database,
            actor=tenant,
            body=body,
            idempotency_key=idempotency_key,
            request_id=request.state.request_id,
        )
    )


@router.get(
    "/summary",
    response_model=FeedbackSummaryResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def get_feedback_summary(
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    contract_type: Annotated[ContractType | None, Query()] = None,
    rule_bundle_version_id: Annotated[UUID | None, Query()] = None,
    model_version: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> FeedbackSummaryResponse:
    resolved_organization_id, role = _read_context(
        database,
        authenticated=authenticated,
        organization_id=organization_id,
        support_grant_id=None,
        request_id=request.state.request_id,
    )
    if role != "org_admin":
        raise ForbiddenError("ORG_ADMIN_REQUIRED", "仅组织管理员可查看反馈统计。")
    return FeedbackSummaryResponse.model_validate(
        feedback_summary(
            database,
            organization_id=resolved_organization_id,
            contract_type=contract_type,
            rule_bundle_version_id=rule_bundle_version_id,
            model_version=model_version,
            created_from=created_from,
            created_to=created_to,
        )
    )


__all__ = ["router"]
