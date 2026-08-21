from uuid import UUID

from backend.app.config import get_settings
from backend.app.db import create_database_engine, create_session_factory
from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.reports.renderer import ChromiumPdfRenderer
from backend.app.modules.reports.service import process_report, recover_expired_report_leases
from backend.app.worker.celery_app import celery_app


@celery_app.task(name="reports.run_report")  # type: ignore[untyped-decorator]
def run_report(report_id: str) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            process_report(
                session,
                report_id=UUID(report_id),
                file_store=LocalFileStore(settings.file_storage_root),
                renderer=ChromiumPdfRenderer(),
            )
    finally:
        engine.dispose()


@celery_app.task(name="reports.recover_expired_leases")  # type: ignore[untyped-decorator]
def recover_report_leases() -> list[str]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            return [str(report_id) for report_id in recover_expired_report_leases(session)]
    finally:
        engine.dispose()


__all__ = ["recover_report_leases", "run_report"]
