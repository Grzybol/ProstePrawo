"""Tests for the OpenAI client helper."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

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


def test_complete_logs_full_authentication_error(caplog):
    message = "Incorrect API key provided: sk-test123"
    client = OpenAIClient(client=_FailingClient(AuthenticationError(message)))

    with caplog.at_level(logging.WARNING), pytest.raises(OpenAIClientError):
        client._complete([{"role": "user", "content": "Hello"}])

    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert any("sk-test123" in record.message for record in caplog.records)
    assert all("[REDACTED]" not in record.message for record in caplog.records)


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


def test_client_ignores_host_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from_file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "from_env")
    monkeypatch.setenv("PROSTE_PRAWO_OPENAI_API_KEY", "from_pref_env")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    class _DummyOpenAI:
        def __init__(self, *args, **kwargs) -> None:
            captured["kwargs"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda *a, **k: None)
            )

    monkeypatch.setattr("app.services.openai_client.OpenAI", _DummyOpenAI)
    try:
        OpenAIClient()
    finally:
        get_settings.cache_clear()

    assert captured.get("kwargs", {}).get("api_key") == "from_file"


def test_client_passes_project_when_available(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=from_file\nOPENAI_PROJECT=project-123\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PROSTE_PRAWO_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_PROJECT", raising=False)
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

    assert captured.get("kwargs", {}).get("api_key") == "from_file"
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


def test_extract_items_handles_markdown_json_response():
    response_content = """```json
    [\n  \"Pierwszy\",\n  \"Drugi\"\n]
    ```"""

    class _SuccessCompletions:
        def create(self, **_: object):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=response_content)
                    )
                ]
            )

    client = OpenAIClient(client=SimpleNamespace(chat=SimpleNamespace(completions=_SuccessCompletions())))

    result, usage = client.extract_items("Tekst", "Kategorie")

    assert result == ["Pierwszy", "Drugi"]
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_complete_json_retries_on_truncated_response(caplog):
    calls: list[int] = []

    class _RetryCompletions:
        def __init__(self) -> None:
            self._call_count = 0

        def create(self, **kwargs: object):
            calls.append(int(kwargs.get("max_tokens", 0)))
            self._call_count += 1
            if self._call_count == 1:
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='["Niedokonczona odpowiedz"'),
                            finish_reason="length",
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=10, completion_tokens=20, total_tokens=30
                    ),
                )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='["Gotowe"]'),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=5, completion_tokens=6, total_tokens=11
                ),
            )

    client = OpenAIClient(
        client=SimpleNamespace(chat=SimpleNamespace(completions=_RetryCompletions()))
    )

    with caplog.at_level(logging.WARNING):
        result, usage = client._complete_json(
            [{"role": "user", "content": "Test"}], max_tokens=50
        )

    assert result == ["Gotowe"]
    assert usage == {"prompt_tokens": 15, "completion_tokens": 26, "total_tokens": 41}
    assert calls[0] == 50
    assert calls[1] >= 100
    warning_messages = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert any("finish_reason=length" in message for message in warning_messages)


def test_complete_json_raises_when_truncated_and_limit_reached(caplog):
    calls: list[int] = []

    class _LengthCompletions:
        def create(self, **kwargs: object):
            calls.append(int(kwargs.get("max_tokens", 0)))
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='["Niedokonczona odpowiedz"'),
                        finish_reason="length",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

    client = OpenAIClient(
        client=SimpleNamespace(chat=SimpleNamespace(completions=_LengthCompletions()))
    )
    client._model_token_limit = MethodType(lambda self: 64, client)

    with caplog.at_level(logging.WARNING), pytest.raises(OpenAIClientError):
        client._complete_json([{"role": "user", "content": "Test"}], max_tokens=64)

    assert calls == [64]
    warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    error_messages = [record.message for record in caplog.records if record.levelno == logging.ERROR]
    assert any("finish_reason=length" in message for message in warning_messages)
    assert any("model token limit" in message for message in error_messages)
