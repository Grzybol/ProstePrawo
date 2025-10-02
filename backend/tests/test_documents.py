"""Integration tests for document API endpoints."""
from __future__ import annotations

import asyncio
import importlib
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_modules(tmp_path, monkeypatch):
    """Provide a configured TestClient and access to the documents module."""

    monkeypatch.setenv("PROSTE_PRAWO_DATA_DIR", str(tmp_path))
    from app.core import config

    config.get_settings.cache_clear()
    documents_module = importlib.reload(importlib.import_module("app.api.routes.documents"))
    main_module = importlib.reload(importlib.import_module("app.main"))
    test_client = TestClient(main_module.app)
    try:
        yield test_client, documents_module
    finally:
        test_client.close()
        config.get_settings.cache_clear()


def test_get_document_missing_returns_404(client_and_modules):
    client, _ = client_and_modules
    missing_id = uuid4()

    response = client.get(f"/documents/{missing_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_upload_persists_file(client_and_modules):
    client, documents_module = client_and_modules
    payload = b"Postanowienia umowne"
    filename = "umowa.txt"

    response = client.post("/documents/", files={"file": (filename, payload, "text/plain")})

    assert response.status_code == 200
    data = response.json()
    document_id = UUID(data["document_id"])

    from app.core.config import get_settings

    metadata = documents_module.pipeline.get_document(document_id)
    assert metadata.source_path is not None
    assert metadata.source_path.exists()
    assert metadata.source_path.read_bytes() == payload
    assert metadata.source_path.name == filename

    settings = get_settings()
    assert Path(settings.data_dir) in metadata.source_path.parents
    assert metadata.source_path.parent.name == "raw"
    assert metadata.source_path.parent.parent.name == str(document_id)


def _wait_for_status(client: TestClient, document_id: UUID, expected: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/documents/{document_id}")
        data = response.json()
        if data["status"] == expected:
            return data
        time.sleep(0.05)
    raise AssertionError(f"Document {document_id} did not reach status {expected} within timeout")


def test_pipeline_generates_metadata_and_answers_questions(client_and_modules):
    client, documents_module = client_and_modules
    payload = (
        "Art. 1. Należy dostarczyć dokumenty w terminie 7 dni.\n"
        "Art. 2. Kara umowna wynosi 5000 zł.\n"
        "Kontakt: biuro@example.com."
    ).encode()
    response = client.post("/documents/", files={"file": ("regulamin.txt", payload, "text/plain")})

    document_id = UUID(response.json()["document_id"])
    data = _wait_for_status(client, document_id, "ready")

    assert data["summary"] is not None
    assert any("termin" in item.lower() for item in data["deadlines"])
    assert any("kara" in item.lower() for item in data["penalties"])
    assert "EMAIL" in " ".join(data["pii_entities"].keys()).upper()

    qa_response = client.get(
        f"/documents/{document_id}/qa",
        params={"question": "Jaka kara grozi za naruszenie?"},
    )
    answer = qa_response.json()["answer"]
    assert "Źródła" in answer


def test_repository_survives_restart(client_and_modules):
    client, documents_module = client_and_modules
    payload = "Art. 1. Strony zobowiązują się do zachowania poufności.".encode("utf-8")
    response = client.post("/documents/", files={"file": ("umowa.txt", payload, "text/plain")})
    document_id = UUID(response.json()["document_id"])
    _wait_for_status(client, document_id, "ready")

    metadata = documents_module.pipeline.get_document(document_id)
    assert metadata.sanitized_path and metadata.sanitized_path.exists()

    # Simulate application restart by creating a fresh pipeline instance
    from app.services.pipeline import DocumentPipeline

    new_pipeline = DocumentPipeline()
    restored = new_pipeline.get_document(document_id)
    assert restored.status == metadata.status
    assert restored.summary == metadata.summary

    answer = asyncio.run(new_pipeline.answer_question(document_id, "Jakie są obowiązki stron?"))
    assert "obowiąz" in answer.lower()


def test_indexing_is_isolated_between_documents(client_and_modules):
    client, _ = client_and_modules

    alpha_payload = (
        "Dokument Alfa.\n"
        "Art. 1. Szczegóły dotyczą wyłącznie procedury Alfa."
    ).encode("utf-8")
    beta_payload = (
        "Dokument Beta.\n"
        "Art. 1. Niniejszy opis skupia się na zadaniach Beta."
    ).encode("utf-8")

    alpha_response = client.post(
        "/documents/",
        files={"file": ("alpha.txt", alpha_payload, "text/plain")},
    )
    beta_response = client.post(
        "/documents/",
        files={"file": ("beta.txt", beta_payload, "text/plain")},
    )

    alpha_id = UUID(alpha_response.json()["document_id"])
    beta_id = UUID(beta_response.json()["document_id"])

    _wait_for_status(client, alpha_id, "ready")
    _wait_for_status(client, beta_id, "ready")

    alpha_answer = client.get(
        f"/documents/{alpha_id}/qa",
        params={"question": "Czego dotyczy procedura Alfa?"},
    ).json()["answer"]
    beta_answer = client.get(
        f"/documents/{beta_id}/qa",
        params={"question": "Czego dotyczy zadanie Beta?"},
    ).json()["answer"]

    assert "Źródła" in alpha_answer
    assert "Źródła" in beta_answer
    assert "Alfa" in alpha_answer
    assert "Beta" in beta_answer
    assert "Alfa" not in beta_answer
