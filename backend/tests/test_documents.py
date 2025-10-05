import importlib
import json
import time
from uuid import UUID

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


@pytest.fixture
def client_and_modules(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PROSTE_PRAWO_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PROSTE_PRAWO_SESSION_SECRET_KEY", "secret")
    monkeypatch.setenv("PROSTE_PRAWO_DISABLE_CLOUDFLARE_TURNSTILE", "1")
    monkeypatch.setenv("PROSTE_PRAWO_ENABLE_CLOUD_LLM", "0")
    monkeypatch.setenv("PROSTE_PRAWO_ENVIRONMENT", "test")

    from app.core import config

    config.get_settings.cache_clear()
    documents_module = importlib.reload(importlib.import_module("app.api.routes.documents"))
    importlib.reload(importlib.import_module("app.api.routes.auth"))
    main_module = importlib.reload(importlib.import_module("app.main"))
    client = TestClient(main_module.app)
    try:
        yield client, documents_module
    finally:
        client.close()
        config.get_settings.cache_clear()


def _register_user(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "Secret123!", "turnstile_token": "ok"},
    )
    assert response.status_code == 201


def _wait_for_status(client: TestClient, doc_id: UUID, expected: str, timeout: float = 6.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/documents/{doc_id}")
        if response.status_code == 200:
            data = response.json()
            if data["status"] == expected:
                return data
        time.sleep(0.05)
    raise AssertionError(f"Document {doc_id} did not reach status {expected} within timeout")


def test_upload_persists_files_per_user(client_and_modules):
    client, documents_module = client_and_modules
    _register_user(client, "alice@example.com")

    payload = (
        b"Art. 1. Dane klienta powinny pozostac poufne. "
        b"Kontakt: biuro@example.com."
    )
    response = client.post(
        "/api/documents/",
        files={"file": ("umowa.txt", payload, "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    doc_id = UUID(data["doc_id"])
    user_id = data["user_id"]

    ready_payload = _wait_for_status(client, doc_id, "ready")
    assert ready_payload["user_id"] == user_id
    assert ready_payload["doc_id"] == str(doc_id)
    assert "simplified_sections" in ready_payload
    assert ready_payload["token_usage"]["total_tokens"] >= 0

    metadata = documents_module.pipeline.get_document(user_id, doc_id)
    assert metadata.source_path is not None and metadata.source_path.exists()
    assert metadata.source_path.parent.name == "raw"
    assert metadata.source_path.parent.parent.name == str(doc_id)
    assert metadata.source_path.parent.parent.parent.name == str(user_id)
    assert metadata.sanitized_path is not None and metadata.sanitized_path.exists()
    assert metadata.pii_secret_path is not None and metadata.pii_secret_path.exists()

    llm_store_root = metadata.sanitized_path.parents[3].parent / "llm_store" / str(user_id)
    assert (llm_store_root / "embeddings.faiss").exists()
    document_store = llm_store_root / "documents" / str(doc_id)
    assert (document_store / "segments.json").exists()

    serialized = json.dumps(ready_payload)
    assert "poufne" in serialized.lower()
    assert all("<" in value for values in ready_payload["pii_placeholders"].values() for value in values)


def test_document_listing_isolated_per_user(client_and_modules):
    client, documents_module = client_and_modules
    _register_user(client, "alpha@example.com")
    first = client.post(
        "/api/documents/",
        files={"file": ("alpha.txt", b"Art. 1. Dane kontaktowe: biuro@example.com", "text/plain")},
    )
    assert first.status_code == 200
    alpha_doc = UUID(first.json()["doc_id"])
    alpha_user = first.json()["user_id"]
    _wait_for_status(client, alpha_doc, "ready")

    listing = client.get("/api/documents/")
    assert listing.status_code == 200
    entries = listing.json()
    assert len(entries) == 1
    assert entries[0]["doc_id"] == str(alpha_doc)

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    _register_user(client, "beta@example.com")
    beta_listing = client.get("/api/documents/")
    assert beta_listing.status_code == 200
    assert beta_listing.json() == []

    missing = client.get(f"/api/documents/{alpha_doc}")
    assert missing.status_code == 404

    metadata = documents_module.pipeline.get_document(alpha_user, alpha_doc)
    assert metadata.user_id == alpha_user


def test_qa_endpoint_requires_ready_status(client_and_modules):
    client, _ = client_and_modules
    _register_user(client, "qa@example.com")
    response = client.post(
        "/api/documents/",
        files={
            "file": (
                "qa.txt",
                "Art. 1. Obowiązki muszą być spełnione.".encode("utf-8"),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    doc_id = UUID(response.json()["doc_id"])

    pending = client.get(f"/api/documents/{doc_id}/qa", params={"question": "Jakie obowiązki?"})
    assert pending.status_code == 200
    assert "przetwarzany" in pending.json()["answer"].lower()

    _wait_for_status(client, doc_id, "ready")
    answer = client.get(f"/api/documents/{doc_id}/qa", params={"question": "Jakie obowiązki?"})
    assert answer.status_code == 200
    assert "Źródła" in answer.json()["answer"]
