"""SQLite-backed repository for document metadata."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import UUID

from ..core.config import get_settings
from ..models.documents import DocumentMetadata, DocumentProcessingStatus


class DocumentRepository:
    """Persist :class:`DocumentMetadata` instances in SQLite."""

    def __init__(self, db_path: Path | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or settings.data_dir / "metadata.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def upsert(self, document: DocumentMetadata) -> None:
        payload = json.dumps(_serialize_document(document))
        with self._connect() as conn:
            conn.execute(
                "REPLACE INTO documents (document_id, payload) VALUES (?, ?)",
                (str(document.document_id), payload),
            )

    def get(self, document_id: UUID) -> DocumentMetadata:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM documents WHERE document_id = ?", (str(document_id),)
            ).fetchone()
        if row is None:
            raise KeyError(str(document_id))
        data = json.loads(row["payload"])
        return _deserialize_document(data)

    def list(self) -> Iterable[DocumentMetadata]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM documents ORDER BY json_extract(payload, '$.created_at')").fetchall()
        for row in rows:
            yield _deserialize_document(json.loads(row["payload"]))


def _serialize_document(document: DocumentMetadata) -> dict:
    data = document.dict()
    data["document_id"] = str(document.document_id)
    data["created_at"] = document.created_at.isoformat()
    data["status"] = document.status.value
    for path_key in ("source_path", "sanitized_path"):
        value = data.get(path_key)
        if value is not None:
            data[path_key] = str(value)
    return data


def _deserialize_document(data: dict) -> DocumentMetadata:
    parsed = data.copy()
    parsed["document_id"] = UUID(parsed["document_id"])
    parsed["created_at"] = datetime.fromisoformat(parsed["created_at"])
    parsed["status"] = DocumentProcessingStatus(parsed["status"])
    for path_key in ("source_path", "sanitized_path"):
        value = parsed.get(path_key)
        if value:
            parsed[path_key] = Path(value)
    return DocumentMetadata(**parsed)
