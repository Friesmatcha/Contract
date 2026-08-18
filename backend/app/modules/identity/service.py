import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.modules.identity.models import (
    AuthOneTimeToken,
    AuthRateLimit,
    AuthSession,
    Organization,
    OrganizationMembership,
    User,
    normalize_email,
)
from backend.app.shared.audit import append_audit_log
from backend.app.shared.db import UnitOfWork
from backend.app.shared.errors import ApplicationError, AuthenticationError, RateLimitedError
from backend.app.shared.tenant import PlatformContext

SESSION_IDLE_TTL = timedelta(hours=8)
SESSION_ABSOLUTE_TTL = timedelta(days=7)
PASSWORD_RESET_TTL = timedelta(minutes=30)
INVITATION_TTL = timedelta(days=7)
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
CSRF_PREVIOUS_TTL = timedelta(minutes=5)
_PASSWORD_HASHER = PasswordHasher()
_DUMMY_HASH = _PASSWORD_HASHER.hash("not-a-real-password")


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session: AuthSession
    user: User


@dataclass(frozen=True, slots=True)
class SessionToken:
    raw_token: str
    csrf_token: str
    session: AuthSession


@dataclass(frozen=True, slots=True)
class PasswordResetDelivery:
    recipient: str
    reset_url: str


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _is_valid_email(email: str) -> bool:
    normalized = normalize_email(email)
    return 3 <= len(normalized) <= 320 and "@" in normalized and not normalized.startswith("@")


def _password_hash(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def validate_new_password(password: str) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ApplicationError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="密码长度必须为 12 到 128 个字符。",
            details={"field": "new_password"},
        )


def verify_password(password: str, password_hash: str | None) -> bool:
    target = password_hash or _DUMMY_HASH
    try:
        return _PASSWORD_HASHER.verify(target, password) and password_hash is not None
    except (InvalidHashError, VerifyMismatchError):
        return False


def _window_started_at(now: datetime) -> datetime:
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


def consume_rate_limit(
    session: Session,
    *,
    action: str,
    key: str,
    limit: int,
) -> None:
    now = _now()
    attempts = session.execute(
        insert(AuthRateLimit)
        .values(
            action=action,
            key_hash=_hash(key),
            window_started_at=_window_started_at(now),
            attempts=1,
        )
        .on_conflict_do_update(
            index_elements=["action", "key_hash", "window_started_at"],
            set_={"attempts": AuthRateLimit.attempts + 1},
        )
        .returning(AuthRateLimit.attempts)
    ).scalar_one()
    session.commit()
    if attempts > limit:
        raise RateLimitedError()


def _create_session(
    session: Session,
    *,
    user: User,
    ip: str | None,
    user_agent: str | None,
) -> SessionToken:
    now = _now()
    raw_token = _new_token("session")
    csrf_token = _new_token("csrf")
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=_hash(raw_token),
        csrf_hash=_hash(csrf_token),
        idle_expires_at=now + SESSION_IDLE_TTL,
        absolute_expires_at=now + SESSION_ABSOLUTE_TTL,
        last_seen_at=now,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(auth_session)
    session.flush()
    return SessionToken(raw_token=raw_token, csrf_token=csrf_token, session=auth_session)


def login(
    session: Session,
    *,
    email: str,
    password: str,
    request_id: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[AuthenticatedSession, SessionToken]:
    if not _is_valid_email(email):
        _record_failed_login(
            session,
            reason="invalid_credentials",
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
        raise ApplicationError(
            status_code=400,
            code="INVALID_CREDENTIALS",
            message="邮箱或密码格式无效。",
        )
    normalized_email = normalize_email(email)
    user = session.scalar(select(User).where(User.normalized_email == normalized_email))
    session.commit()
    if user is None or not verify_password(password, user.password_hash):
        _record_failed_login(
            session,
            actor=user.id if user is not None else None,
            reason="invalid_credentials",
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
        raise ApplicationError(
            status_code=401,
            code="AUTHENTICATION_FAILED",
            message="邮箱或密码错误。",
        )
    if user.status != "active":
        _record_failed_login(
            session,
            actor=user.id,
            reason="user_disabled",
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
        raise ApplicationError(status_code=403, code="USER_DISABLED", message="该账号已被停用。")
    with UnitOfWork(session) as unit_of_work:
        token = _create_session(session, user=user, ip=ip, user_agent=user_agent)
        append_audit_log(
            session,
            actor=PlatformContext(user.id),
            action="auth.login",
            resource_type="auth_session",
            resource_id=token.session.id,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
        )
        unit_of_work.commit()
    return AuthenticatedSession(token.session, user), token


def _record_failed_login(
    session: Session,
    *,
    reason: str,
    request_id: str,
    ip: str | None,
    user_agent: str | None,
    actor: UUID | None = None,
) -> None:
    with UnitOfWork(session) as unit_of_work:
        append_audit_log(
            session,
            actor=PlatformContext(actor) if actor is not None else None,
            action="auth.login_failed",
            resource_type="auth_attempt",
            request_id=request_id,
            after={"reason": reason},
            ip=ip,
            user_agent=user_agent,
        )
        unit_of_work.commit()


def load_authenticated_session(session: Session, raw_token: str | None) -> AuthenticatedSession:
    if not raw_token:
        raise AuthenticationError()
    now = _now()
    result = session.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == _hash(raw_token))
    ).one_or_none()
    if result is None:
        raise AuthenticationError("SESSION_EXPIRED", "会话已过期，请重新登录。")
    auth_session, user = result
    if (
        auth_session.revoked_at is not None
        or auth_session.idle_expires_at <= now
        or auth_session.absolute_expires_at <= now
    ):
        raise AuthenticationError("SESSION_EXPIRED", "会话已过期，请重新登录。")
    if user.status != "active":
        raise AuthenticationError("SESSION_EXPIRED", "会话已失效，请重新登录。")
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == auth_session.id)
        .values(
            last_seen_at=now,
            idle_expires_at=min(now + SESSION_IDLE_TTL, auth_session.absolute_expires_at),
        )
    )
    session.commit()
    return AuthenticatedSession(auth_session, user)


def rotate_csrf(session: Session, authenticated: AuthenticatedSession) -> str:
    csrf_token = _new_token("csrf")
    now = _now()
    with UnitOfWork(session) as unit_of_work:
        auth_session = session.scalar(
            select(AuthSession)
            .where(AuthSession.id == authenticated.session.id, AuthSession.revoked_at.is_(None))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if auth_session is None:
            raise AuthenticationError("SESSION_EXPIRED", "会话已过期，请重新登录。")
        auth_session.csrf_previous_hash = auth_session.csrf_hash
        auth_session.csrf_previous_expires_at = now + CSRF_PREVIOUS_TTL
        auth_session.csrf_hash = _hash(csrf_token)
        unit_of_work.commit()
    return csrf_token


def require_csrf(authenticated: AuthenticatedSession, csrf_token: str | None) -> None:
    if not csrf_token:
        raise ApplicationError(status_code=403, code="CSRF_INVALID", message="CSRF 校验失败。")
    candidate = _hash(csrf_token)
    current_valid = hmac.compare_digest(candidate, authenticated.session.csrf_hash)
    previous_valid = (
        authenticated.session.csrf_previous_hash is not None
        and authenticated.session.csrf_previous_expires_at is not None
        and authenticated.session.csrf_previous_expires_at > _now()
        and hmac.compare_digest(candidate, authenticated.session.csrf_previous_hash)
    )
    if not current_valid and not previous_valid:
        raise ApplicationError(status_code=403, code="CSRF_INVALID", message="CSRF 校验失败。")


def logout(session: Session, *, authenticated: AuthenticatedSession, request_id: str) -> None:
    with UnitOfWork(session) as unit_of_work:
        session.execute(
            update(AuthSession)
            .where(AuthSession.id == authenticated.session.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        append_audit_log(
            session,
            actor=PlatformContext(authenticated.user.id),
            action="auth.logout",
            resource_type="auth_session",
            resource_id=authenticated.session.id,
            request_id=request_id,
        )
        unit_of_work.commit()


def session_payload(
    session: Session, authenticated: AuthenticatedSession, csrf_token: str
) -> dict[str, object]:
    memberships = list(
        session.execute(
            select(OrganizationMembership, Organization.name)
            .join(Organization, OrganizationMembership.organization_id == Organization.id)
            .where(
                OrganizationMembership.user_id == authenticated.user.id,
                OrganizationMembership.status == "active",
            )
            .order_by(Organization.name)
        )
    )
    return {
        "user": {
            "id": str(authenticated.user.id),
            "email": authenticated.user.email,
            "display_name": authenticated.user.display_name,
            "status": authenticated.user.status,
            "is_platform_admin": authenticated.user.is_platform_admin,
        },
        "memberships": [
            {
                "organization_id": str(membership.organization_id),
                "organization_name": organization_name,
                "role": membership.role,
                "status": membership.status,
            }
            for membership, organization_name in memberships
        ],
        "csrf_token": csrf_token,
    }


def login_payload(
    session: Session, authenticated: AuthenticatedSession, csrf_token: str
) -> dict[str, object]:
    payload = session_payload(session, authenticated, csrf_token)
    memberships = payload.pop("memberships")
    assert isinstance(memberships, list)
    return {
        "user": payload["user"],
        "organizations": [
            {
                "id": membership["organization_id"],
                "name": membership["organization_name"],
                "role": membership["role"],
            }
            for membership in memberships
        ],
        "csrf_token": csrf_token,
    }


def request_password_reset(
    session: Session,
    *,
    email: str,
    request_id: str,
    frontend_base_url: str | None,
) -> PasswordResetDelivery | None:
    with UnitOfWork(session) as unit_of_work:
        user = session.scalar(
            select(User).where(User.normalized_email == normalize_email(email)).with_for_update()
        )
        if user is None or user.status != "active":
            return None
        if not frontend_base_url:
            raise ApplicationError(
                status_code=503,
                code="SMTP_NOT_CONFIGURED",
                message="认证邮件服务尚未配置。",
            )
        raw_token = _new_token("reset")
        session.execute(
            update(AuthOneTimeToken)
            .where(
                AuthOneTimeToken.user_id == user.id, AuthOneTimeToken.purpose == "password_reset"
            )
            .values(used_at=_now())
        )
        session.add(
            AuthOneTimeToken(
                user_id=user.id,
                purpose="password_reset",
                token_hash=_hash(raw_token),
                expires_at=_now() + PASSWORD_RESET_TTL,
            )
        )
        append_audit_log(
            session,
            actor=PlatformContext(user.id),
            action="auth.password_reset_requested",
            resource_type="user",
            resource_id=user.id,
            request_id=request_id,
        )
        unit_of_work.commit()
    assert user is not None
    reset_url = f"{frontend_base_url.rstrip('/')}/password-reset/confirm?"
    return PasswordResetDelivery(
        recipient=user.email,
        reset_url=reset_url + urlencode({"token": raw_token}),
    )


def confirm_password_reset(
    session: Session, *, token: str, new_password: str, request_id: str
) -> None:
    validate_new_password(new_password)
    with UnitOfWork(session) as unit_of_work:
        one_time_token = session.scalar(
            select(AuthOneTimeToken)
            .where(AuthOneTimeToken.token_hash == _hash(token))
            .with_for_update()
        )
        _validate_one_time_token(one_time_token, purpose="password_reset")
        assert one_time_token is not None and one_time_token.user_id is not None
        user = session.get(User, one_time_token.user_id)
        if user is None or user.status != "active":
            raise ApplicationError(status_code=400, code="TOKEN_INVALID", message="令牌无效。")
        user.password_hash = _password_hash(new_password)
        one_time_token.used_at = _now()
        session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        append_audit_log(
            session,
            actor=PlatformContext(user.id),
            action="auth.password_reset_completed",
            resource_type="user",
            resource_id=user.id,
            request_id=request_id,
        )
        unit_of_work.commit()


def issue_invitation_token(session: Session, *, membership_id: UUID) -> str:
    raw_token = _new_token("invite")
    with UnitOfWork(session) as unit_of_work:
        membership = session.scalar(
            select(OrganizationMembership)
            .where(OrganizationMembership.id == membership_id)
            .with_for_update()
        )
        if membership is None or membership.status != "pending_invitation":
            raise ValueError("membership must be pending invitation")
        session.execute(
            update(AuthOneTimeToken)
            .where(
                AuthOneTimeToken.membership_id == membership_id,
                AuthOneTimeToken.purpose == "invitation",
                AuthOneTimeToken.used_at.is_(None),
            )
            .values(used_at=_now())
        )
        session.add(
            AuthOneTimeToken(
                membership_id=membership.id,
                purpose="invitation",
                token_hash=_hash(raw_token),
                expires_at=_now() + INVITATION_TTL,
            )
        )
        unit_of_work.commit()
    return raw_token


def accept_invitation(
    session: Session,
    *,
    token: str,
    display_name: str | None,
    password: str | None,
    request_id: str,
) -> dict[str, str]:
    with UnitOfWork(session) as unit_of_work:
        one_time_token = session.scalar(
            select(AuthOneTimeToken)
            .where(AuthOneTimeToken.token_hash == _hash(token))
            .with_for_update()
        )
        _validate_one_time_token(one_time_token, purpose="invitation")
        assert one_time_token is not None and one_time_token.membership_id is not None
        membership = session.get(OrganizationMembership, one_time_token.membership_id)
        if membership is None or membership.status != "pending_invitation":
            raise ApplicationError(status_code=400, code="TOKEN_INVALID", message="令牌无效。")
        user = session.scalar(
            select(User).where(User.normalized_email == membership.normalized_email)
        )
        if user is None:
            if not display_name or not password:
                raise ApplicationError(
                    status_code=422,
                    code="VALIDATION_ERROR",
                    message="新用户必须提供展示名和密码。",
                )
            validate_new_password(password)
            user = User(
                email=membership.email,
                normalized_email=membership.normalized_email,
                display_name=display_name.strip(),
                password_hash=_password_hash(password),
            )
            session.add(user)
            session.flush()
        elif user.status != "active":
            raise ApplicationError(
                status_code=409, code="EMAIL_ALREADY_IN_USE", message="该邮箱无法接受邀请。"
            )
        membership.user_id = user.id
        membership.status = "active"
        if display_name and user.display_name != display_name.strip() and not user.password_hash:
            user.display_name = display_name.strip()
        one_time_token.used_at = _now()
        append_audit_log(
            session,
            actor=PlatformContext(user.id),
            action="auth.invitation_accepted",
            resource_type="organization_membership",
            resource_id=membership.id,
            organization_id=membership.organization_id,
            request_id=request_id,
        )
        unit_of_work.commit()
    return {
        "user_id": str(user.id),
        "organization_id": str(membership.organization_id),
        "role": membership.role,
        "status": membership.status,
    }


def _validate_one_time_token(token: AuthOneTimeToken | None, *, purpose: str) -> None:
    if token is None or token.purpose != purpose:
        raise ApplicationError(status_code=400, code="TOKEN_INVALID", message="令牌无效。")
    if token.used_at is not None:
        raise ApplicationError(status_code=409, code="TOKEN_ALREADY_USED", message="令牌已使用。")
    if token.expires_at <= _now():
        raise ApplicationError(status_code=400, code="TOKEN_EXPIRED", message="令牌已过期。")
