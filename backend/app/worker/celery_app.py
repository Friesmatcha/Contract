from celery import Celery

from backend.app.config import Settings, get_settings
from backend.app.logging import configure_logging


def create_celery_app(settings: Settings | None = None) -> Celery:
    resolved_settings = settings or get_settings()
    redis_url = resolved_settings.redis_url.get_secret_value()
    configure_logging(
        resolved_settings.log_level,
        service="worker",
        environment=resolved_settings.app_env,
    )
    application = Celery("contract_review", broker=redis_url, backend=redis_url)
    application.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        worker_hijack_root_logger=False,
    )
    return application


celery_app = create_celery_app()
