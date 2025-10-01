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
    extraction using PyMuPDF when available; otherwise we fall back to decoding
    whatever text layer may already be present in the file.
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
    raw_bytes = path.read_bytes()
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1", errors="ignore")


def _split_into_sections(text: str) -> Iterable[DocumentSection]:
    buffer = io.StringIO()
    current_identifier = "section-1"
    index = 1
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            buffer.write("\n")
            continue
        match = _SECTION_PATTERN.match(line)
        if match:
            if buffer.tell() > 0:
                yield DocumentSection(identifier=current_identifier, text=buffer.getvalue().strip())
                buffer = io.StringIO()
            index += 1
            current_identifier = f"section-{index}: {match.group().strip()}"
        buffer.write(line)
        buffer.write("\n")
    if buffer.tell() > 0:
        yield DocumentSection(identifier=current_identifier, text=buffer.getvalue().strip())
