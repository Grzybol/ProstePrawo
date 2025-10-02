"""High-level orchestration of the document processing pipeline."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from ..core.config import get_settings
from ..models.documents import DocumentMetadata, DocumentProcessingStatus
from ..repositories import DocumentRepository
from . import inference, ingestion, indexing, sanitizer


def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("\\", r"\\\\").replace("(", r"\(").replace(")", r"\)")
    )


def _write_simple_pdf(destination: Path, title: str, body: str) -> None:
    """Persist ``title`` and ``body`` into a lightweight PDF document."""

    combined_parts = [part.strip() for part in (title or "", body or "") if part and part.strip()]
    combined = "\n\n".join(combined_parts)
    lines = combined.splitlines() if combined else [""]
    stream_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        escaped = _escape_pdf_text(line)
        if index == 0:
            stream_lines.append(f"({escaped}) Tj")
        else:
            stream_lines.append("T*")
            stream_lines.append(f"({escaped}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines) + "\n"
    stream_bytes = stream.encode("utf-8")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream_bytes)).encode("utf-8")
        + b" >>\nstream\n"
        + stream_bytes
        + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        handle.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(handle.tell())
            handle.write(f"{index} 0 obj\n".encode("utf-8"))
            handle.write(obj)
            handle.write(b"\nendobj\n")
        xref_offset = handle.tell()
        handle.write(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
        handle.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            handle.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
        handle.write(b"trailer\n")
        handle.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("utf-8"))
        handle.write(b"startxref\n")
        handle.write(f"{xref_offset}\n".encode("utf-8"))
        handle.write(b"%%EOF")


class DocumentNotFoundError(KeyError):
    """Raised when requested document metadata is not present in the store."""

    def __init__(self, document_id: UUID) -> None:
        message = f"Document with id {document_id} was not found"
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
        asyncio.create_task(self._run_pipeline(metadata.document_id))
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

            metadata.sanitized_path = sanitized_path
            metadata.pii_entities = sanitized.entities

            sanitized_sections = await asyncio.to_thread(
                lambda: ingestion.extract_document(sanitized_path).sections
            )
            await asyncio.to_thread(self._indexer.index, document_id, sanitized_sections)

            metadata.summary = inference.build_summary(sanitized.text)
            metadata.obligations = inference.extract_obligations(sanitized.text)
            metadata.penalties = inference.extract_penalties(sanitized.text)
            metadata.deadlines = inference.extract_deadlines(sanitized.text)

            pdf_dir = self._settings.data_dir / str(document_id) / "pdf"
            student_pdf_path = pdf_dir / "student_book.pdf"
            teacher_pdf_path = pdf_dir / "teacher_book.pdf"

            _write_simple_pdf(student_pdf_path, metadata.title, sanitized.text)

            teacher_sections: list[str] = []
            if metadata.summary:
                teacher_sections.append(f"Podsumowanie:\n{metadata.summary}")
            if metadata.obligations:
                teacher_sections.append(
                    "Obowiązki:\n" + "\n".join(metadata.obligations)
                )
            if metadata.penalties:
                teacher_sections.append("Kary:\n" + "\n".join(metadata.penalties))
            if metadata.deadlines:
                teacher_sections.append("Terminy:\n" + "\n".join(metadata.deadlines))
            teacher_sections.append(sanitized.text)

            _write_simple_pdf(
                teacher_pdf_path,
                f"{metadata.title} (wersja nauczycielska)",
                "\n\n".join(teacher_sections),
            )

            metadata.student_book_pdf = student_pdf_path
            metadata.teacher_book_pdf = teacher_pdf_path
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
        answer = inference.answer_question(question, retrieved)
        if answer.sources:
            sources = ", ".join(answer.sources)
            return f"{answer.content} Źródła: {sources}."
        return answer.content

    def iter_documents(self) -> Iterable[DocumentMetadata]:
        return list(self.repository.list())

    def get_document(self, document_id: UUID) -> DocumentMetadata:
        return self._get(document_id)

    def get_student_book(self, document_id: UUID) -> Path:
        metadata = self._get(document_id)
        path = metadata.student_book_pdf
        if path and path.exists():
            return path
        raise FileNotFoundError("Student book PDF not available")

    def get_teacher_book(self, document_id: UUID) -> Path:
        metadata = self._get(document_id)
        path = metadata.teacher_book_pdf
        if path and path.exists():
            return path
        raise FileNotFoundError("Teacher book PDF not available")

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
