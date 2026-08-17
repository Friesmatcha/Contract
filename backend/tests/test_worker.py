from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.worker.celery_app import create_celery_app


def test_celery_uses_redis_without_exposing_it_in_task_configuration() -> None:
    settings = Settings(
        app_env="test",
        database_url=SecretStr("postgresql+psycopg://test:test@localhost/test"),
        redis_url=SecretStr("redis://localhost:6379/15"),
    )

    app = create_celery_app(settings)

    assert app.conf.broker_url == "redis://localhost:6379/15"
    assert app.conf.task_serializer == "json"
    assert app.conf.enable_utc is True
