import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.repositories.users import UserRepository
from app.services.session_manager import SESSION_COOKIE_NAME


@pytest.fixture(autouse=True)
def configure_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PROSTE_PRAWO_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PROSTE_PRAWO_DISABLE_CLOUDFLARE_TURNSTILE", "true")
    monkeypatch.setenv("PROSTE_PRAWO_SMTP__SENDER", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_register_and_session_flow(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "secret123", "turnstile_token": None},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "user@example.com"
    assert SESSION_COOKIE_NAME in response.cookies

    session_response = client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["user"]["email"] == "user@example.com"


def test_login_sets_cookie(client: TestClient) -> None:
    repo = UserRepository()
    repo.create_user("login@example.com", "$2b$12$C6UzMDM.H6dfI/f/IKGheu", is_verified=True)  # bcrypt hash for 'password'

    response = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "password", "turnstile_token": None},
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies


def test_verification_endpoint_marks_user_verified(client: TestClient) -> None:
    repo = UserRepository()
    user = repo.create_user("verify@example.com", "hash", is_verified=False)
    token = repo.issue_verification_token(user, ttl_hours=1)

    response = client.post(
        "/api/auth/verify",
        json={"token": token.token, "turnstile_token": None},
    )
    assert response.status_code == 200
    repo_user = repo.get_user_by_email("verify@example.com")
    assert repo_user is not None and repo_user.is_verified


def test_password_reset_request_returns_accepted(client: TestClient) -> None:
    repo = UserRepository()
    repo.create_user("reset@example.com", "hash", is_verified=True)

    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "reset@example.com", "turnstile_token": None},
    )
    assert response.status_code == 202
