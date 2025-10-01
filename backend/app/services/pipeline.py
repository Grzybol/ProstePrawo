"""High-level orchestration of the document processing pipeline."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from fastapi import UploadFile

from ..models.documents import DocumentMetadata, DocumentProcessingStatus


@dataclass
class MetadataStore:
    """In-memory placeholder for document metadata persistence."""

    _documents: dict[UUID, DocumentMetadata]

    def __init__(self) -> None:
        self._documents = {}

    def add_document(self, document: DocumentMetadata) -> None:
        self._documents[document.document_id] = document

    def get_document(self, document_id: UUID) -> DocumentMetadata:
        return self._documents[document_id]

    def list_documents(self) -> list[DocumentMetadata]:
        return list(self._documents.values())


class DocumentPipeline:
    """Orchestrate the ingestion, sanitisation, indexing and inference steps."""

    def __init__(self) -> None:
        self.metadata_store = MetadataStore()

    async def ingest(self, file: UploadFile) -> DocumentMetadata:
        metadata = DocumentMetadata(title=file.filename or "unknown")
        self.metadata_store.add_document(metadata)
        asyncio.create_task(self._run_pipeline(metadata, file))
        return metadata

    async def _run_pipeline(self, metadata: DocumentMetadata, file: UploadFile) -> None:
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
