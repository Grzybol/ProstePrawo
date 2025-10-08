"""Reusable FastAPI dependency helpers for authentication."""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Response, status

from ..core.config import Settings, get_settings
from ..models.auth import User
from ..repositories.users import UserRepository
from ..services.session_manager import SESSION_COOKIE_NAME, SESSION_MAX_AGE, SessionManager


def get_user_repository() -> UserRepository:
    """Provide a repository instance for dependency injection."""

    return UserRepository()


def _session_manager(settings: Settings) -> SessionManager:
    secret = settings.session_secret_key or settings.turnstile_secret_key or settings.app_name
    return SessionManager(secret)


async def get_current_user(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    settings: Settings = Depends(get_settings),
    repository: UserRepository = Depends(get_user_repository),
) -> User:
    """Return the authenticated user based on the session cookie."""

    manager = _session_manager(settings)
    fallback_allowed = settings.environment != "production"

    def _bootstrap_demo_session() -> User:
        if not fallback_allowed:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Brak aktywnej sesji.")
        user = repository.ensure_demo_user()
        token = manager.create(user.id)
        _set_session_cookie(response, token, settings)
        return user

    if not session_token:
        return _bootstrap_demo_session()

    user_id = manager.verify(session_token)
    if user_id is None:
        if fallback_allowed:
            return _bootstrap_demo_session()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesja wygasła lub jest nieprawidłowa.")

    try:
        return repository.get_user_by_id(user_id)
    except KeyError:
        if fallback_allowed:
            return _bootstrap_demo_session()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesja wygasła lub jest nieprawidłowa.")


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
