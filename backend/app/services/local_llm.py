"""Utilities managing per-user local LLM context stores."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from ..core.config import get_settings


class LocalLLMStore:
    """Persist lightweight context required by the local LLM runtime."""

    def __init__(self, base_dir: Path | None = None) -> None:
        settings = get_settings()
        self._base_dir = base_dir or settings.data_dir.parent / "llm_store"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def bootstrap(self, user_id: int) -> Path:
        """Ensure that the directory structure for ``user_id`` exists."""

        user_dir = self._base_dir / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        documents_dir = user_dir / "documents"
        documents_dir.mkdir(exist_ok=True)

        embeddings_path = user_dir / "embeddings.faiss"
        vectors_path = user_dir / "vectors.json"
        feedback_path = user_dir / "feedback.json"

        if not embeddings_path.exists():
            embeddings_path.write_bytes(b"")
        if not vectors_path.exists():
            vectors_path.write_text("[]", encoding="utf-8")
        if not feedback_path.exists():
            feedback_path.write_text("[]", encoding="utf-8")
        return user_dir

    def ingest_segments(self, user_id: int, doc_id: Path | str, segments: list[dict]) -> None:
        """Persist sanitized segments for later retrieval by the LLM."""

        user_dir = self.bootstrap(user_id)
        doc_dir = user_dir / "documents" / str(doc_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        segments_path = doc_dir / "segments.json"
        segments_path.write_text(json.dumps(list(segments), ensure_ascii=False, indent=2), encoding="utf-8")

    def update_context(self, user_id: int, channel: str, payload: dict | list | str) -> None:
        """Append feedback or validation artefacts to the user context history."""

        user_dir = self.bootstrap(user_id)
        feedback_path = user_dir / "feedback.json"
        existing: list[dict] = []
        if feedback_path.exists():
            try:
                existing = json.loads(feedback_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = []
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "channel": channel,
            "payload": payload,
        }
        existing.append(entry)
        feedback_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    def store_vectors(self, user_id: int, vectors: list[float]) -> None:
        """Persist embedding vectors computed during indexing."""

        user_dir = self.bootstrap(user_id)
        vectors_path = user_dir / "vectors.json"
        vectors_path.write_text(json.dumps(vectors, ensure_ascii=False, indent=2), encoding="utf-8")
