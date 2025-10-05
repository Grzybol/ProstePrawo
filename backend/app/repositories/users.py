"""SQLite-backed repository for authentication artefacts."""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..core.config import get_settings
from ..models.auth import PasswordResetToken, User, VerificationToken


ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class UserRepository:
    """Persist user accounts and security tokens in SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or settings.data_dir / "auth.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS verification_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # User helpers
    # ------------------------------------------------------------------
    def create_user(self, email: str, password_hash: str, *, is_verified: bool = False) -> User:
        now = _now()
        payload = (email.lower(), password_hash, int(is_verified), now, now)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (email, password_hash, is_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                payload,
            )
            user_id = cursor.lastrowid
        return self.get_user_by_id(int(user_id))

    def get_user_by_id(self, user_id: int) -> User:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None:
            raise KeyError(str(user_id))
        return _row_to_user(row)

    def get_user_by_email(self, email: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
        if row is None:
            return None
        return _row_to_user(row)

    def update_user_password(self, user: User, password_hash: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?
                """,
                (password_hash, now, user.id),
            )

    def mark_user_verified(self, user: User) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users SET is_verified = 1, updated_at = ? WHERE id = ?
                """,
                (now, user.id),
            )

    def record_login(self, user: User) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?
                """,
                (now, now, user.id),
            )

    def list_users(self) -> Iterable[User]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        for row in rows:
            yield _row_to_user(row)

    # ------------------------------------------------------------------
    # Verification tokens
    # ------------------------------------------------------------------
    def issue_verification_token(self, user: User, *, ttl_hours: int) -> VerificationToken:
        token = secrets.token_urlsafe(32)
        created_at = _now()
        expires_at = _future_hours(ttl_hours)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO verification_tokens (token, user_id, expires_at, consumed_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (token, user.id, expires_at, created_at),
            )
        return self.get_verification_token(token)

    def get_verification_token(self, token: str) -> VerificationToken | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM verification_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        user = self.get_user_by_id(int(row["user_id"])) if row["user_id"] is not None else None
        return VerificationToken(
            token=str(row["token"]),
            user=user,
            expires_at=_parse_datetime(row["expires_at"]),
            consumed_at=_parse_datetime(row["consumed_at"]) if row["consumed_at"] else None,
            created_at=_parse_datetime(row["created_at"]),
        )

    def consume_verification_token(self, token: VerificationToken) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE verification_tokens SET consumed_at = ? WHERE token = ?
                """,
                (now, token.token),
            )

    # ------------------------------------------------------------------
    # Password reset tokens
    # ------------------------------------------------------------------
    def issue_password_reset_token(self, user: User, *, ttl_hours: int) -> PasswordResetToken:
        token = secrets.token_urlsafe(32)
        created_at = _now()
        expires_at = _future_hours(ttl_hours)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO password_reset_tokens (token, user_id, expires_at, consumed_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (token, user.id, expires_at, created_at),
            )
        return self.get_password_reset_token(token)

    def get_password_reset_token(self, token: str) -> PasswordResetToken | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        user = self.get_user_by_id(int(row["user_id"])) if row["user_id"] is not None else None
        return PasswordResetToken(
            token=str(row["token"]),
            user=user,
            expires_at=_parse_datetime(row["expires_at"]),
            consumed_at=_parse_datetime(row["consumed_at"]) if row["consumed_at"] else None,
            created_at=_parse_datetime(row["created_at"]),
        )

    def consume_password_reset_token(self, token: PasswordResetToken) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE password_reset_tokens SET consumed_at = ? WHERE token = ?
                """,
                (now, token.token),
            )

    # ------------------------------------------------------------------
    # Maintenance helpers
    # ------------------------------------------------------------------
    def cleanup_expired_tokens(self) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM verification_tokens WHERE expires_at < ? OR consumed_at IS NOT NULL",
                (now,),
            )
            conn.execute(
                "DELETE FROM password_reset_tokens WHERE expires_at < ? OR consumed_at IS NOT NULL",
                (now,),
            )


def _now() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def _future_hours(hours: int) -> str:
    delta = datetime.now(timezone.utc) + timedelta(hours=hours)
    return delta.strftime(ISO_FORMAT)


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=int(row["id"]),
        email=str(row["email"]),
        password_hash=str(row["password_hash"]),
        is_verified=bool(row["is_verified"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        last_login_at=_parse_datetime(row["last_login_at"]) if row["last_login_at"] else None,
    )


def _parse_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("Empty datetime value")
    return datetime.strptime(value, ISO_FORMAT)
