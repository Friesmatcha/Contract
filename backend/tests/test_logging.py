import logging

from backend.app.logging import configure_logging


def test_uvicorn_access_log_is_disabled_in_favor_of_request_log() -> None:
    configure_logging("INFO", service="api", environment="test")

    access_logger = logging.getLogger("uvicorn.access")

    assert access_logger.disabled is True
    assert access_logger.propagate is False
