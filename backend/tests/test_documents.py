"""Integration tests for document API endpoints."""
from __future__ import annotations

import importlib
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

    metadata = documents_module.pipeline.metadata_store.get_document(document_id)
    assert metadata.source_path is not None
    assert metadata.source_path.exists()
    assert metadata.source_path.read_bytes() == payload
    assert metadata.source_path.name == filename

    settings = get_settings()
    assert Path(settings.data_dir) in metadata.source_path.parents
    assert metadata.source_path.parent.name == "raw"
    assert metadata.source_path.parent.parent.name == str(document_id)
