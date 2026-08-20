from uuid import UUID

from backend.app.config import get_settings
from backend.app.db import create_database_engine, create_session_factory
from backend.app.modules.reviews.service import FakeStageExecutor, process_review_task
from backend.app.worker.celery_app import celery_app


@celery_app.task(name="reviews.run_review_task")  # type: ignore[untyped-decorator]
def run_review_task(task_id: str) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            process_review_task(
                session,
                task_id=UUID(task_id),
                executor=FakeStageExecutor(),
            )
    finally:
        engine.dispose()
