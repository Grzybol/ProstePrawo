import importlib

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


@pytest.fixture
def template_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PROSTE_PRAWO_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PROSTE_PRAWO_SESSION_SECRET_KEY", "secret")
    monkeypatch.setenv("PROSTE_PRAWO_DISABLE_CLOUDFLARE_TURNSTILE", "1")
    monkeypatch.setenv("PROSTE_PRAWO_ENABLE_CLOUD_LLM", "0")
    monkeypatch.setenv("PROSTE_PRAWO_ENVIRONMENT", "test")

    from app.core import config

    config.get_settings.cache_clear()
    importlib.reload(importlib.import_module("app.api.routes.templates"))
    importlib.reload(importlib.import_module("app.api.routes.auth"))
    main_module = importlib.reload(importlib.import_module("app.main"))
    client = TestClient(main_module.app)
    try:
        yield client
    finally:
        client.close()
        config.get_settings.cache_clear()


def _register_user(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Secret123!", "turnstile_token": "ok"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == email


def test_generate_template_returns_markdown(template_client):
    _register_user(template_client, "template@example.com")

    response = template_client.post(
        "/api/templates/",
        json={"prompt": "Umowa współpracy marketingowej", "country": "PL"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["country"] == "PL"
    assert "Umowa współpracy marketingowej" in data["template"]
    assert data["token_usage"]["total_tokens"] == 0


def test_generate_template_rejects_unsupported_country(template_client):
    _register_user(template_client, "country@example.com")

    response = template_client.post(
        "/api/templates/",
        json={"prompt": "Kontrakt", "country": "DE"},
    )
    assert response.status_code == 400
    assert "Polski" in response.json()["detail"]
