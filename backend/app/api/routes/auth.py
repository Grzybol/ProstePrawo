"""Authentication endpoints (register, login, verification, password reset)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urljoin

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ...core.config import Settings, get_settings
from ...models.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PublicAuthConfig,
    RegisterRequest,
    RegisterResponse,
    User,
    UserResponse,
    VerificationConfirmRequest,
)
from ...repositories.users import UserRepository
from ...services.mailer import Mailer
from ...services.session_manager import SESSION_COOKIE_NAME, SESSION_MAX_AGE, SessionManager
from ...services.turnstile import require_turnstile
from ..deps import get_current_user, get_user_repository

router = APIRouter(tags=["auth"])


def _safe_trimmed(value: object) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def _serialize_user(user: User) -> UserResponse:
    display_name = _safe_trimmed(getattr(user, "display_name", None))
    if display_name is None:
        display_name = _safe_trimmed(getattr(user, "name", None))

    username = _safe_trimmed(getattr(user, "username", None))
    email = _safe_trimmed(getattr(user, "email", None))

    identifier = None
    for candidate in (display_name, username, email):
        if candidate:
            identifier = candidate
            break

    return UserResponse(
        id=user.id,
        email=email,
        username=username,
        display_name=display_name,
        identifier=identifier,
        is_verified=bool(getattr(user, "is_verified", False)),
        points=getattr(user, "points", 0) or 0,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    store: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RegisterResponse:
    await require_turnstile(payload.turnstile_token, request, stage="register", settings=settings)
    store.cleanup_expired_tokens()

    existing = store.get_user_by_email(payload.email)
    hashed_password = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    auto_verify = not settings.smtp.is_configured()

    if existing:
        if existing.is_verified:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Użytkownik z tym adresem e-mail już istnieje.")
        store.update_user_password(existing, hashed_password)
        user = store.get_user_by_email(payload.email)
        assert user is not None  # for mypy
    else:
        user = store.create_user(payload.email, hashed_password, is_verified=auto_verify)

    if auto_verify:
        if not user.is_verified:
            store.mark_user_verified(user)
            user = store.get_user_by_email(payload.email)
            assert user is not None
        session_token = _session_manager(settings).create(user.id)
        _set_session_cookie(response, session_token, settings)
        store.record_login(user)
        return RegisterResponse(
            message="Konto zostało utworzone i zweryfikowane.",
            user=_serialize_user(user),
        )

    token = store.issue_verification_token(user, ttl_hours=settings.verification.token_ttl_hours)
    verification_link = _build_verification_link(settings, token.token)
    mailer = Mailer(settings)
    await mailer.send_verification_email(user.email, verification_link)
    return RegisterResponse(message="Sprawdź swoją skrzynkę pocztową, aby potwierdzić konto.")


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    store: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    await require_turnstile(payload.turnstile_token, request, stage="login", settings=settings)
    store.cleanup_expired_tokens()

    user = store.get_user_by_email(payload.email)
    if not user or not bcrypt.checkpw(payload.password.encode("utf-8"), user.password_hash.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy e-mail lub hasło.")

    mailer = Mailer(settings)
    if not user.is_verified:
        if settings.smtp.is_configured():
            token = store.issue_verification_token(user, ttl_hours=settings.verification.token_ttl_hours)
            verification_link = _build_verification_link(settings, token.token)
            await mailer.send_verification_email(user.email, verification_link)
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Konto nie zostało jeszcze zweryfikowane. Wysłaliśmy ponownie link aktywacyjny.",
            )
        store.mark_user_verified(user)
        user = store.get_user_by_email(payload.email)
        assert user is not None

    session_token = _session_manager(settings).create(user.id)
    _set_session_cookie(response, session_token, settings)
    store.record_login(user)
    return AuthResponse(message="Zalogowano pomyślnie.", user=_serialize_user(user))


@router.post("/password-reset/request", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    store: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await require_turnstile(payload.turnstile_token, request, stage="password-reset-request", settings=settings)
    store.cleanup_expired_tokens()

    user = store.get_user_by_email(payload.email)
    if user:
        token = store.issue_password_reset_token(user, ttl_hours=settings.password_reset.token_ttl_hours)
        reset_link = _build_password_reset_link(settings, token.token)
        mailer = Mailer(settings)
        await mailer.send_password_reset_email(user.email, reset_link)

    return MessageResponse(message="Jeżeli konto istnieje, wysłaliśmy instrukcje resetu hasła.")


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    request: Request,
    store: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    await require_turnstile(payload.turnstile_token, request, stage="password-reset-confirm", settings=settings)
    store.cleanup_expired_tokens()

    token_model = store.get_password_reset_token(payload.token)
    now = datetime.now(timezone.utc)
    if token_model is None or token_model.consumed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy lub wygasły token.")

    if token_model.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy lub wygasły token.")

    user = token_model.user
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy lub wygasły token.")

    hashed_password = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    store.update_user_password(user, hashed_password)
    store.consume_password_reset_token(token_model)
    return MessageResponse(message="Hasło zostało zaktualizowane.")


@router.post("/verify", response_model=AuthResponse)
async def verify_account(
    payload: VerificationConfirmRequest,
    request: Request,
    response: Response,
    store: Annotated[UserRepository, Depends(get_user_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    await require_turnstile(payload.turnstile_token, request, stage="verify", settings=settings)
    store.cleanup_expired_tokens()

    token_model = store.get_verification_token(payload.token)
    now = datetime.now(timezone.utc)
    if token_model is None or token_model.consumed_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy lub wygasły token.")

    if token_model.expires_at < now or token_model.user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy lub wygasły token.")

    user = token_model.user
    store.consume_verification_token(token_model)
    store.mark_user_verified(user)
    session_token = _session_manager(settings).create(user.id)
    _set_session_cookie(response, session_token, settings)
    store.record_login(user)
    return AuthResponse(message="Konto zostało potwierdzone.", user=_serialize_user(user))


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response) -> MessageResponse:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return MessageResponse(message="Wylogowano pomyślnie.")


@router.get("/config", response_model=PublicAuthConfig)
async def public_auth_config(settings: Annotated[Settings, Depends(get_settings)]) -> PublicAuthConfig:
    default_base = "http://localhost:8000"
    verification_base = settings.verification.base_url or default_base
    password_reset_base = (
        settings.password_reset.base_url or settings.verification.base_url or default_base
    )
    return PublicAuthConfig(
        turnstile_site_key=settings.turnstile_site_key,
        turnstile_disabled=settings.disable_cloudflare_turnstile,
        verification_base_url=verification_base,
        password_reset_base_url=password_reset_base,
        verification_token_ttl_hours=settings.verification.token_ttl_hours,
        password_reset_token_ttl_hours=settings.password_reset.token_ttl_hours,
    )


@router.get("/session", response_model=AuthResponse)
async def current_session(current_user: Annotated[User, Depends(get_current_user)]) -> AuthResponse:
    return AuthResponse(message="Sesja aktywna.", user=_serialize_user(current_user))


def _session_manager(settings: Settings) -> SessionManager:
    secret = settings.session_secret_key or settings.turnstile_secret_key or settings.app_name
    return SessionManager(secret, max_age_seconds=SESSION_MAX_AGE)


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def _build_verification_link(settings: Settings, token: str) -> str:
    base = settings.verification.base_url or "http://localhost:8000"
    base = base.rstrip("/") + "/"
    return urljoin(base, f"./verify.html?token={token}")


def _build_password_reset_link(settings: Settings, token: str) -> str:
    base = settings.password_reset.base_url or settings.verification.base_url
    base = base or "http://localhost:8000"
    base = base.rstrip("/") + "/"
    return urljoin(base, f"./password-reset-confirm.html?token={token}")
