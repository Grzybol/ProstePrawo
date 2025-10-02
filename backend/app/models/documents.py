"""Pydantic models describing document lifecycle objects."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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
    pii_entities: dict[str, list[str]] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class DocumentCreateResponse(BaseModel):
    """Response payload for a document upload."""

    document_id: UUID
    status: DocumentProcessingStatus
