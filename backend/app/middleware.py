import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

from backend.app.errors import error_response
from backend.app.logging import bind_request_id, reset_request_id

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
logger = logging.getLogger(__name__)


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else f"req_{uuid4().hex}"
    )
    request.state.request_id = request_id
    token = bind_request_id(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("unhandled_request_error", extra={"error_class": type(exc).__name__})
            response = error_response(
                status_code=500,
                code="INTERNAL_ERROR",
                message="服务暂时不可用。",
                request_id=request_id,
            )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        request.state.duration_ms = duration_ms
        logger.info(
            "http_request_completed",
            extra={
                "duration_ms": duration_ms,
                "http_method": request.method,
                "http_path": request.url.path,
                "request_id": request_id,
                "status_code": response.status_code,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        reset_request_id(token)
