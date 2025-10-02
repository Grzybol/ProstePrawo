"""Unit tests for ingestion structure and sanitisation privacy guarantees."""
from __future__ import annotations

import asyncio
import os
import json
import sqlite3
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_section_numbering_starts_at_one(tmp_path):
    from app.services import ingestion

    content = (
        "Art. 1. Pierwszy artykuł.\n"
        "Art. 2. Drugi artykuł."
    )
    path = tmp_path / "ustawa.txt"
    path.write_text(content, encoding="utf-8")

    extracted = ingestion.extract_document(path)

    assert extracted.sections[0].identifier.startswith("section-1")
    assert ": Art. 1" in extracted.sections[0].identifier
    assert extracted.sections[1].identifier.startswith("section-2")


def test_section_numbering_with_preamble(tmp_path):
    from app.services import ingestion

    content = (
        "Preambuła dokumentu.\n"
        "Art. 1. Postanowienia ogólne.\n"
        "Art. 2. Postanowienia końcowe."
    )
    path = tmp_path / "statut.txt"
    path.write_text(content, encoding="utf-8")

    extracted = ingestion.extract_document(path)

    assert extracted.sections[0].identifier.startswith("section-1")
    assert ": Art. 1" in extracted.sections[0].identifier
    assert "Preambuła" in extracted.sections[0].text
    assert extracted.sections[1].identifier.startswith("section-2")


def test_pipeline_persists_only_placeholders(tmp_path, monkeypatch):
    pytest.importorskip("pydantic")
    monkeypatch.setenv("PROSTE_PRAWO_DATA_DIR", str(tmp_path))
    from app.core import config
    from app.models.documents import DocumentMetadata
    from app.services.pipeline import DocumentPipeline

    config.get_settings.cache_clear()
    try:
        pipeline = DocumentPipeline()

        metadata = DocumentMetadata(title="regulamin.txt")
        document_dir = tmp_path / str(metadata.document_id) / "raw"
        document_dir.mkdir(parents=True, exist_ok=True)
        payload = (
            "Art. 1. Termin dostarczenia wynosi 7 dni.\n"
            "Kontakt: biuro@example.com.\n"
            "PESEL: 12345678901."
        )
        source_path = document_dir / "regulamin.txt"
        source_path.write_text(payload, encoding="utf-8")
        metadata.source_path = source_path

        pipeline.repository.upsert(metadata)
        asyncio.run(pipeline._run_pipeline(metadata.document_id))

        processed = pipeline.get_document(metadata.document_id)

        assert processed.pii_placeholders["email"] == ["<EMAIL_1>"]
        assert processed.pii_placeholders["pesel"] == ["<PESEL_1>"]
        assert "biuro@example.com" not in processed.summary

        sanitized_text = processed.sanitized_path.read_text(encoding="utf-8")
        assert "biuro@example.com" not in sanitized_text
        assert "12345678901" not in sanitized_text
        assert "<EMAIL_1>" in sanitized_text
        assert "<PESEL_1>" in sanitized_text

        metadata_db = tmp_path / "metadata.db"
        with sqlite3.connect(metadata_db) as conn:
            row = conn.execute(
                "SELECT payload FROM documents WHERE document_id = ?",
                (str(processed.document_id),),
            ).fetchone()
            assert row is not None
            payload_json = row[0]
        assert "biuro@example.com" not in payload_json
        assert "12345678901" not in payload_json

        secrets_path = Path(processed.pii_secret_path)
        secrets_content = secrets_path.read_text(encoding="utf-8")
        assert "biuro@example.com" in secrets_content
        assert "12345678901" in secrets_content
        placeholders = json.loads(secrets_content)
        assert placeholders["email"]["<EMAIL_1>"] == "biuro@example.com"
        assert placeholders["pesel"]["<PESEL_1>"] == "12345678901"
    finally:
        config.get_settings.cache_clear()


@pytest.mark.skipif(os.name == "nt", reason="Windows does not support POSIX permission checks")
def test_secure_artifacts_have_restrictive_permissions(tmp_path, monkeypatch):
    pytest.importorskip("pydantic")
    monkeypatch.setenv("PROSTE_PRAWO_DATA_DIR", str(tmp_path))
    from app.core import config
    from app.models.documents import DocumentMetadata
    from app.services.pipeline import DocumentPipeline

    config.get_settings.cache_clear()
    try:
        pipeline = DocumentPipeline()

        metadata = DocumentMetadata(title="regulamin.txt")
        document_dir = tmp_path / str(metadata.document_id) / "raw"
        document_dir.mkdir(parents=True, exist_ok=True)
        source_path = document_dir / "regulamin.txt"
        source_path.write_text("Art. 1. Poufne dane.", encoding="utf-8")
        metadata.source_path = source_path

        pipeline.repository.upsert(metadata)
        asyncio.run(pipeline._run_pipeline(metadata.document_id))

        processed = pipeline.get_document(metadata.document_id)
        assert processed.pii_secret_path is not None
        secure_dir = processed.pii_secret_path.parent

        dir_mode = secure_dir.stat().st_mode & 0o777
        file_mode = processed.pii_secret_path.stat().st_mode & 0o777

        assert dir_mode == 0o700
        assert file_mode == 0o600
    finally:
        config.get_settings.cache_clear()
