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
