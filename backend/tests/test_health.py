import logging
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import create_app


def test_live_returns_contract_response(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"].startswith("req_")


def test_request_id_is_echoed_when_valid(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "browser-request-123"},
    )

    assert response.headers["X-Request-ID"] == "browser-request-123"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": "invalid request id"},
    )

    assert response.headers["X-Request-ID"].startswith("req_")


def test_unknown_route_uses_shared_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/not-a-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_error_keeps_request_id(client: TestClient) -> None:
    @client.app.get("/api/v1/test-error")
    def raise_error() -> None:
        raise RuntimeError("postgresql://user:secret@private-host/contract")

    response = client.get("/api/v1/test-error", headers={"X-Request-ID": "req_expected"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req_expected"
    assert response.json()["error"]["request_id"] == "req_expected"
    assert "secret" not in response.text


def test_ready_returns_200_when_database_is_available(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "configuration": "ok",
    }


def test_ready_returns_safe_503_when_database_is_unavailable(
    app_factory: Callable[[Callable[[], None]], FastAPI],
) -> None:
    def unavailable() -> None:
        raise RuntimeError("postgresql://user:secret@private-host/contract")

    with TestClient(app_factory(unavailable), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_NOT_READY"
    assert response.json()["error"]["details"] == {
        "configuration": "ok",
        "database": "error",
    }
    assert "secret" not in response.text
    assert "private-host" not in response.text


def test_ready_returns_safe_503_when_configuration_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["details"] == {
        "configuration": "error",
        "database": "not_checked",
    }
    assert "DATABASE_URL" not in response.text


def test_health_openapi_matches_success_and_error_contract(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    live_responses = paths["/api/v1/health/live"]["get"]["responses"]
    ready_responses = paths["/api/v1/health/ready"]["get"]["responses"]

    assert live_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/LiveHealthResponse"
    )
    assert live_responses["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
    assert ready_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ReadyHealthResponse"
    )
    assert ready_responses["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )


def test_request_completion_log_contains_request_context(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="backend.app.middleware"):
        client.get("/api/v1/health/live", headers={"X-Request-ID": "request-log-test"})

    record = next(record for record in caplog.records if record.message == "http_request_completed")
    assert record.request_id == "request-log-test"
    assert record.http_method == "GET"
    assert record.http_path == "/api/v1/health/live"
    assert record.status_code == 200
    assert record.duration_ms >= 0
