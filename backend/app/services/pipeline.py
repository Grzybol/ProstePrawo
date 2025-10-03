"""High-level orchestration of the document processing pipeline."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from ..core.config import get_settings
from ..models.documents import (
    DocumentMetadata,
    DocumentProcessingStatus,
    SectionSimplification,
)
from ..repositories import DocumentRepository
from . import exporter, inference, ingestion, indexing, sanitizer
from .openai_client import OpenAIClientError


@dataclass(slots=True)
class ExportArtefact:
    """Binary representation of an exported document."""

    filename: str
    media_type: str
    content: bytes


class DocumentNotFoundError(KeyError):
    """Raised when requested document metadata is not present in the store."""

    def __init__(self, document_id: UUID) -> None:
        message = f"Document with id {document_id} was not found"
        super().__init__(message)
        self.document_id = document_id


class DocumentNotReadyError(RuntimeError):
    """Raised when an operation requires a fully processed document."""

    def __init__(self, document_id: UUID) -> None:
        message = f"Document with id {document_id} is not ready"
        super().__init__(message)
        self.document_id = document_id


class DocumentPipeline:
    """Orchestrate the ingestion, sanitisation, indexing and inference steps."""

    def __init__(
        self,
        repository: DocumentRepository | None = None,
        indexer: indexing.SimpleIndexer | None = None,
    ) -> None:
        self._settings = get_settings()
        self.repository = repository or DocumentRepository()
        self._indexer = indexer or indexing.SimpleIndexer()
        self._rehydrate_index()

    async def ingest(self, file: UploadFile) -> DocumentMetadata:
        metadata = DocumentMetadata(title=file.filename or "unknown")
        await self._persist_upload(file, metadata)
        self.repository.upsert(metadata)
        loop = asyncio.get_running_loop()

        def _runner() -> None:
            asyncio.run(self._run_pipeline(metadata.document_id))

        loop.run_in_executor(None, _runner)
        return metadata

    async def _run_pipeline(self, document_id: UUID) -> None:
        try:
            metadata = self._get(document_id)
            metadata.status = DocumentProcessingStatus.PROCESSING
            self.repository.upsert(metadata)

            if metadata.source_path is None:
                raise ValueError("Document source path missing")

            extracted = await asyncio.to_thread(ingestion.extract_document, metadata.source_path)
            sanitized = await asyncio.to_thread(sanitizer.sanitize_text, extracted.text)

            sanitized_dir = self._settings.data_dir / str(document_id) / "sanitized"
            sanitized_dir.mkdir(parents=True, exist_ok=True)
            sanitized_path = sanitized_dir / "document.txt"
            sanitized_path.write_text(sanitized.text, encoding="utf-8")

            secure_dir = self._settings.data_dir / str(document_id) / "secure"
            secure_dir.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(secure_dir, 0o700)
            secrets_path = secure_dir / "pii_map.json"
            secrets_path.write_text(
                json.dumps(sanitized.secrets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if os.name != "nt":
                os.chmod(secrets_path, 0o600)

            metadata.sanitized_path = sanitized_path
            metadata.pii_placeholders = sanitized.entities
            metadata.pii_secret_path = secrets_path

            sanitized_sections = await asyncio.to_thread(
                lambda: ingestion.extract_document(sanitized_path).sections
            )
            await asyncio.to_thread(self._indexer.index, document_id, sanitized_sections)

            use_cloud = self._settings.enable_cloud_llm
            try:
                metadata.summary = inference.build_summary(sanitized.text, use_cloud=use_cloud)
                metadata.obligations = inference.extract_obligations(sanitized.text, use_cloud=use_cloud)
                metadata.penalties = inference.extract_penalties(sanitized.text, use_cloud=use_cloud)
                metadata.deadlines = inference.extract_deadlines(sanitized.text, use_cloud=use_cloud)
                metadata.risks = inference.extract_risks(sanitized.text, use_cloud=use_cloud)
                metadata.simplified_sections = inference.simplify_sections(
                    sanitized_sections, use_cloud=use_cloud
                )
            except OpenAIClientError:
                metadata.summary = inference.build_summary(sanitized.text, use_cloud=False)
                metadata.obligations = inference.extract_obligations(sanitized.text, use_cloud=False)
                metadata.penalties = inference.extract_penalties(sanitized.text, use_cloud=False)
                metadata.deadlines = inference.extract_deadlines(sanitized.text, use_cloud=False)
                metadata.risks = inference.extract_risks(sanitized.text, use_cloud=False)
                metadata.simplified_sections = inference.simplify_sections(
                    sanitized_sections, use_cloud=False
                )
            metadata.definitions = inference.extract_definitions(sanitized.text)
            metadata.status = DocumentProcessingStatus.READY
            self.repository.upsert(metadata)
        except Exception as exc:  # pragma: no cover - defensive path
            metadata = self._get(document_id)
            metadata.status = DocumentProcessingStatus.FAILED
            metadata.extra["error"] = str(exc)
            self.repository.upsert(metadata)

    async def answer_question(self, document_id: UUID, question: str) -> str:
        metadata = self._get(document_id)
        if metadata.status != DocumentProcessingStatus.READY:
            return "Dokument jest nadal przetwarzany. Spróbuj ponownie później."
        retrieved = await asyncio.to_thread(self._indexer.retrieve, document_id, question, 3)
        if not retrieved and metadata.obligations:
            obligations = "; ".join(metadata.obligations[:3])
            return (
                "Na podstawie zapisanych obowiązków dokument wskazuje: "
                f"{obligations}"
            )
        use_cloud = self._settings.enable_cloud_llm
        try:
            answer = inference.answer_question(question, retrieved, use_cloud=use_cloud)
        except OpenAIClientError:
            answer = inference.answer_question(question, retrieved, use_cloud=False)
        if answer.sources:
            sources = ", ".join(answer.sources)
            return f"{answer.content} Źródła: {sources}."
        return answer.content

    async def export_document(
        self,
        document_id: UUID,
        format: str = "markdown",
        restore_pii: bool = False,
    ) -> ExportArtefact:
        """Generate an export artefact for ``document_id`` in the given ``format``."""

        metadata = self._get(document_id)
        if metadata.status != DocumentProcessingStatus.READY:
            raise DocumentNotReadyError(document_id)

        normalised = format.lower()
        supported = {"markdown", "pdf", "docx"}
        if normalised not in supported:
            raise ValueError(f"Unsupported export format: {format}")

        if restore_pii and (not metadata.pii_secret_path or not metadata.pii_secret_path.exists()):
            raise ValueError("Original PII mapping is unavailable for this document")

        if normalised == "markdown":
            payload = await asyncio.to_thread(exporter.generate_markdown, metadata, restore_pii=restore_pii)
            return ExportArtefact(
                filename=f"{document_id}.md",
                media_type="text/markdown",
                content=payload.encode("utf-8"),
            )
        if normalised == "pdf":
            payload = await asyncio.to_thread(exporter.generate_pdf, metadata, restore_pii=restore_pii)
            return ExportArtefact(
                filename=f"{document_id}.pdf",
                media_type="application/pdf",
                content=payload,
            )

        payload = await asyncio.to_thread(exporter.generate_docx, metadata, restore_pii=restore_pii)
        return ExportArtefact(
            filename=f"{document_id}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=payload,
        )

    def iter_documents(self) -> Iterable[DocumentMetadata]:
        return list(self.repository.list())

    def get_document(self, document_id: UUID) -> DocumentMetadata:
        return self._get(document_id)

    def get_simplified_sections(self, document_id: UUID) -> list[SectionSimplification]:
        metadata = self._get(document_id)
        if metadata.status != DocumentProcessingStatus.READY:
            raise DocumentNotReadyError(document_id)
        return list(metadata.simplified_sections)

    def get_document_insights(self, document_id: UUID) -> dict[str, object]:
        metadata = self._get(document_id)
        if metadata.status != DocumentProcessingStatus.READY:
            raise DocumentNotReadyError(document_id)
        return {
            "summary": metadata.summary,
            "obligations": list(metadata.obligations),
            "penalties": list(metadata.penalties),
            "deadlines": list(metadata.deadlines),
            "risks": list(metadata.risks),
        }

    async def _persist_upload(self, file: UploadFile, metadata: DocumentMetadata) -> None:
        filename = Path(file.filename).name if file.filename else "document"
        document_dir = self._settings.data_dir / str(metadata.document_id) / "raw"
        document_dir.mkdir(parents=True, exist_ok=True)
        destination = document_dir / filename
        content = await file.read()
        destination.write_bytes(content)
        metadata.source_path = destination
        await file.close()

    def _rehydrate_index(self) -> None:
        for document in self.repository.list():
            if not document.sanitized_path or not document.sanitized_path.exists():
                continue
            extracted = ingestion.extract_document(document.sanitized_path)
            self._indexer.index(document.document_id, extracted.sections)

    def _get(self, document_id: UUID) -> DocumentMetadata:
        try:
            return self.repository.get(document_id)
        except KeyError as exc:
            raise DocumentNotFoundError(document_id) from exc
