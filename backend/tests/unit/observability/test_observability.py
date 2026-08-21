import logging

from backend.app.logging import JsonFormatter, filter_sensitive_log_text


def test_sensitive_log_filter_removes_tokens_and_prompt_values() -> None:
    value = "token=secret-value prompt=contract body authorization=Bearer-value"
    filtered = filter_sensitive_log_text(value)
    assert "secret-value" not in filtered
    assert "contract body" not in filtered
    assert "Bearer-value" not in filtered


def test_json_formatter_keeps_low_cardinality_safe_fields() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="model_call_completed",
        args=(),
        exc_info=None,
    )
    record.organization_id = "org-1"
    record.user_id = "user-1"
    assert '"organization_id":"org-1"' in JsonFormatter("test", "test").format(record)
