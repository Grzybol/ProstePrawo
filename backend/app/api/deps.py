"""Reusable FastAPI dependency helpers for authentication."""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status

from ..core.config import Settings, get_settings
from ..models.auth import User
from ..repositories.users import UserRepository
from ..services.session_manager import SESSION_COOKIE_NAME, SessionManager


def get_user_repository() -> UserRepository:
    """Provide a repository instance for dependency injection."""

    return UserRepository()


def _session_manager(settings: Settings) -> SessionManager:
    secret = settings.session_secret_key or settings.turnstile_secret_key or settings.app_name
    return SessionManager(secret)


async def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    settings: Settings = Depends(get_settings),
    repository: UserRepository = Depends(get_user_repository),
) -> User:
    """Return the authenticated user based on the session cookie."""

    if not session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Brak aktywnej sesji.")

    manager = _session_manager(settings)
    user_id = manager.verify(session_token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesja wygasła lub jest nieprawidłowa.")

    try:
        return repository.get_user_by_id(user_id)
    except KeyError as exc:  # pragma: no cover - extremely rare edge case
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesja wygasła lub jest nieprawidłowa.") from exc
