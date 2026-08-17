import os
from collections.abc import Callable, Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        database_url=SecretStr("postgresql+psycopg://test:test@localhost:5432/test"),
        redis_url=SecretStr("redis://localhost:6379/15"),
        allowed_origins=["http://localhost:5173"],
    )


@pytest.fixture
def app_factory(settings: Settings) -> Callable[[Callable[[], None]], FastAPI]:
    def factory(database_check: Callable[[], None]) -> FastAPI:
        return create_app(settings=settings, database_check=database_check)

    return factory


@pytest.fixture
def client(app_factory: Callable[[Callable[[], None]], FastAPI]) -> Iterator[TestClient]:
    with TestClient(app_factory(lambda: None)) as test_client:
        yield test_client
