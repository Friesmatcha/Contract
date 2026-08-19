import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://contract:replace-me@127.0.0.1:5432/contract_test"


def _ensure_test_database(database_url: str) -> None:
    url = make_url(database_url)
    database_name = url.database
    if database_name is None:
        raise RuntimeError("TEST_DATABASE_URL must include a database name")
    admin_url = url.set(database="postgres", drivername="postgresql")
    admin_dsn = admin_url.render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    _ensure_test_database(database_url)
    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
    get_settings.cache_clear()

    repository_root = Path(__file__).resolve().parents[4]
    alembic_config = Config(str(repository_root / "alembic.ini"))
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(database_engine: Engine) -> Iterator[None]:
    with database_engine.begin() as connection:
        connection.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_truncate"))
        connection.execute(
            text(
                "TRUNCATE TABLE auth_rate_limits, audit_logs, idempotency_records, "
                "organization_memberships, support_access_grants, users, organizations, "
                "platform_model_configurations CASCADE"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO platform_model_configurations (
                    id, singleton_key, timeout_seconds, max_retries,
                    usage_tracking_enabled, status, version
                ) VALUES (
                    '00000000-0000-0000-0000-000000000004', 1, 60, 3, true, 'active', 1
                )
                """
            )
        )
        connection.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_truncate"))
    yield


@pytest.fixture
def session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=database_engine, expire_on_commit=False)
