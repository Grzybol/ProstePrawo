"""Utilities for generating export artefacts from processed documents."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..models.documents import DocumentMetadata


def generate_markdown(metadata: DocumentMetadata) -> str:
    """Return a Markdown report describing ``metadata`` and its findings."""

    lines: list[str] = []
    title = metadata.title or "Dokument"
    lines.append(f"# {title}")
    lines.append("")

    created_at = _format_datetime(metadata.created_at)
    lines.append(f"- **ID dokumentu:** `{metadata.document_id}`")
    lines.append(f"- **Data utworzenia:** {created_at}")
    lines.append(f"- **Status przetwarzania:** {metadata.status.value}")
    lines.append("")
    lines.append(
        "> Niniejsze opracowanie ma charakter informacyjny i nie stanowi porady prawnej."
    )
    lines.append("")

    if metadata.summary:
        lines.append("## Podsumowanie")
        lines.append("")
        lines.append(metadata.summary.strip())
        lines.append("")

    _extend_with_list(lines, "Twoje obowiązki", metadata.obligations)
    _extend_with_list(lines, "Potencjalne kary", metadata.penalties)
    _extend_with_list(lines, "Kluczowe terminy", metadata.deadlines)

    if metadata.simplified_sections:
        lines.append("## Uproszczone brzmienie")
        lines.append("")
        for section in metadata.simplified_sections:
            lines.append(f"### {section.identifier}")
            lines.append("")
            if section.source_excerpt:
                lines.append(f"> {section.source_excerpt}")
                lines.append("")
            lines.append(section.plain_language.strip())
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


def _extend_with_list(lines: list[str], header: str, items: Iterable[str]) -> None:
    items = [item.strip() for item in items if item.strip()]
    if not items:
        return
    lines.append(f"## {header}")
    lines.append("")
    for item in items:
        lines.append(f"- {item}")
    lines.append("")


def _read_sanitized_text(metadata: DocumentMetadata) -> str:
    path = metadata.sanitized_path
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _format_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()
