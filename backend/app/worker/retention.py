from backend.app.config import get_settings
from backend.app.db import create_database_engine, create_session_factory
from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.retention.service import run_retention_cleanup
from backend.app.worker.celery_app import celery_app


@celery_app.task(name="retention.run_cleanup")  # type: ignore[untyped-decorator]
def run_cleanup() -> list[str]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            finalized = run_retention_cleanup(
                session,
                file_store=LocalFileStore(settings.file_storage_root),
            )
        return [str(operation_id) for operation_id in finalized]
    finally:
        engine.dispose()


__all__ = ["run_cleanup"]
