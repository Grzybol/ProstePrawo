"""Document lifecycle endpoints."""
from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from ...models.documents import (
    DocumentCreateResponse,
    DocumentDefinitionsResponse,
    DocumentMetadataPublic,
    DocumentProcessingStatus,
    DocumentSimplifiedResponse,
    DocumentInsightsResponse,
)
from ...services.pipeline import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    DocumentPipeline,
)

router = APIRouter()

pipeline = DocumentPipeline()


@router.post("/", summary="Upload a document for processing", response_model=DocumentCreateResponse)
async def upload_document(file: UploadFile) -> DocumentCreateResponse:
    """Persist an uploaded file and trigger asynchronous processing."""
    document = await pipeline.ingest(file)
    return DocumentCreateResponse(document_id=document.document_id, status=document.status)


@router.get(
    "/",
    summary="List processed documents",
    response_model=list[DocumentMetadataPublic],
)
async def list_documents() -> Iterable[DocumentMetadataPublic]:
    """Return metadata for all processed documents in the local store."""
    return [document.to_public() for document in pipeline.iter_documents()]


@router.get(
    "/{document_id}",
    summary="Get metadata for a document",
    response_model=DocumentMetadataPublic,
)
async def get_document(document_id: UUID) -> DocumentMetadataPublic:
    """Fetch stored metadata for an individual document."""
    try:
        document = pipeline.get_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return document.to_public()


@router.get("/{document_id}/qa", summary="Ask a question about a document")
async def ask_question(document_id: UUID, question: str) -> dict[str, str]:
    """Provide a lightweight placeholder for document Q&A functionality."""
    try:
        answer = await pipeline.answer_question(document_id=document_id, question=question)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return {"answer": answer}


@router.get(
    "/{document_id}/export",
    summary="Generate a lightweight export for a document",
    response_class=PlainTextResponse,
)
async def export_document(document_id: UUID, format: str = "markdown") -> PlainTextResponse:
    """Return a Markdown representation of the processed document."""

    try:
        content = await pipeline.export_document(document_id=document_id, format=format)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=409, detail="Document is still processing") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media_type = "text/markdown" if format.lower() == "markdown" else "text/plain"
    return PlainTextResponse(content, media_type=media_type)


@router.get(
    "/{document_id}/simplified",
    summary="Retrieve plain-language sections for a document",
    response_model=DocumentSimplifiedResponse,
)
async def get_simplified_document(document_id: UUID) -> DocumentSimplifiedResponse:
    """Return sanitized excerpts paired with simplified explanations."""

    try:
        sections = pipeline.get_simplified_sections(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=409, detail="Document is still processing") from exc
    return DocumentSimplifiedResponse(document_id=document_id, sections=sections)


@router.get(
    "/{document_id}/definitions",
    summary="Retrieve glossary definitions for a document",
    response_model=DocumentDefinitionsResponse,
)
async def get_definitions(document_id: UUID) -> DocumentDefinitionsResponse:
    """Expose extracted legal definitions for the document."""

    try:
        metadata = pipeline.get_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    if metadata.status != DocumentProcessingStatus.READY:
        raise HTTPException(status_code=409, detail="Document is still processing")
    return DocumentDefinitionsResponse(document_id=document_id, definitions=metadata.definitions)


@router.get(
    "/{document_id}/insights",
    summary="Retrieve checklist-style insights for a document",
    response_model=DocumentInsightsResponse,
)
async def get_insights(document_id: UUID) -> DocumentInsightsResponse:
    """Expose summary, obligations, penalties, deadlines and risks for a document."""

    try:
        insights = pipeline.get_document_insights(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=409, detail="Document is still processing") from exc
    return DocumentInsightsResponse(document_id=document_id, **insights)
