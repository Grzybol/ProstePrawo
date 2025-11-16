from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services import inference
from app.services.ingestion import DocumentSection


def test_build_summary_skips_cloud_when_text_blank(monkeypatch):
    monkeypatch.setattr(inference, "_should_use_cloud", lambda use_cloud: True)

    def _fail():  # pragma: no cover - defensive guard
        raise AssertionError("get_openai_client should not be called")

    monkeypatch.setattr(inference, "get_openai_client", _fail)

    summary, usage = inference.build_summary("   ")

    assert summary == "Brak treści do podsumowania."
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0


def test_extract_penalties_skips_cloud_when_text_blank(monkeypatch):
    monkeypatch.setattr(inference, "_should_use_cloud", lambda use_cloud: True)

    def _fail():  # pragma: no cover - defensive guard
        raise AssertionError("get_openai_client should not be called")

    monkeypatch.setattr(inference, "get_openai_client", _fail)

    penalties, usage = inference.extract_penalties("\n\t")

    assert penalties == []
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0


def test_simplify_sections_skips_cloud_when_all_text_blank(monkeypatch):
    monkeypatch.setattr(inference, "_should_use_cloud", lambda use_cloud: True)

    def _fail():  # pragma: no cover - defensive guard
        raise AssertionError("get_openai_client should not be called")

    monkeypatch.setattr(inference, "get_openai_client", _fail)

    result, usage = inference.simplify_sections(
        [DocumentSection(identifier="1", text="   ")]
    )

    assert result == []
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0


def test_generate_document_template_requires_prompt():
    with pytest.raises(ValueError):
        inference.generate_document_template("  \n  ", "PL")


def test_generate_document_template_local_builder(monkeypatch):
    monkeypatch.setattr(inference, "_should_use_cloud", lambda use_cloud: False)

    template, usage = inference.generate_document_template(
        "Umowa o świadczenie usług IT", "pl"
    )

    assert "Wzór dokumentu" in template
    assert "Umowa o świadczenie usług IT" in template
    assert "Polsce" in template
    assert usage.total_tokens == 0
