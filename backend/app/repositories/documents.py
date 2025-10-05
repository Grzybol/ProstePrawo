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
                    user_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (user_id, doc_id)
                )
                """
            )

    def upsert(self, document: DocumentMetadata) -> None:
        payload = json.dumps(_serialize_document(document))
        with self._connect() as conn:
            conn.execute(
                "REPLACE INTO documents (user_id, doc_id, payload) VALUES (?, ?, ?)",
                (str(document.user_id), str(document.doc_id), payload),
            )

    def get(self, user_id: int, doc_id: UUID) -> DocumentMetadata:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM documents WHERE user_id = ? AND doc_id = ?",
                (str(user_id), str(doc_id)),
            ).fetchone()
        if row is None:
            raise KeyError(f"{user_id}:{doc_id}")
        data = json.loads(row["payload"])
        return _deserialize_document(data)

    def list_for_user(self, user_id: int) -> Iterable[DocumentMetadata]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM documents WHERE user_id = ? ORDER BY json_extract(payload, '$.created_at')",
                (str(user_id),),
            ).fetchall()
        for row in rows:
            yield _deserialize_document(json.loads(row["payload"]))

    def list_all(self) -> Iterable[DocumentMetadata]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM documents ORDER BY json_extract(payload, '$.created_at')"
            ).fetchall()
        for row in rows:
            yield _deserialize_document(json.loads(row["payload"]))


def _serialize_document(document: DocumentMetadata) -> dict:
    data = document.dict()
    data["user_id"] = int(document.user_id)
    data["doc_id"] = str(document.doc_id)
    data["created_at"] = document.created_at.isoformat()
    data["status"] = document.status.value
    for path_key in ("source_path", "sanitized_path", "pii_secret_path"):
        value = data.get(path_key)
        if value is not None:
            data[path_key] = str(value)
    return data


def _deserialize_document(data: dict) -> DocumentMetadata:
    parsed = data.copy()
    parsed["user_id"] = int(parsed["user_id"])
    parsed["doc_id"] = UUID(parsed["doc_id"])
    parsed["created_at"] = datetime.fromisoformat(parsed["created_at"])
    parsed["status"] = DocumentProcessingStatus(parsed["status"])
    for path_key in ("source_path", "sanitized_path", "pii_secret_path"):
        value = parsed.get(path_key)
        if value:
            parsed[path_key] = Path(value)
    return DocumentMetadata(**parsed)
