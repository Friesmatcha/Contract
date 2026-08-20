from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.main import create_app


def test_phase11_openapi_projects_warning_and_notification_contract() -> None:
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url=SecretStr("postgresql+psycopg://test:test@localhost:5432/test"),
            redis_url=SecretStr("redis://localhost:6379/15"),
            allowed_origins=["http://localhost:5173"],
        ),
        database_check=lambda: None,
    )
    paths = app.openapi()["paths"]

    assert {
        "/api/v1/warnings",
        "/api/v1/warnings/{warning_id}",
        "/api/v1/warnings/{warning_id}/events",
        "/api/v1/notifications",
        "/api/v1/notifications/{notification_id}/read",
        "/api/v1/notifications/unread-count",
    } <= set(paths)
    assert paths["/api/v1/warnings/{warning_id}/events"]["post"]["responses"]["201"]
    assert paths["/api/v1/notifications/unread-count"]["get"]["responses"]["200"]
