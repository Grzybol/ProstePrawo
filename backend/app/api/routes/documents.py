"""Document lifecycle endpoints."""
from collections.abc import Iterable
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response

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

logger = logging.getLogger(__name__)

router = APIRouter()

pipeline = DocumentPipeline()


@router.post("/", summary="Upload a document for processing", response_model=DocumentCreateResponse)
async def upload_document(file: UploadFile) -> DocumentCreateResponse:
    """Persist an uploaded file and trigger asynchronous processing."""
    logger.info("Received upload request for %s", file.filename)
    document = await pipeline.ingest(file)
    logger.info("Document %s accepted for processing", document.document_id)
    return DocumentCreateResponse(document_id=document.document_id, status=document.status)


@router.get(
    "/",
    summary="List processed documents",
    response_model=list[DocumentMetadataPublic],
)
async def list_documents() -> Iterable[DocumentMetadataPublic]:
    """Return metadata for all processed documents in the local store."""
    logger.debug("Listing processed documents")
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
        logger.warning("Requested metadata for missing document %s", document_id)
        raise HTTPException(status_code=404, detail="Document not found") from exc
    logger.debug("Returning metadata for %s", document_id)
    return document.to_public()


@router.get("/{document_id}/qa", summary="Ask a question about a document")
async def ask_question(document_id: UUID, question: str) -> dict[str, str]:
    """Provide a lightweight placeholder for document Q&A functionality."""
    logger.info("Received Q&A request for %s", document_id)
    try:
        answer = await pipeline.answer_question(document_id=document_id, question=question)
    except DocumentNotFoundError as exc:
        logger.warning("Q&A requested for missing document %s", document_id)
        raise HTTPException(status_code=404, detail="Document not found") from exc
    logger.debug("Returning Q&A response for %s", document_id)
    return {"answer": answer}


@router.get(
    "/{document_id}/export",
    summary="Generate a lightweight export for a document",
)
async def export_document(
    document_id: UUID, format: str = "markdown", restore_pii: bool = False
) -> Response:
    """Return a Markdown representation of the processed document."""

    try:
        artefact = await pipeline.export_document(
            document_id=document_id, format=format, restore_pii=restore_pii
        )
    except DocumentNotFoundError as exc:
        logger.warning("Export requested for missing document %s", document_id)
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except DocumentNotReadyError as exc:
        logger.info("Export requested for processing document %s", document_id)
        raise HTTPException(status_code=409, detail="Document is still processing") from exc
    except ValueError as exc:
        logger.warning(
            "Export request for %s failed due to invalid input: %s", document_id, exc
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    headers = {
        "Content-Disposition": f'attachment; filename="{artefact.filename}"'
    }
    if artefact.media_type.startswith("text/"):
        return PlainTextResponse(artefact.content.decode("utf-8"), media_type=artefact.media_type, headers=headers)
    return Response(content=artefact.content, media_type=artefact.media_type, headers=headers)


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
        logger.warning("Simplified view requested for missing document %s", document_id)
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except DocumentNotReadyError as exc:
        logger.info("Simplified view requested for processing document %s", document_id)
        raise HTTPException(status_code=409, detail="Document is still processing") from exc
    logger.debug("Returning simplified sections for %s", document_id)
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
        logger.warning("Definitions requested for missing document %s", document_id)
        raise HTTPException(status_code=404, detail="Document not found") from exc
    if metadata.status != DocumentProcessingStatus.READY:
        logger.info("Definitions requested for processing document %s", document_id)
        raise HTTPException(status_code=409, detail="Document is still processing")
    logger.debug("Returning definitions for %s", document_id)
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
        logger.warning("Insights requested for missing document %s", document_id)
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except DocumentNotReadyError as exc:
        logger.info("Insights requested for processing document %s", document_id)
        raise HTTPException(status_code=409, detail="Document is still processing") from exc
    logger.debug("Returning insights for %s", document_id)
    return DocumentInsightsResponse(document_id=document_id, **insights)
