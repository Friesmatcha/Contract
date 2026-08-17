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


class AuthenticationError(ApplicationError):
    def __init__(self, code: str = "AUTHENTICATION_REQUIRED", message: str = "请先登录。") -> None:
        super().__init__(status_code=401, code=code, message=message)


class ForbiddenError(ApplicationError):
    def __init__(self, code: str = "FORBIDDEN", message: str = "当前请求不被允许。") -> None:
        super().__init__(status_code=403, code=code, message=message)


class RateLimitedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(status_code=429, code="RATE_LIMITED", message="请求过于频繁，请稍后重试。")
