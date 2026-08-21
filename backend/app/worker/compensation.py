from backend.app.config import get_settings
from backend.app.db import create_database_engine, create_session_factory
from backend.app.modules.notifications.compensation import retry_failed_notifications
from backend.app.modules.reviews.service import (
    FakeStageExecutor,
    recover_expired_leases,
    requeue_orphaned_tasks,
)
from backend.app.worker.celery_app import celery_app


@celery_app.task(name="reviews.recover_expired_leases")  # type: ignore[untyped-decorator]
def recover_review_leases() -> list[str]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            recovered = recover_expired_leases(session, executor=FakeStageExecutor())
        return [str(task_id) for task_id in recovered]
    finally:
        engine.dispose()


@celery_app.task(name="reviews.requeue_orphaned_tasks")  # type: ignore[untyped-decorator]
def requeue_orphaned_reviews() -> list[str]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            queued = requeue_orphaned_tasks(session)
        return [str(task_id) for task_id in queued]
    finally:
        engine.dispose()


@celery_app.task(name="notifications.retry_failed")  # type: ignore[untyped-decorator]
def retry_notifications() -> list[str]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            processed = retry_failed_notifications(session)
        return [str(notification_id) for notification_id in processed]
    finally:
        engine.dispose()
