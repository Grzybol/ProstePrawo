"""High-level orchestration of the document processing pipeline."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import UUID

from fastapi import UploadFile

from ..core.config import get_settings
from ..models.documents import DocumentMetadata, DocumentProcessingStatus


class DocumentNotFoundError(KeyError):
    """Raised when requested document metadata is not present in the store."""

    def __init__(self, document_id: UUID) -> None:
        message = f"Document with id {document_id} was not found"
        super().__init__(message)
        self.document_id = document_id


@dataclass
class MetadataStore:
    """In-memory placeholder for document metadata persistence."""

    _documents: dict[UUID, DocumentMetadata]

    def __init__(self) -> None:
        self._documents = {}

    def add_document(self, document: DocumentMetadata) -> None:
        self._documents[document.document_id] = document

    def get_document(self, document_id: UUID) -> DocumentMetadata:
        try:
            return self._documents[document_id]
        except KeyError as exc:
            raise DocumentNotFoundError(document_id) from exc

    def list_documents(self) -> list[DocumentMetadata]:
        return list(self._documents.values())


class DocumentPipeline:
    """Orchestrate the ingestion, sanitisation, indexing and inference steps."""

    def __init__(self) -> None:
        self.metadata_store = MetadataStore()
        self._settings = get_settings()

    async def ingest(self, file: UploadFile) -> DocumentMetadata:
        metadata = DocumentMetadata(title=file.filename or "unknown")
        await self._persist_upload(file, metadata)
        self.metadata_store.add_document(metadata)
        asyncio.create_task(self._run_pipeline(metadata))
        return metadata

    async def _run_pipeline(self, metadata: DocumentMetadata) -> None:
        try:
            metadata.status = DocumentProcessingStatus.PROCESSING
            await asyncio.sleep(0)  # placeholder for heavy work
            metadata.summary = "Streszczenie zostanie wygenerowane w pełnej wersji systemu."
            metadata.status = DocumentProcessingStatus.READY
        except Exception as exc:  # pragma: no cover - placeholder handling
            metadata.status = DocumentProcessingStatus.FAILED
            metadata.extra["error"] = str(exc)

    async def answer_question(self, document_id: UUID, question: str) -> str:
        document = self.metadata_store.get_document(document_id)
        if document.status != DocumentProcessingStatus.READY:
            return "Dokument jest nadal przetwarzany. Spróbuj ponownie później."
        return (
            "Moduł Q&A zostanie podłączony w kolejnych iteracjach. "
            "Obecnie brak jest wygenerowanej odpowiedzi."
        )

    def iter_documents(self) -> Iterable[DocumentMetadata]:
        return self.metadata_store.list_documents()

    async def _persist_upload(self, file: UploadFile, metadata: DocumentMetadata) -> None:
        """Store the incoming file on disk so background tasks can access it."""

        filename = Path(file.filename).name if file.filename else "document"
        document_dir = self._settings.data_dir / str(metadata.document_id) / "raw"
        document_dir.mkdir(parents=True, exist_ok=True)
        destination = document_dir / filename
        content = await file.read()
        destination.write_bytes(content)
        metadata.source_path = destination
        await file.close()
