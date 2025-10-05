"""High-level orchestration of the document processing pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from fastapi import UploadFile

from ..core.config import get_settings
from ..models.documents import (
    DocumentMetadata,
    DocumentProcessingStatus,
    DocumentUsageMetrics,
    SectionSimplification,
)
from ..repositories import DocumentRepository
from . import exporter, inference, ingestion, sanitizer
from .indexing import SimpleIndexer
from .local_llm import LocalLLMStore
from .openai_client import OpenAIClientError
from .segmenter import SemanticSegmenter


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineEvent:
    """Event emitted after completing a pipeline stage."""

    type: str
    user_id: int
    doc_id: UUID
    payload: dict[str, Any]


@dataclass(slots=True)
class ExportArtefact:
    """Binary representation of an exported document."""

    filename: str
    media_type: str
    content: bytes


class DocumentNotFoundError(KeyError):
    """Raised when requested document metadata is not present in the store."""

    def __init__(self, user_id: int, doc_id: UUID) -> None:
        message = f"Document with id {doc_id} for user {user_id} was not found"
        super().__init__(message)
        self.user_id = user_id
        self.doc_id = doc_id


class DocumentNotReadyError(RuntimeError):
    """Raised when an operation requires a fully processed document."""

    def __init__(self, user_id: int, doc_id: UUID) -> None:
        message = f"Document with id {doc_id} for user {user_id} is not ready"
        super().__init__(message)
        self.user_id = user_id
        self.doc_id = doc_id


class DocumentPipeline:
    """Orchestrate the ingestion, sanitisation, indexing and inference steps."""

    MAX_OPENAI_CONCURRENCY = 8

    def __init__(
        self,
        repository: DocumentRepository | None = None,
        indexer: SimpleIndexer | None = None,
        segmenter: SemanticSegmenter | None = None,
        llm_store: LocalLLMStore | None = None,
    ) -> None:
        self._settings = get_settings()
        self.repository = repository or DocumentRepository()
        self._indexer = indexer or SimpleIndexer()
        self._segmenter = segmenter or SemanticSegmenter()
        self._llm_store = llm_store or LocalLLMStore()
        self._events: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        self._tasks: set[asyncio.Task[None]] = set()
        self._semaphores: dict[int, asyncio.Semaphore] = {}
        self._rehydrate_index()

    async def ingest(self, user_id: int, file: UploadFile) -> DocumentMetadata:
        metadata = DocumentMetadata(user_id=user_id, title=file.filename or "unknown")
        await self._persist_upload(file, metadata)
        self.repository.upsert(metadata)
        await self._emit_event("DocumentQueued", metadata, filename=file.filename)
        task = asyncio.create_task(self._process_document(metadata))
        self._tasks.add(task)
        task.add_done_callback(lambda finished: self._tasks.discard(finished))
        return metadata

    async def _process_document(self, metadata: DocumentMetadata) -> None:
        user_id = metadata.user_id
        doc_id = metadata.doc_id
        try:
            metadata.status = DocumentProcessingStatus.PROCESSING
            self.repository.upsert(metadata)
            await self._emit_event("ProcessingStarted", metadata, title=metadata.title)

            self._llm_store.bootstrap(user_id)

            if metadata.source_path is None:
                raise ValueError("Document source path missing")

            extracted = await asyncio.to_thread(ingestion.extract_document, metadata.source_path)
            base_dir = self._document_dir(user_id, doc_id)
            preprocessed_dir = base_dir / "preprocessed"
            preprocessed_dir.mkdir(parents=True, exist_ok=True)
            raw_text_path = preprocessed_dir / "raw_text.txt"
            raw_text_path.write_text(extracted.text, encoding="utf-8")

            segments = self._segmenter.segment(extracted.sections)
            segments_payload = [segment.to_dict() for segment in segments]
            (preprocessed_dir / "segments.json").write_text(
                json.dumps(segments_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            await self._emit_event("SegmentsGenerated", metadata, count=len(segments))

            sanitized_segments, entities, secrets = sanitizer.sanitize_segments(segments)
            sanitized_dir = base_dir / "sanitized"
            sanitized_dir.mkdir(parents=True, exist_ok=True)
            sanitized_segments_path = sanitized_dir / "segments.json"
            sanitized_segments_payload = [
                {
                    "identifier": segment.identifier,
                    "topic": segment.topic,
                    "text": segment.text,
                    "source_sections": segment.source_sections,
                    "entities": segment.entities,
                }
                for segment in sanitized_segments
            ]
            sanitized_segments_path.write_text(
                json.dumps(sanitized_segments_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            sanitized_text = "\n\n".join(segment["text"] for segment in sanitized_segments_payload)
            sanitized_document_path = sanitized_dir / "document.txt"
            sanitized_document_path.write_text(sanitized_text, encoding="utf-8")

            secure_dir = base_dir / "secure"
            secure_dir.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(secure_dir, 0o700)
            pii_path = secure_dir / "pii_map.json"
            pii_path.write_text(json.dumps(secrets, ensure_ascii=False, indent=2), encoding="utf-8")
            if os.name != "nt":
                os.chmod(pii_path, 0o600)

            metadata.sanitized_path = sanitized_document_path
            metadata.pii_placeholders = entities
            metadata.pii_secret_path = pii_path

            sanitized_sections = [
                ingestion.DocumentSection(identifier=segment.identifier, text=segment.text)
                for segment in sanitized_segments
            ]
            await asyncio.to_thread(
                self._indexer.index, user_id, doc_id, sanitized_sections
            )
            self._llm_store.ingest_segments(user_id, doc_id, sanitized_segments_payload)
            flat_vectors: list[float] = []
            for segment in segments:
                flat_vectors.extend(segment.embedding)
            self._llm_store.store_vectors(user_id, flat_vectors)
            await self._emit_event("IndexUpdated", metadata, sections=len(sanitized_sections))

            use_cloud = self._settings.enable_cloud_llm
            usage_totals = DocumentUsageMetrics()

            summary, summary_usage = await asyncio.to_thread(
                inference.build_summary, sanitized_text, use_cloud
            )
            metadata.summary = summary
            usage_totals.accumulate(summary_usage)

            obligations, obligations_usage = await asyncio.to_thread(
                inference.extract_obligations, sanitized_text, use_cloud
            )
            metadata.obligations = obligations
            usage_totals.accumulate(obligations_usage)

            penalties, penalties_usage = await asyncio.to_thread(
                inference.extract_penalties, sanitized_text, use_cloud
            )
            metadata.penalties = penalties
            usage_totals.accumulate(penalties_usage)

            deadlines, deadlines_usage = await asyncio.to_thread(
                inference.extract_deadlines, sanitized_text, use_cloud
            )
            metadata.deadlines = deadlines
            usage_totals.accumulate(deadlines_usage)

            risks, risks_usage = await asyncio.to_thread(
                inference.extract_risks, sanitized_text, use_cloud
            )
            metadata.risks = risks
            usage_totals.accumulate(risks_usage)

            simplifications, simplify_usage = await self._run_parallel_simplify(
                metadata, sanitized_sections, use_cloud
            )
            metadata.simplified_sections = simplifications
            usage_totals.accumulate(simplify_usage)
            await self._emit_event("SimplificationCompleted", metadata, sections=len(simplifications))

            definitions = await asyncio.to_thread(
                inference.extract_definitions, sanitized_text
            )
            metadata.definitions = definitions

            if usage_totals.total_tokens == 0 and (
                usage_totals.prompt_tokens or usage_totals.completion_tokens
            ):
                usage_totals.total_tokens = (
                    usage_totals.prompt_tokens + usage_totals.completion_tokens
                )
            pricing = self._settings.openai_pricing.get(
                self._settings.openai_model
            ) or self._settings.openai_pricing.get("default", {})
            prompt_rate = float(pricing.get("prompt", 0.0))
            completion_rate = float(pricing.get("completion", 0.0))
            cost = (
                (usage_totals.prompt_tokens / 1000) * prompt_rate
                + (usage_totals.completion_tokens / 1000) * completion_rate
            )
            usage_totals.cost_usd = round(cost, 6)
            metadata.token_usage = usage_totals

            validation = await self._validate_document(metadata, sanitized_segments_payload, simplifications)
            validation_path = secure_dir / "validation.json"
            validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata.extra["validation"] = validation
            if validation["issues"]:
                metadata.extra["needs_review"] = validation["issues"]
                metadata.status = DocumentProcessingStatus.PROCESSING
                await self._emit_event(
                    "ValidationFailed",
                    metadata,
                    issues=validation["issues"],
                )
            else:
                metadata.extra.pop("needs_review", None)
                metadata.status = DocumentProcessingStatus.READY
                await self._emit_event("ValidationPassed", metadata, issues=0)

            self._llm_store.update_context(user_id, "validation", validation)
            self.repository.upsert(metadata)
            await self._emit_event("ProcessingCompleted", metadata, status=metadata.status.value)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.exception("Processing workflow for %s/%s failed: %s", user_id, doc_id, exc)
            metadata.status = DocumentProcessingStatus.FAILED
            metadata.extra["error"] = str(exc)
            self.repository.upsert(metadata)
            await self._emit_event("ProcessingFailed", metadata, error=str(exc))

    async def _run_parallel_simplify(
        self,
        metadata: DocumentMetadata,
        sections: list[ingestion.DocumentSection],
        use_cloud: bool,
    ) -> tuple[list[SectionSimplification], DocumentUsageMetrics]:
        semaphore = self._semaphores.setdefault(
            metadata.user_id, asyncio.Semaphore(self.MAX_OPENAI_CONCURRENCY)
        )
        chunks: list[list[ingestion.DocumentSection]] = []
        current: list[ingestion.DocumentSection] = []
        for section in sections:
            current.append(section)
            if len(current) >= 2:
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)

        async def _simplify_chunk(
            chunk: list[ingestion.DocumentSection],
        ) -> tuple[list[SectionSimplification], DocumentUsageMetrics]:
            async with semaphore:
                result, usage = await asyncio.to_thread(
                    inference.simplify_sections, chunk, use_cloud
                )
            await self._emit_event(
                "SegmentSimplified",
                metadata,
                identifiers=[section.identifier for section in chunk],
            )
            return result, usage

        tasks = [asyncio.create_task(_simplify_chunk(chunk)) for chunk in chunks]
        results = await asyncio.gather(*tasks)
        simplifications: list[SectionSimplification] = []
        total_usage = DocumentUsageMetrics()
        for chunk_result, usage in results:
            simplifications.extend(chunk_result)
            total_usage.accumulate(usage)
        return simplifications, total_usage

    async def _validate_document(
        self,
        metadata: DocumentMetadata,
        sanitized_segments: list[dict[str, Any]],
        simplifications: list[SectionSimplification],
    ) -> dict[str, Any]:
        def _worker() -> dict[str, Any]:
            issues: list[dict[str, str]] = []
            sanitized_map = {
                segment["identifier"]: segment["text"] for segment in sanitized_segments
            }
            for simplification in simplifications:
                text = simplification.plain_language
                if _contains_pii(text):
                    issues.append(
                        {
                            "section_id": simplification.identifier,
                            "reason": "Plain language output appears to contain PII.",
                        }
                    )
                else:
                    original = sanitized_map.get(simplification.identifier, "")
                    if original and any(token in text for token in secrets_tokens(original)):
                        issues.append(
                            {
                                "section_id": simplification.identifier,
                                "reason": "Detected placeholder leakage in simplification.",
                            }
                        )
            return {"issues": issues}

        result = await asyncio.to_thread(_worker)
        return result

    async def answer_question(self, user_id: int, doc_id: UUID, question: str) -> str:
        metadata = self._get(user_id, doc_id)
        if metadata.status != DocumentProcessingStatus.READY:
            logger.info(
                "Document %s/%s not ready for Q&A (status: %s)",
                user_id,
                doc_id,
                metadata.status,
            )
            return "Dokument jest nadal przetwarzany. Spróbuj ponownie później."
        retrieved = await asyncio.to_thread(
            self._indexer.retrieve, user_id, doc_id, question, 3
        )
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
            logger.warning(
                "Falling back to local Q&A for %s/%s due to OpenAI failure",
                user_id,
                doc_id,
                exc_info=True,
            )
            answer = inference.answer_question(question, retrieved, use_cloud=False)
        if answer.sources:
            sources = ", ".join(answer.sources)
            return f"{answer.content} Źródła: {sources}."
        return answer.content

    async def export_document(
        self,
        user_id: int,
        doc_id: UUID,
        format: str = "markdown",
        restore_pii: bool = False,
    ) -> ExportArtefact:
        metadata = self._get(user_id, doc_id)
        if metadata.status != DocumentProcessingStatus.READY:
            raise DocumentNotReadyError(user_id, doc_id)
        normalised = format.lower()
        supported = {"markdown", "pdf", "docx"}
        if normalised not in supported:
            raise ValueError(f"Unsupported export format: {format}")
        if restore_pii and (not metadata.pii_secret_path or not metadata.pii_secret_path.exists()):
            raise ValueError("Original PII mapping is unavailable for this document")
        if normalised == "markdown":
            payload = await asyncio.to_thread(
                exporter.generate_markdown, metadata, restore_pii=restore_pii
            )
            return ExportArtefact(
                filename=f"{doc_id}.md",
                media_type="text/markdown",
                content=payload.encode("utf-8"),
            )
        if normalised == "pdf":
            payload = await asyncio.to_thread(
                exporter.generate_pdf, metadata, restore_pii=restore_pii
            )
            return ExportArtefact(
                filename=f"{doc_id}.pdf",
                media_type="application/pdf",
                content=payload,
            )
        payload = await asyncio.to_thread(
            exporter.generate_docx, metadata, restore_pii=restore_pii
        )
        return ExportArtefact(
            filename=f"{doc_id}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=payload,
        )

    def iter_documents(self, user_id: int) -> Iterable[DocumentMetadata]:
        return list(self.repository.list_for_user(user_id))

    def get_document(self, user_id: int, doc_id: UUID) -> DocumentMetadata:
        return self._get(user_id, doc_id)

    def get_simplified_sections(self, user_id: int, doc_id: UUID) -> list[SectionSimplification]:
        metadata = self._get(user_id, doc_id)
        if metadata.status != DocumentProcessingStatus.READY:
            raise DocumentNotReadyError(user_id, doc_id)
        return list(metadata.simplified_sections)

    def get_document_insights(self, user_id: int, doc_id: UUID) -> dict[str, object]:
        metadata = self._get(user_id, doc_id)
        if metadata.status != DocumentProcessingStatus.READY:
            raise DocumentNotReadyError(user_id, doc_id)
        return {
            "summary": metadata.summary,
            "obligations": list(metadata.obligations),
            "penalties": list(metadata.penalties),
            "deadlines": list(metadata.deadlines),
            "risks": list(metadata.risks),
        }

    def event_queue(self) -> asyncio.Queue[PipelineEvent]:
        return self._events

    async def _emit_event(self, event_type: str, metadata: DocumentMetadata, **payload: Any) -> None:
        event = PipelineEvent(
            type=event_type,
            user_id=metadata.user_id,
            doc_id=metadata.doc_id,
            payload=payload,
        )
        await self._events.put(event)

    async def _persist_upload(self, file: UploadFile, metadata: DocumentMetadata) -> None:
        filename = Path(file.filename).name if file.filename else "document"
        document_dir = self._document_dir(metadata.user_id, metadata.doc_id) / "raw"
        document_dir.mkdir(parents=True, exist_ok=True)
        destination = document_dir / filename
        content = await file.read()
        destination.write_bytes(content)
        metadata.source_path = destination
        await file.close()
        logger.debug(
            "Persisted uploaded file for %s/%s at %s (%d bytes)",
            metadata.user_id,
            metadata.doc_id,
            destination,
            len(content),
        )

    def _rehydrate_index(self) -> None:
        for document in self.repository.list_all():
            if not document.sanitized_path or not document.sanitized_path.exists():
                continue
            extracted = ingestion.extract_document(document.sanitized_path)
            self._indexer.index(document.user_id, document.doc_id, extracted.sections)
            logger.debug("Rehydrated index for %s/%s", document.user_id, document.doc_id)

    def _document_dir(self, user_id: int, doc_id: UUID) -> Path:
        return self._settings.data_dir / str(user_id) / str(doc_id)

    def _get(self, user_id: int, doc_id: UUID) -> DocumentMetadata:
        try:
            return self.repository.get(user_id, doc_id)
        except KeyError as exc:
            raise DocumentNotFoundError(user_id, doc_id) from exc


def _contains_pii(text: str) -> bool:
    from .sanitizer import PII_PATTERNS

    return any(pattern.search(text) for pattern in PII_PATTERNS.values())


def secrets_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in text.split():
        if token.startswith("<") and token.endswith(">"):
            tokens.append(token)
    return tokens
