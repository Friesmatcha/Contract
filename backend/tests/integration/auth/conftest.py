from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from backend.app.config import Settings
from backend.app.main import create_app


@dataclass
class FakeMailer:
    password_resets: list[tuple[str, str]] = field(default_factory=list)

    def send_password_reset(self, *, recipient: str, reset_url: str) -> None:
        self.password_resets.append((recipient, reset_url))

    def send_invitation(self, *, recipient: str, invitation_url: str) -> None:
        pass


@pytest.fixture
def fake_mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def auth_client(database_engine: Engine, fake_mailer: FakeMailer) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        database_url=SecretStr(database_engine.url.render_as_string(hide_password=False)),
        redis_url=SecretStr("redis://localhost:6379/15"),
        allowed_origins=["http://localhost:5173"],
        smtp_host="localhost",
        smtp_from="contract-review@example.test",
        frontend_base_url="http://localhost:5173",
    )
    app = create_app(settings=settings, database_check=lambda: None)
    app.state.mailer = fake_mailer
    with TestClient(app) as client:
        yield client
