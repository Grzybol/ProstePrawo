"""Tests ensuring the pipeline switches between OpenAI and heuristic modes."""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("pydantic")

from app.models.documents import DocumentMetadata, DocumentProcessingStatus
from app.services.ingestion import DocumentSection, ExtractedDocument
from app.services.indexing import RetrievedChunk
from app.services.pipeline import DocumentPipeline
from app.services.sanitizer import SanitizationResult


class InMemoryRepository:
    def __init__(self) -> None:
        self._store: dict = {}

    def upsert(self, document: DocumentMetadata) -> None:
        self._store[document.document_id] = document

    def get(self, document_id):
        return self._store[document_id]

    def list(self) -> Iterable[DocumentMetadata]:
        return list(self._store.values())


class DummyIndexer:
    def __init__(self) -> None:
        self._documents: dict = {}
        self.retrieve_calls: list[tuple] = []

    def index(self, document_id, sections: Iterable[DocumentSection]) -> None:
        sections = list(sections)
        self._documents[document_id] = sections

    def retrieve(self, document_id, query: str, top_k: int):
        self.retrieve_calls.append((document_id, query, top_k))
        sections = self._documents.get(document_id, [])
        if not sections:
            return []
        first = sections[0]
        return [RetrievedChunk(identifier=first.identifier, score=1.0, text=first.text)]


@dataclass
class DummySettings:
    data_dir: Path
    enable_cloud_llm: bool
    llm_provider: str = "openai"
    openai_model: str = "gpt-test"
    openai_pricing: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "gpt-test": {"prompt": 0.001, "completion": 0.002},
            "default": {"prompt": 0.001, "completion": 0.002},
        }
    )


class DummyOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def summarise(self, text: str) -> tuple[str, dict[str, int]]:
        self.calls.append(("summarise", text))
        return "Streszczenie z chmury", {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }

    def extract_items(self, text: str, category: str) -> tuple[list[str], dict[str, int]]:
        self.calls.append(("extract_items", category))
        return [f"AI {category}"], {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
        }

    def simplify_sections(
        self, sections: Iterable[DocumentSection]
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
        sections = list(sections)
        self.calls.append(("simplify_sections", [section.identifier for section in sections]))
        return (
            [
                {
                    "identifier": section.identifier,
                    "plain_language": f"Uproszczenie {section.identifier}",
                    "source_excerpt": "fragment",
                }
                for section in sections
            ],
            {
                "prompt_tokens": 50,
                "completion_tokens": 25,
                "total_tokens": 75,
            },
        )

    def answer_question(
        self, question: str, retrieved_chunks: Iterable[RetrievedChunk]
    ) -> tuple[dict[str, object], dict[str, int]]:
        self.calls.append(("answer_question", question))
        return (
            {
                "answer": "Odpowiedź z chmury",
                "sources": [chunk.identifier for chunk in retrieved_chunks],
            },
            {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
        )


def _setup_documents(tmp_path: Path) -> tuple[InMemoryRepository, DummyIndexer, DocumentMetadata]:
    repository = InMemoryRepository()
    indexer = DummyIndexer()
    metadata = DocumentMetadata(title="Test")
    metadata.source_path = tmp_path / "source.txt"
    repository.upsert(metadata)
    return repository, indexer, metadata


def test_run_pipeline_uses_openai_when_enabled(tmp_path):
    repository, indexer, metadata = _setup_documents(tmp_path)
    settings = DummySettings(data_dir=tmp_path, enable_cloud_llm=True)
    extracted_original = ExtractedDocument(
        text="Treść oryginalna",
        sections=[DocumentSection(identifier="section-1", text="Treść oryginalna")],
    )
    sanitized_text = "To jest przykładowy tekst."
    extracted_sanitized = ExtractedDocument(
        text=sanitized_text,
        sections=[DocumentSection(identifier="section-1", text=sanitized_text)],
    )
    sanitization_result = SanitizationResult(text=sanitized_text, entities={}, secrets={})
    client = DummyOpenAIClient()

    def fake_extract(path):
        if path == metadata.source_path:
            return extracted_original
        return extracted_sanitized

    with patch("app.services.pipeline.get_settings", return_value=settings), patch(
        "app.services.inference.get_openai_client", return_value=client
    ), patch("app.services.ingestion.extract_document", side_effect=fake_extract), patch(
        "app.services.sanitizer.sanitize_text", return_value=sanitization_result
    ):
        pipeline = DocumentPipeline(repository=repository, indexer=indexer)
        asyncio.run(pipeline._run_pipeline(metadata.document_id))

    processed = repository.get(metadata.document_id)
    assert processed.status is DocumentProcessingStatus.READY
    assert processed.summary == "Streszczenie z chmury"
    assert processed.obligations == ["AI obowiązki"]
    assert processed.penalties == ["AI kary lub sankcje"]
    assert processed.deadlines == ["AI terminy lub daty graniczne"]
    assert processed.risks == ["AI ryzyka dla stron umowy"]
    assert all(section.plain_language.startswith("Uproszczenie") for section in processed.simplified_sections)
    assert processed.token_usage.prompt_tokens == 140
    assert processed.token_usage.completion_tokens == 70
    assert processed.token_usage.total_tokens == 210
    assert processed.token_usage.cost_usd == pytest.approx(0.00028)
    called_operations = [name for name, _ in client.calls]
    assert "summarise" in called_operations
    assert "simplify_sections" in called_operations


def test_run_pipeline_uses_heuristics_when_cloud_disabled(tmp_path):
    repository, indexer, metadata = _setup_documents(tmp_path)
    settings = DummySettings(data_dir=tmp_path, enable_cloud_llm=False)
    text_body = "Należy zapłacić karę do 7 dni."
    extracted = ExtractedDocument(
        text=text_body,
        sections=[DocumentSection(identifier="section-1", text=text_body)],
    )
    sanitization_result = SanitizationResult(text=text_body, entities={}, secrets={})

    def fake_extract(path):
        return extracted

    with patch("app.services.pipeline.get_settings", return_value=settings), patch(
        "app.services.inference.get_openai_client", side_effect=AssertionError("Should not call OpenAI")
    ), patch("app.services.ingestion.extract_document", side_effect=fake_extract), patch(
        "app.services.sanitizer.sanitize_text", return_value=sanitization_result
    ):
        pipeline = DocumentPipeline(repository=repository, indexer=indexer)
        asyncio.run(pipeline._run_pipeline(metadata.document_id))

    processed = repository.get(metadata.document_id)
    assert processed.summary == "Należy zapłacić karę do 7 dni."
    assert processed.obligations == ["Należy zapłacić karę do 7 dni."]
    assert processed.penalties == ["Należy zapłacić karę do 7 dni."]
    assert processed.deadlines == ["Należy zapłacić karę do 7 dni."]
    assert processed.token_usage.prompt_tokens == 0
    assert processed.token_usage.completion_tokens == 0
    assert processed.token_usage.total_tokens == 0
    assert processed.token_usage.cost_usd == 0


def test_answer_question_uses_openai_when_enabled(tmp_path):
    repository, indexer, metadata = _setup_documents(tmp_path)
    settings = DummySettings(data_dir=tmp_path, enable_cloud_llm=True)
    base_text = "To jest sekcja testowa."
    extracted = ExtractedDocument(
        text=base_text,
        sections=[DocumentSection(identifier="section-1", text=base_text)],
    )
    sanitization_result = SanitizationResult(text=base_text, entities={}, secrets={})
    client = DummyOpenAIClient()

    def fake_extract(path):
        return extracted

    with patch("app.services.pipeline.get_settings", return_value=settings), patch(
        "app.services.inference.get_openai_client", return_value=client
    ), patch("app.services.ingestion.extract_document", side_effect=fake_extract), patch(
        "app.services.sanitizer.sanitize_text", return_value=sanitization_result
    ):
        pipeline = DocumentPipeline(repository=repository, indexer=indexer)
        asyncio.run(pipeline._run_pipeline(metadata.document_id))
        answer = asyncio.run(pipeline.answer_question(metadata.document_id, "Jakie są obowiązki?"))

    assert answer.startswith("Odpowiedź z chmury")
    assert any(call[0] == "answer_question" for call in client.calls)


def test_answer_question_uses_heuristics_when_cloud_disabled(tmp_path):
    repository, indexer, metadata = _setup_documents(tmp_path)
    settings = DummySettings(data_dir=tmp_path, enable_cloud_llm=False)
    base_text = "To jest sekcja testowa z obowiązkiem."
    extracted = ExtractedDocument(
        text=base_text,
        sections=[DocumentSection(identifier="section-1", text=base_text)],
    )
    sanitization_result = SanitizationResult(text=base_text, entities={}, secrets={})

    def fake_extract(path):
        return extracted

    with patch("app.services.pipeline.get_settings", return_value=settings), patch(
        "app.services.inference.get_openai_client", side_effect=AssertionError("Should not call OpenAI")
    ), patch("app.services.ingestion.extract_document", side_effect=fake_extract), patch(
        "app.services.sanitizer.sanitize_text", return_value=sanitization_result
    ):
        pipeline = DocumentPipeline(repository=repository, indexer=indexer)
        asyncio.run(pipeline._run_pipeline(metadata.document_id))
        answer = asyncio.run(pipeline.answer_question(metadata.document_id, "Jakie są obowiązki?"))

    assert "heurystycznie" in answer
