from typing import Annotated, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from backend.app.config import Settings
from backend.app.db import DatabaseSession
from backend.app.integrations.notifications.smtp import UnavailableMailer
from backend.app.modules.identity.schemas import (
    InvitationAcceptance,
    InvitationAcceptanceResponse,
    LoginRequest,
    LoginResponse,
    PasswordResetAccepted,
    PasswordResetConfirmation,
    PasswordResetRequest,
    SessionResponse,
)
from backend.app.modules.identity.service import (
    AuthenticatedSession,
    accept_invitation,
    confirm_password_reset,
    consume_rate_limit,
    load_authenticated_session,
    login,
    login_payload,
    logout,
    request_password_reset,
    require_csrf,
    rotate_csrf,
    session_payload,
)
from backend.app.shared.errors import ApplicationError, ForbiddenError

router = APIRouter(prefix="/auth", tags=["authentication"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_origin(request: Request, settings: Annotated[Settings, Depends(_settings)]) -> None:
    origin = request.headers.get("Origin")
    if not origin or origin not in settings.allowed_origins:
        raise ForbiddenError("ORIGIN_INVALID", "请求来源不被允许。")


def current_session(request: Request, database: DatabaseSession) -> AuthenticatedSession:
    return load_authenticated_session(database, request.cookies.get("session"))


Authenticated = Annotated[AuthenticatedSession, Depends(current_session)]


def csrf_protected(
    request: Request,
    authenticated: Authenticated,
    settings: Annotated[Settings, Depends(_settings)],
) -> AuthenticatedSession:
    require_origin(request, settings)
    require_csrf(authenticated, request.headers.get("X-CSRF-Token"))
    return authenticated


CsrfProtected = Annotated[AuthenticatedSession, Depends(csrf_protected)]


def _set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key="session",
        value=raw_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
def post_login(
    body: LoginRequest,
    response: Response,
    request: Request,
    database: DatabaseSession,
    settings: Annotated[Settings, Depends(_settings)],
    _: Annotated[None, Depends(require_origin)],
) -> LoginResponse:
    consume_rate_limit(database, action="login:email", key=body.email, limit=5)
    consume_rate_limit(database, action="login:ip", key=_client_ip(request), limit=30)
    authenticated, token = login(
        database,
        email=body.email,
        password=body.password,
        request_id=request.state.request_id,
        ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    _set_session_cookie(response, token.raw_token, settings)
    return LoginResponse.model_validate(login_payload(database, authenticated, token.csrf_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def post_logout(
    request: Request,
    database: DatabaseSession,
    settings: Annotated[Settings, Depends(_settings)],
    authenticated: CsrfProtected,
) -> Response:
    logout(database, authenticated=authenticated, request_id=request.state.request_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key="session", path="/", secure=settings.session_cookie_secure, httponly=True
    )
    return response


@router.get("/session", response_model=SessionResponse)
def get_session(database: DatabaseSession, authenticated: Authenticated) -> SessionResponse:
    csrf_token = rotate_csrf(database, authenticated)
    return SessionResponse.model_validate(session_payload(database, authenticated, csrf_token))


@router.post("/password-reset/request", response_model=PasswordResetAccepted, status_code=202)
def post_password_reset_request(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    database: DatabaseSession,
    settings: Annotated[Settings, Depends(_settings)],
    _: Annotated[None, Depends(require_origin)],
) -> PasswordResetAccepted:
    consume_rate_limit(database, action="reset:email", key=body.email, limit=3)
    consume_rate_limit(database, action="reset:ip", key=_client_ip(request), limit=15)
    mailer = request.app.state.mailer
    if isinstance(mailer, UnavailableMailer):
        raise ApplicationError(
            status_code=503, code="SMTP_NOT_CONFIGURED", message="认证邮件服务尚未配置。"
        )
    if not settings.frontend_base_url:
        raise ApplicationError(
            status_code=503, code="SMTP_NOT_CONFIGURED", message="认证邮件服务尚未配置。"
        )
    delivery = request_password_reset(
        database,
        email=body.email,
        request_id=request.state.request_id,
        frontend_base_url=settings.frontend_base_url,
    )
    if delivery is not None:
        background_tasks.add_task(
            mailer.send_password_reset,
            recipient=delivery.recipient,
            reset_url=delivery.reset_url,
        )
    return PasswordResetAccepted(
        accepted=True, message="如果账号存在，系统将继续处理密码重置请求。"
    )


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def post_password_reset_confirm(
    body: PasswordResetConfirmation,
    request: Request,
    database: DatabaseSession,
    _: Annotated[None, Depends(require_origin)],
) -> Response:
    consume_rate_limit(database, action="reset-confirm:ip", key=_client_ip(request), limit=15)
    confirm_password_reset(
        database,
        token=body.token,
        new_password=body.new_password,
        request_id=request.state.request_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invitations/accept", response_model=InvitationAcceptanceResponse)
def post_invitation_accept(
    body: InvitationAcceptance,
    request: Request,
    database: DatabaseSession,
    _: Annotated[None, Depends(require_origin)],
) -> InvitationAcceptanceResponse:
    consume_rate_limit(database, action="invite:ip", key=_client_ip(request), limit=15)
    return InvitationAcceptanceResponse.model_validate(
        accept_invitation(
            database,
            token=body.token,
            display_name=body.display_name,
            password=body.password,
            request_id=request.state.request_id,
        )
    )
