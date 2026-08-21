from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request

from backend.app.db import DatabaseSession
from backend.app.errors import ErrorResponse
from backend.app.modules.contracts.schemas import ContractType
from backend.app.modules.identity.api import Authenticated
from backend.app.modules.identity.organization import require_organization_member
from backend.app.modules.operations.schemas import ReviewMetricsResponse, WarningMetricsResponse
from backend.app.modules.operations.service import (
    ensure_metrics_enabled,
    review_metrics,
    warning_metrics,
)
from backend.app.shared.errors import ApplicationError

router = APIRouter(tags=["operations"])


def _validate_range(from_: datetime, to: datetime) -> None:
    if (
        from_.tzinfo is None
        or from_.utcoffset() is None
        or to.tzinfo is None
        or to.utcoffset() is None
    ):
        raise ApplicationError(
            status_code=422,
            code="INVALID_DATE_RANGE",
            message="日期必须包含时区。",
        )
    if from_ >= to:
        raise ApplicationError(
            status_code=422,
            code="INVALID_DATE_RANGE",
            message="开始日期必须早于结束日期。",
        )


def _reject_unknown(request: Request, allowed: set[str]) -> None:
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise ApplicationError(
            status_code=422,
            code="INVALID_DATE_RANGE",
            message="指标筛选字段无效。",
            details={"field": unknown[0]},
        )


def _require_org_admin(database: DatabaseSession, organization_id: UUID, user_id: UUID) -> None:
    require_organization_member(
        database,
        organization_id=organization_id,
        user_id=user_id,
        require_org_admin=True,
    )


@router.get(
    "/organizations/{organization_id}/metrics/reviews",
    response_model=ReviewMetricsResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def get_review_metrics(
    organization_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    from_: Annotated[datetime, Query(alias="from")],
    to: datetime,
    contract_type: ContractType | None = None,
) -> ReviewMetricsResponse:
    _reject_unknown(request, {"from", "to", "contract_type"})
    _validate_range(from_, to)
    _require_org_admin(database, organization_id, authenticated.user.id)
    ensure_metrics_enabled(database)
    return ReviewMetricsResponse.model_validate(
        review_metrics(
            database,
            organization_id=organization_id,
            from_=from_,
            to=to,
            contract_type=contract_type,
        )
    )


@router.get(
    "/organizations/{organization_id}/metrics/warnings",
    response_model=WarningMetricsResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def get_warning_metrics(
    organization_id: UUID,
    request: Request,
    database: DatabaseSession,
    authenticated: Authenticated,
    from_: Annotated[datetime, Query(alias="from")],
    to: datetime,
    risk_type: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    severity: Literal["high", "medium", "low"] | None = None,
) -> WarningMetricsResponse:
    _reject_unknown(request, {"from", "to", "risk_type", "severity"})
    _validate_range(from_, to)
    _require_org_admin(database, organization_id, authenticated.user.id)
    ensure_metrics_enabled(database)
    return WarningMetricsResponse.model_validate(
        warning_metrics(
            database,
            organization_id=organization_id,
            from_=from_,
            to=to,
            risk_type=risk_type,
            severity=severity,
        )
    )


__all__ = ["router"]
