from uuid import UUID

from backend.app.config import get_settings
from backend.app.db import create_database_engine, create_session_factory
from backend.app.integrations.model.fake import FakeModelGateway
from backend.app.integrations.model.qwen import QwenModelGateway
from backend.app.integrations.storage.local import LocalFileStore
from backend.app.modules.reviews.results.worker import Phase9CStageExecutor
from backend.app.modules.reviews.service import process_review_task
from backend.app.worker.celery_app import celery_app


@celery_app.task(name="reviews.run_review_task")  # type: ignore[untyped-decorator]
def run_review_task(task_id: str) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        with create_session_factory(engine)() as session:
            gateway = (
                FakeModelGateway()
                if settings.app_env == "test"
                else QwenModelGateway(
                    api_key=settings.model_api_key,
                    model=settings.model_name,
                )
            )
            process_review_task(
                session,
                task_id=UUID(task_id),
                executor=Phase9CStageExecutor(
                    session,
                    task_id=UUID(task_id),
                    file_store=LocalFileStore(settings.file_storage_root),
                    gateway=gateway,
                ),
            )
    finally:
        engine.dispose()
