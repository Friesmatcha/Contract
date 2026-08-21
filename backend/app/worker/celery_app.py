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
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        beat_schedule={
            "reviews-recover-expired-leases": {
                "task": "reviews.recover_expired_leases",
                "schedule": 30.0,
            },
            "reviews-requeue-orphaned-tasks": {
                "task": "reviews.requeue_orphaned_tasks",
                "schedule": 60.0,
            },
            "reports-recover-expired-leases": {
                "task": "reports.recover_expired_leases",
                "schedule": 60.0,
            },
        },
    )
    return application


celery_app = create_celery_app()

# Register task modules for a worker started with this module as its app.
from backend.app.worker import compensation as _review_compensation  # noqa: E402,F401
from backend.app.worker import reports as _reports  # noqa: E402,F401
from backend.app.worker import review_tasks as _review_tasks  # noqa: E402,F401
