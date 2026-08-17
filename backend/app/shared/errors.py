from typing import Any


class ApplicationError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(code)


class IdempotencyConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="该幂等键已用于不同请求。",
        )


class InvalidCursorError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            status_code=422,
            code="VALIDATION_ERROR",
            message="分页游标无效。",
            details={"field": "cursor"},
        )


class InvalidFilterError(ApplicationError):
    def __init__(self, field: str) -> None:
        super().__init__(
            status_code=422,
            code="VALIDATION_ERROR",
            message="筛选字段无效。",
            details={"field": field},
        )
