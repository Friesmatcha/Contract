import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.health import router as health_router
from backend.app.config import Settings, SettingsConfigurationError, get_settings
from backend.app.db import check_database, create_database_engine, create_session_factory
from backend.app.errors import error_response
from backend.app.integrations.antivirus.clamav import ClamAVScanner
from backend.app.integrations.notifications.smtp import create_mailer
from backend.app.integrations.storage.local import LocalFileStore
from backend.app.logging import configure_logging
from backend.app.middleware import request_context_middleware
from backend.app.modules.audit.api import router as audit_router
from backend.app.modules.clauses.templates.api import router as clause_templates_router
from backend.app.modules.contracts.api import file_router
from backend.app.modules.contracts.api import router as contracts_router
from backend.app.modules.documents.api import router as documents_router
from backend.app.modules.feedback.api import router as feedback_router
from backend.app.modules.identity.api import router as identity_router
from backend.app.modules.identity.organization_api import router as organization_router
from backend.app.modules.operations.api import router as operations_router
from backend.app.modules.reports.api import router as reports_router
from backend.app.modules.reports.renderer import (
    ChromiumPdfRenderer,
    FakeReportRenderer,
    ReportRenderer,
)
from backend.app.modules.reviews.api import contract_reviews_router
from backend.app.modules.reviews.api import result_router as review_result_router
from backend.app.modules.reviews.api import router as reviews_router
from backend.app.modules.risks.rules.api import router as risk_rules_router
from backend.app.modules.warnings.api import notification_router, warning_router
from backend.app.observability.metrics import metrics_response
from backend.app.shared.errors import ApplicationError

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    database_check: Callable[[], None] | None = None,
    file_store: LocalFileStore | None = None,
    antivirus_scanner: ClamAVScanner | None = None,
    report_renderer: ReportRenderer | None = None,
) -> FastAPI:
    configuration_error: SettingsConfigurationError | None = None
    if settings is None:
        try:
            settings = get_settings()
        except SettingsConfigurationError as exc:
            configuration_error = exc

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings is not None:
            engine = create_database_engine(settings.database_url.get_secret_value())
            app.state.db_engine = engine
            app.state.session_factory = create_session_factory(engine)
            app.state.database_check = database_check or (lambda: check_database(engine))
            app.state.file_store = file_store or LocalFileStore(settings.file_storage_root)
            app.state.antivirus_scanner = antivirus_scanner or ClamAVScanner(
                host=settings.clamav_host,
                port=settings.clamav_port,
                timeout_seconds=settings.clamav_timeout_seconds,
            )
            app.state.report_renderer = report_renderer or (
                FakeReportRenderer() if settings.app_env == "test" else ChromiumPdfRenderer()
            )
        try:
            yield
        finally:
            active_engine = getattr(app.state, "db_engine", None)
            if active_engine is not None:
                active_engine.dispose()

    app = FastAPI(title="Contract Review API", version="0.1.0", lifespan=lifespan)
    app.state.configuration_error = configuration_error
    app.state.settings = settings
    if settings is not None:
        app.state.mailer = create_mailer(settings)

    if settings is not None:
        configure_logging(settings.log_level, service="api", environment=settings.app_env)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Content-Type",
                "X-CSRF-Token",
                "X-Request-ID",
                "Idempotency-Key",
                "X-Organization-ID",
                "X-Support-Access-Grant",
            ],
        )
    else:
        configure_logging("INFO", service="api", environment="unknown")

    app.middleware("http")(request_context_middleware)
    app.include_router(health_router, prefix="/api/v1")
    app.add_api_route("/metrics", metrics_response, methods=["GET"], include_in_schema=False)
    if settings is not None:
        app.include_router(identity_router, prefix="/api/v1")
        app.include_router(organization_router, prefix="/api/v1")
        app.include_router(contracts_router, prefix="/api/v1")
        app.include_router(file_router, prefix="/api/v1")
        app.include_router(documents_router, prefix="/api/v1")
        app.include_router(risk_rules_router, prefix="/api/v1")
        app.include_router(clause_templates_router, prefix="/api/v1")
        app.include_router(contract_reviews_router, prefix="/api/v1")
        app.include_router(reviews_router, prefix="/api/v1")
        app.include_router(review_result_router, prefix="/api/v1")
        app.include_router(warning_router, prefix="/api/v1")
        app.include_router(notification_router, prefix="/api/v1")
        app.include_router(feedback_router, prefix="/api/v1")
        app.include_router(reports_router, prefix="/api/v1")
        app.include_router(audit_router, prefix="/api/v1")
        app.include_router(operations_router, prefix="/api/v1")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "RESOURCE_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        message = "资源不存在。" if exc.status_code == 404 else "请求无法处理。"
        return error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
            request_id=getattr(request.state, "request_id", "req_unknown"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="请求参数未通过校验。",
            request_id=getattr(request.state, "request_id", "req_unknown"),
        )

    @app.exception_handler(ApplicationError)
    async def application_exception(request: Request, exc: ApplicationError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=getattr(request.state, "request_id", "req_unknown"),
            details=exc.details,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_request_error", extra={"error_class": type(exc).__name__})
        return error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务暂时不可用。",
            request_id=getattr(request.state, "request_id", "req_unknown"),
        )

    return app


app = create_app()
