import logging
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.errors import ErrorResponse, error_response

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


class LiveHealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyHealthResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]
    configuration: Literal["ok"]


@router.get(
    "/live",
    response_model=LiveHealthResponse,
    responses={503: {"model": ErrorResponse, "description": "Service is unavailable"}},
)
def live() -> LiveHealthResponse:
    return LiveHealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadyHealthResponse,
    responses={503: {"model": ErrorResponse, "description": "Service is not ready"}},
)
def ready(request: Request) -> ReadyHealthResponse | JSONResponse:
    request_id: str = request.state.request_id
    if request.app.state.configuration_error is not None:
        return error_response(
            status_code=503,
            code="SERVICE_NOT_READY",
            message="服务配置不完整。",
            request_id=request_id,
            details={"configuration": "error", "database": "not_checked"},
        )

    database_check: Callable[[], None] = request.app.state.database_check
    try:
        database_check()
    except Exception as exc:
        logger.warning(
            "database_readiness_failed",
            extra={"error_class": type(exc).__name__},
        )
        return error_response(
            status_code=503,
            code="SERVICE_NOT_READY",
            message="服务尚未就绪。",
            request_id=request_id,
            details={"configuration": "ok", "database": "error"},
        )

    return ReadyHealthResponse(status="ready", database="ok", configuration="ok")
