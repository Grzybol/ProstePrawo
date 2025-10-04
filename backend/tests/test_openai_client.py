"""Tests for the OpenAI client helper."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from openai import AuthenticationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.openai_client import OpenAIClient, OpenAIClientError


class _FailingCompletions:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create(self, **_: object):  # pragma: no cover - simple helper
        raise self._exc


class _FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.chat = SimpleNamespace(completions=_FailingCompletions(exc))


def test_complete_masks_authentication_error(caplog):
    message = "Incorrect API key provided: sk-test123"
    client = OpenAIClient(client=_FailingClient(AuthenticationError(message)))

    with caplog.at_level(logging.WARNING), pytest.raises(OpenAIClientError):
        client._complete([{"role": "user", "content": "Hello"}])

    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert all("sk-test123" not in record.message for record in caplog.records)
    assert any("[REDACTED]" in record.message for record in caplog.records)


def test_client_uses_api_key_from_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from_env\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PROSTE_PRAWO_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    class _DummyOpenAI:
        def __init__(self, *args, **kwargs) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda *a, **k: None)
            )

    monkeypatch.setattr("app.services.openai_client.OpenAI", _DummyOpenAI)
    try:
        OpenAIClient()
    finally:
        get_settings.cache_clear()

    assert captured.get("kwargs", {}).get("api_key") == "from_env"


def test_client_passes_project_when_available(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from_env")
    monkeypatch.setenv("OPENAI_PROJECT", "project-123")
    monkeypatch.delenv("PROSTE_PRAWO_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PROSTE_PRAWO_OPENAI_PROJECT", raising=False)
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    class _DummyOpenAI:
        def __init__(self, *args, **kwargs) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda *a, **k: None)
            )

    monkeypatch.setattr("app.services.openai_client.OpenAI", _DummyOpenAI)
    try:
        OpenAIClient()
    finally:
        get_settings.cache_clear()

    assert captured.get("kwargs", {}).get("api_key") == "from_env"
    assert captured.get("kwargs", {}).get("project") == "project-123"


def test_client_requires_api_key(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PROSTE_PRAWO_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="OpenAI API key is missing"):
            OpenAIClient()
    finally:
        get_settings.cache_clear()
