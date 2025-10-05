from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.auth import PasswordResetToken, User, VerificationToken
from app.repositories.users import UserRepository


@pytest.fixture()
def user_repo(tmp_path) -> UserRepository:
    return UserRepository(db_path=tmp_path / "auth.db")


def test_create_and_retrieve_user(user_repo: UserRepository) -> None:
    user = user_repo.create_user("test@example.com", "hash", is_verified=False)
    assert isinstance(user, User)
    fetched = user_repo.get_user_by_email("test@example.com")
    assert fetched is not None
    assert fetched.email == "test@example.com"
    assert not fetched.is_verified

    user_repo.mark_user_verified(fetched)
    verified = user_repo.get_user_by_email("test@example.com")
    assert verified is not None and verified.is_verified

    user_repo.record_login(verified)
    refreshed = user_repo.get_user_by_email("test@example.com")
    assert refreshed is not None and refreshed.last_login_at is not None


def test_verification_token_lifecycle(user_repo: UserRepository) -> None:
    user = user_repo.create_user("verify@example.com", "hash", is_verified=False)
    token = user_repo.issue_verification_token(user, ttl_hours=1)
    assert isinstance(token, VerificationToken)
    retrieved = user_repo.get_verification_token(token.token)
    assert retrieved is not None
    assert retrieved.user is not None and retrieved.user.email == "verify@example.com"

    user_repo.consume_verification_token(retrieved)
    consumed = user_repo.get_verification_token(token.token)
    assert consumed is not None and consumed.consumed_at is not None

    user_repo.cleanup_expired_tokens()
    still_present = user_repo.get_verification_token(token.token)
    assert still_present is None


def test_password_reset_token_lifecycle(user_repo: UserRepository) -> None:
    user = user_repo.create_user("reset@example.com", "hash", is_verified=True)
    token = user_repo.issue_password_reset_token(user, ttl_hours=1)
    assert isinstance(token, PasswordResetToken)

    retrieved = user_repo.get_password_reset_token(token.token)
    assert retrieved is not None
    assert retrieved.user is not None and retrieved.user.email == "reset@example.com"

    user_repo.consume_password_reset_token(retrieved)
    consumed = user_repo.get_password_reset_token(token.token)
    assert consumed is not None and consumed.consumed_at is not None

    user_repo.cleanup_expired_tokens()
    still_present = user_repo.get_password_reset_token(token.token)
    assert still_present is None


def test_cleanup_removes_expired_tokens(user_repo: UserRepository) -> None:
    user = user_repo.create_user("expired@example.com", "hash", is_verified=True)
    token = user_repo.issue_password_reset_token(user, ttl_hours=0)
    assert token.expires_at <= datetime.now(timezone.utc)
    user_repo.cleanup_expired_tokens()
    assert user_repo.get_password_reset_token(token.token) is None
