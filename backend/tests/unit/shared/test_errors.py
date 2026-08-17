from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.shared.errors import ApplicationError


def test_application_error_uses_safe_contract_shape(app_factory) -> None:
    app: FastAPI = app_factory(lambda: None)

    @app.get("/test/application-error")
    def raise_application_error() -> None:
        raise ApplicationError(
            status_code=409,
            code="TEST_CONFLICT",
            message="请求冲突。",
            details={"field": "version"},
        )

    with TestClient(app) as client:
        response = client.get("/test/application-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "TEST_CONFLICT",
            "message": "请求冲突。",
            "request_id": response.headers["X-Request-ID"],
            "details": {"field": "version"},
        }
    }
    assert "traceback" not in response.text.lower()
