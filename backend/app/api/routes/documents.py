"""Document lifecycle endpoints."""
from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile

from ...models.documents import DocumentCreateResponse, DocumentMetadata
from ...services.pipeline import DocumentNotFoundError, DocumentPipeline

router = APIRouter()

pipeline = DocumentPipeline()


@router.post("/", summary="Upload a document for processing", response_model=DocumentCreateResponse)
async def upload_document(file: UploadFile) -> DocumentCreateResponse:
    """Persist an uploaded file and trigger asynchronous processing."""
    document = await pipeline.ingest(file)
    return DocumentCreateResponse(document_id=document.document_id, status=document.status)


@router.get("/", summary="List processed documents", response_model=list[DocumentMetadata])
async def list_documents() -> Iterable[DocumentMetadata]:
    """Return metadata for all processed documents in the local store."""
    return pipeline.metadata_store.list_documents()


@router.get("/{document_id}", summary="Get metadata for a document", response_model=DocumentMetadata)
async def get_document(document_id: UUID) -> DocumentMetadata:
    """Fetch stored metadata for an individual document."""
    try:
        return pipeline.metadata_store.get_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc


@router.get("/{document_id}/qa", summary="Ask a question about a document")
async def ask_question(document_id: UUID, question: str) -> dict[str, str]:
    """Provide a lightweight placeholder for document Q&A functionality."""
    try:
        answer = await pipeline.answer_question(document_id=document_id, question=question)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return {"answer": answer}
