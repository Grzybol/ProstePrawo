"""Utilities for generating export artefacts from processed documents."""
from __future__ import annotations

from datetime import datetime
import io
import json
import textwrap
from typing import Iterable
from zipfile import ZipFile, ZIP_DEFLATED

from ..models.documents import DocumentMetadata


def generate_markdown(metadata: DocumentMetadata, *, restore_pii: bool = False) -> str:
    """Return a Markdown report describing ``metadata`` and its findings."""

    replacements = _load_replacements(metadata) if restore_pii else {}
    lines: list[str] = []
    title = metadata.title or "Dokument"
    lines.append(f"# {title}")
    lines.append("")

    created_at = _format_datetime(metadata.created_at)
    lines.append(f"- **ID dokumentu:** `{metadata.doc_id}`")
    lines.append(f"- **Data utworzenia:** {created_at}")
    lines.append(f"- **Status przetwarzania:** {metadata.status.value}")
    lines.append("")
    lines.append(
        "> Niniejsze opracowanie ma charakter informacyjny i nie stanowi porady prawnej."
    )
    lines.append("")

    if metadata.summary:
        summary = metadata.summary.strip()
        if restore_pii:
            summary = _rehydrate(summary, replacements)
        lines.append("## Podsumowanie")
        lines.append("")
        lines.append(summary)
        lines.append("")

    _extend_with_list(lines, "Twoje obowiązki", metadata.obligations, replacements if restore_pii else None)
    _extend_with_list(lines, "Potencjalne kary", metadata.penalties, replacements if restore_pii else None)
    _extend_with_list(lines, "Kluczowe terminy", metadata.deadlines, replacements if restore_pii else None)
    _extend_with_list(lines, "Potencjalne ryzyka", metadata.risks, replacements if restore_pii else None)

    if metadata.definitions:
        lines.append("## Kluczowe definicje")
        lines.append("")
        for definition in metadata.definitions:
            meaning = definition.meaning.strip()
            source = definition.source.strip() if definition.source else None
            if restore_pii:
                meaning = _rehydrate(meaning, replacements)
                if source:
                    source = _rehydrate(source, replacements)
            lines.append(f"### {definition.term}")
            lines.append("")
            lines.append(meaning)
            lines.append("")
            if source:
                lines.append(f"> Źródło: {source}")
                lines.append("")

    if metadata.simplified_sections:
        lines.append("## Uproszczone brzmienie")
        lines.append("")
        for section in metadata.simplified_sections:
            lines.append(f"### {section.identifier}")
            lines.append("")
            excerpt = section.source_excerpt
            plain = section.plain_language.strip()
            if restore_pii:
                excerpt = _rehydrate(excerpt, replacements)
                plain = _rehydrate(plain, replacements)
            if excerpt:
                lines.append(f"> {excerpt}")
                lines.append("")
            lines.append(plain)
            lines.append("")

    if metadata.pii_placeholders:
        lines.append("## Maskowane dane")
        lines.append("")
        for key in sorted(metadata.pii_placeholders):
            placeholders = ", ".join(metadata.pii_placeholders[key]) or "brak"
            lines.append(f"- **{key}:** {placeholders}")
        lines.append("")

    sanitized_text = _read_sanitized_text(metadata)
    if sanitized_text:
        if restore_pii:
            sanitized_text = _rehydrate(sanitized_text, replacements)
        lines.append("## Tekst po anonimizacji")
        lines.append("")
        lines.append("```")
        lines.append(sanitized_text.strip())
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append(
        "Wygenerowano automatycznie przez moduł eksportu ProstePrawo. "
        "Zweryfikuj treść przed dalszym wykorzystaniem."
    )
    return "\n".join(lines).strip() + "\n"


def generate_pdf(metadata: DocumentMetadata, *, restore_pii: bool = False) -> bytes:
    """Render a lightweight PDF file summarising ``metadata``."""

    text = _generate_plaintext(metadata, restore_pii=restore_pii)
    stream = _build_pdf_stream(text)
    return _assemble_pdf(stream)


def generate_docx(metadata: DocumentMetadata, *, restore_pii: bool = False) -> bytes:
    """Produce a DOCX document from ``metadata`` contents."""

    text = _generate_plaintext(metadata, restore_pii=restore_pii)
    document_xml = _build_docx_document_xml(text)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        archive.writestr("_rels/.rels", _DOCX_RELS)
        archive.writestr("docProps/core.xml", _DOCX_CORE)
        archive.writestr("docProps/app.xml", _DOCX_APP)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _generate_plaintext(metadata: DocumentMetadata, *, restore_pii: bool) -> str:
    replacements = _load_replacements(metadata) if restore_pii else {}
    lines: list[str] = []
    title = metadata.title or "Dokument"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    lines.append(f"ID: {metadata.doc_id}")
    lines.append(f"Utworzono: {_format_datetime(metadata.created_at)}")
    lines.append(f"Status: {metadata.status.value}")
    lines.append("")
    summary = metadata.summary.strip() if metadata.summary else ""
    if summary:
        if restore_pii:
            summary = _rehydrate(summary, replacements)
        lines.append("Podsumowanie:")
        lines.append(summary)
        lines.append("")
    _extend_plaintext(lines, "Obowiązki", metadata.obligations, replacements if restore_pii else None)
    _extend_plaintext(lines, "Kary", metadata.penalties, replacements if restore_pii else None)
    _extend_plaintext(lines, "Terminy", metadata.deadlines, replacements if restore_pii else None)
    _extend_plaintext(lines, "Ryzyka", metadata.risks, replacements if restore_pii else None)
    if metadata.simplified_sections:
        lines.append("Sekcje:")
        for section in metadata.simplified_sections:
            excerpt = section.source_excerpt
            plain = section.plain_language
            if restore_pii:
                excerpt = _rehydrate(excerpt, replacements)
                plain = _rehydrate(plain, replacements)
            lines.append(f"- {section.identifier}")
            if excerpt:
                lines.append(f"  Oryginał: {excerpt}")
            lines.append(f"  Uproszczenie: {plain}")
        lines.append("")
    sanitized_text = _read_sanitized_text(metadata)
    if sanitized_text:
        if restore_pii:
            sanitized_text = _rehydrate(sanitized_text, replacements)
        lines.append("Pełny tekst:")
        lines.extend(textwrap.wrap(sanitized_text, width=90))
    return "\n".join(lines).strip()


def _extend_with_list(
    lines: list[str], header: str, items: Iterable[str], replacements: dict[str, str] | None
) -> None:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        return
    lines.append(f"## {header}")
    lines.append("")
    for item in values:
        if replacements:
            item = _rehydrate(item, replacements)
        lines.append(f"- {item}")
    lines.append("")


def _extend_plaintext(
    lines: list[str], header: str, items: Iterable[str], replacements: dict[str, str] | None
) -> None:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        return
    lines.append(f"{header}:")
    for item in values:
        if replacements:
            item = _rehydrate(item, replacements)
        lines.append(f"- {item}")
    lines.append("")


def _read_sanitized_text(metadata: DocumentMetadata) -> str:
    path = metadata.sanitized_path
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _format_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _load_replacements(metadata: DocumentMetadata) -> dict[str, str]:
    path = metadata.pii_secret_path
    if not path or not path.exists():
        return {}
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    replacements: dict[str, str] = {}
    for mapping in content.values():
        for placeholder, value in mapping.items():
            replacements[placeholder] = value
    return replacements


def _rehydrate(text: str, replacements: dict[str, str]) -> str:
    restored = text
    for placeholder, value in replacements.items():
        restored = restored.replace(placeholder, value)
    return restored


def _build_pdf_stream(text: str) -> bytes:
    safe_lines = [line.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)") for line in text.splitlines()]
    commands = ["BT", "/F1 12 Tf", "14 TL", "72 800 Td"]
    for index, line in enumerate(safe_lines):
        if index == 0:
            commands.append(f"({line}) Tj")
        else:
            commands.append("T*")
            commands.append(f"({line}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="ignore")


def _assemble_pdf(stream: bytes) -> bytes:
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = [0]

    def _write_obj(obj_id: int, payload: bytes) -> None:
        offsets.append(buffer.tell())
        buffer.write(f"{obj_id} 0 obj\n".encode("ascii"))
        buffer.write(payload)
        buffer.write(b"\nendobj\n")

    _write_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    _write_obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    _write_obj(
        3,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    )
    content = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
    _write_obj(4, content)
    _write_obj(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    xref_position = buffer.tell()
    buffer.write(b"xref\n0 6\n0000000000 65535 f \n")
    for position in offsets[1:]:
        buffer.write(f"{position:010d} 00000 n \n".encode("ascii"))
    buffer.write(b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n")
    buffer.write(str(xref_position).encode("ascii"))
    buffer.write(b"\n%%EOF")
    return buffer.getvalue()


def _build_docx_document_xml(text: str) -> str:
    paragraphs = []
    for line in text.splitlines() or [""]:
        escaped = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
        paragraphs.append(
            "<w:p><w:r><w:t xml:space=\"preserve\">{}</w:t></w:r></w:p>".format(escaped if escaped else "")
        )
    body = "".join(paragraphs)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        f"<w:body>{body}</w:body></w:document>"
    )


_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

_DOCX_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Eksport dokumentu ProstePrawo</dc:title>
  <dc:creator>ProstePrawo</dc:creator>
  <cp:lastModifiedBy>ProstePrawo</cp:lastModifiedBy>
</cp:coreProperties>
"""

_DOCX_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>ProstePrawo</Application>
</Properties>
"""
