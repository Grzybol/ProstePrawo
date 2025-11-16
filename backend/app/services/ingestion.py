"""Utilities for extracting structured text from uploaded documents."""
from __future__ import annotations

from dataclasses import dataclass
import io
import re
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class DocumentSection:
    """Representation of a logical fragment of the source document."""

    identifier: str
    text: str


@dataclass(slots=True)
class ExtractedDocument:
    """Return object containing the raw text and detected sections."""

    text: str
    sections: list[DocumentSection]


_SECTION_PATTERN = re.compile(r"^(Art\.|§|Rozdział|Ust\.)[\w .-]*", re.IGNORECASE)


def extract_document(path: Path) -> ExtractedDocument:
    """Extract text from ``path`` and create lightweight structural segments.

    The implementation purposefully keeps the logic conservative so that it can
    operate in the test environment without heavyweight OCR dependencies.  For
    plain-text sources we simply decode the bytes using UTF-8 with fallback to
    latin-1.  For binary formats such as PDF we attempt a best-effort text
    extraction using PyMuPDF when available, fall back to PyPDF2 when it is
    installed, and only decode raw bytes if both strategies fail.
    """

    content = _read_text(path)
    sections = list(_split_into_sections(content))
    if not sections:
        sections = [DocumentSection(identifier="section-1", text=content.strip())]
    return ExtractedDocument(text=content, sections=sections)


def _read_text(path: Path) -> str:
    if path.suffix.lower() in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".pdf":
        try:  # pragma: no cover - exercised only when PyMuPDF is installed
            import fitz

            doc = fitz.open(path)
            try:
                return "\n".join(page.get_text("text") for page in doc)
            finally:
                doc.close()
        except Exception:  # pragma: no cover - import and runtime fallback
            pass
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(path))
            text_chunks: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text_chunks.append(page_text.strip())
            if text_chunks:
                return "\n".join(text_chunks)
            return ""
        except Exception:
            pass
    raw_bytes = path.read_bytes()
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1", errors="ignore")


def _split_into_sections(text: str) -> Iterable[DocumentSection]:
    buffer = io.StringIO()
    current_label: str | None = None
    emitted = 0

    def emit_section(content: str, label: str | None) -> Iterable[DocumentSection]:
        nonlocal emitted
        stripped = content.strip()
        if not stripped:
            return []
        emitted += 1
        identifier = f"section-{emitted}"
        if label:
            identifier = f"{identifier}: {label}"
        return [DocumentSection(identifier=identifier, text=stripped)]

    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            buffer.write("\n")
            continue
        match = _SECTION_PATTERN.match(line)
        if match:
            content = buffer.getvalue()
            if content and (emitted > 0 or current_label is not None):
                for section in emit_section(content, current_label):
                    yield section
                buffer = io.StringIO()
            elif content:
                # Preserve leading preambles inside the first labelled section.
                buffer = io.StringIO()
                buffer.write(content)
            else:
                buffer = io.StringIO()
            current_label = match.group().strip()
        buffer.write(line)
        buffer.write("\n")
    content = buffer.getvalue()
    if content:
        for section in emit_section(content, current_label):
            yield section
