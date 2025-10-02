"""Document lifecycle endpoints."""
from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

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
    return pipeline.iter_documents()


@router.get("/{document_id}", summary="Get metadata for a document", response_model=DocumentMetadata)
async def get_document(document_id: UUID) -> DocumentMetadata:
    """Fetch stored metadata for an individual document."""
    try:
        return pipeline.get_document(document_id)
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


@router.get("/{document_id}/student-book", summary="Download the student PDF")
async def download_student_book(document_id: UUID) -> FileResponse:
    try:
        path = pipeline.get_student_book(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/{document_id}/teacher-book", summary="Download the teacher PDF")
async def download_teacher_book(document_id: UUID) -> FileResponse:
    try:
        path = pipeline.get_teacher_book(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name)
