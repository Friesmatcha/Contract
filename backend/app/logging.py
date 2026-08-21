import json
import logging
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_SENSITIVE_LOG_PATTERNS = (
    (
        re.compile(
            r"(?i)(authorization|cookie|x-csrf-token|api[_-]?key|secret|token)\s*[:=]\s*[^\s,;]+"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)(prompt|raw[_-]?response|contract[_-]?text|response[_-]?body)\s*[:=].+"),
        r"\1=[REDACTED]",
    ),
)


def filter_sensitive_log_text(value: str) -> str:
    filtered = value
    for pattern, replacement in _SENSITIVE_LOG_PATTERNS:
        filtered = pattern.sub(replacement, filtered)
    return filtered


def bind_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "environment": self.environment,
            "request_id": getattr(record, "request_id", _request_id.get()),
            "event": filter_sensitive_log_text(record.getMessage()),
        }
        for name in (
            "duration_ms",
            "error_class",
            "http_method",
            "http_path",
            "status_code",
            "task_id",
            "stage",
            "organization_id",
            "user_id",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = filter_sensitive_log_text(str(value))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str, service: str, environment: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service=service, environment=environment))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for logger_name in ("uvicorn", "uvicorn.error"):
        framework_logger = logging.getLogger(logger_name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
