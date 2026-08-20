from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def auth_client(database_engine: Engine) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        database_url=SecretStr(database_engine.url.render_as_string(hide_password=False)),
        redis_url=SecretStr("redis://localhost:6379/15"),
        allowed_origins=["http://localhost:5173"],
        smtp_host="localhost",
        smtp_from="contract-review@example.test",
        frontend_base_url="http://localhost:5173",
        model_name="qwen-test-model",
        model_api_key=SecretStr("test-model-api-key"),
    )
    app = create_app(settings=settings, database_check=lambda: None)
    with TestClient(app) as client:
        yield client
