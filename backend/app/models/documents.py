"""Pydantic models describing document lifecycle objects."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SectionSimplification(BaseModel):
    """Plain-language representation of a document fragment."""

    identifier: str
    source_excerpt: str
    plain_language: str


class DocumentDefinition(BaseModel):
    """Definition of a legal term detected in the source material."""

    term: str
    meaning: str
    source: str | None = None


class DocumentSimplifiedResponse(BaseModel):
    """Payload returned for simplified document views."""

    document_id: UUID
    sections: list[SectionSimplification] = Field(default_factory=list)


class DocumentProcessingStatus(str, Enum):
    """Enumerate the high-level processing states for documents."""

    RECEIVED = "received"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    """Persisted metadata tracked for each document."""

    document_id: UUID = Field(default_factory=uuid4)
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: DocumentProcessingStatus = DocumentProcessingStatus.RECEIVED
    source_path: Path | None = None
    sanitized_path: Path | None = None
    summary: str | None = None
    obligations: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    deadlines: list[str] = Field(default_factory=list)
    pii_placeholders: dict[str, list[str]] = Field(default_factory=dict)
    pii_secret_path: Path | None = None
    simplified_sections: list[SectionSimplification] = Field(default_factory=list)
    definitions: list[DocumentDefinition] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_public(self) -> "DocumentMetadataPublic":
        """Expose a sanitized view suitable for API responses."""

        return DocumentMetadataPublic(
            document_id=self.document_id,
            title=self.title,
            created_at=self.created_at,
            status=self.status,
            summary=self.summary,
            obligations=list(self.obligations),
            penalties=list(self.penalties),
            deadlines=list(self.deadlines),
            pii_placeholders=dict(self.pii_placeholders),
            simplified_sections=list(self.simplified_sections),
            definitions=list(self.definitions),
            extra=dict(self.extra),
        )


class DocumentMetadataPublic(BaseModel):
    """Subset of metadata fields safe to return to API consumers."""

    document_id: UUID
    title: str
    created_at: datetime
    status: DocumentProcessingStatus
    summary: str | None = None
    obligations: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    deadlines: list[str] = Field(default_factory=list)
    pii_placeholders: dict[str, list[str]] = Field(default_factory=dict)
    simplified_sections: list[SectionSimplification] = Field(default_factory=list)
    definitions: list[DocumentDefinition] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class DocumentCreateResponse(BaseModel):
    """Response payload for a document upload."""

    document_id: UUID
    status: DocumentProcessingStatus


class DocumentDefinitionsResponse(BaseModel):
    """Response payload for the definitions endpoint."""

    document_id: UUID
    definitions: list[DocumentDefinition] = Field(default_factory=list)
