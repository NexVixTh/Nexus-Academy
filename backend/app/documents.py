import sqlite3
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.answering import (
    Answerer,
    CitationValidationError,
    QuotedEvidenceAnswerer,
    validate_citations,
)
from app.ingestion import (
    InvalidDocumentError,
    UnsupportedDocumentError,
    extract_document,
)
from app.retrieval import DocumentNotFoundError, normalize_query, search_document
from app.storage import get_database_path, save_document


MAX_UPLOAD_SIZE = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

router = APIRouter()


class IngestionResponse(BaseModel):
    document_id: str
    pages_or_slides_processed: int
    records_created: int


class SearchResultResponse(BaseModel):
    document_id: str
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    excerpt: str
    score: float


class DocumentSearchResponse(BaseModel):
    document_id: str
    results: list[SearchResultResponse]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def require_non_blank_question(cls, question: str) -> str:
        if not question.strip():
            raise ValueError("Question must not be blank.")
        return question.strip()


class CitationResponse(BaseModel):
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    excerpt: str


class AskResponse(BaseModel):
    document_id: str
    question: str
    answer: str
    citations: list[CitationResponse]
    abstained: bool
    abstention_reason: str | None


ANSWERER: Answerer = QuotedEvidenceAnswerer()


@router.post("/documents", response_model=IngestionResponse, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File(description="A PDF or PPTX document")],
) -> IngestionResponse:
    try:
        original_filename = file.filename
        if not original_filename:
            raise HTTPException(status_code=400, detail="A filename is required.")

        extension = Path(original_filename).suffix.lower()
        content_type = CONTENT_TYPES.get(extension)
        if content_type is None:
            raise HTTPException(status_code=415, detail="Only PDF and PPTX files are supported.")

        with tempfile.TemporaryDirectory(prefix="nexus-academy-upload-") as temporary_directory:
            temporary_path = Path(temporary_directory) / f"{uuid4().hex}{extension}"
            total_bytes = 0
            with temporary_path.open("xb") as destination:
                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail="The upload exceeds the 20 MB size limit.",
                        )
                    destination.write(chunk)

            if total_bytes == 0:
                raise HTTPException(status_code=400, detail="The uploaded file is empty.")

            try:
                records = extract_document(temporary_path, extension)
            except UnsupportedDocumentError as exc:
                raise HTTPException(status_code=415, detail=str(exc)) from exc
            except InvalidDocumentError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            try:
                document_id = save_document(
                    get_database_path(), original_filename, content_type, records
                )
            except sqlite3.Error as exc:
                raise HTTPException(
                    status_code=500,
                    detail="The document could not be stored.",
                ) from exc

            return IngestionResponse(
                document_id=document_id,
                pages_or_slides_processed=len(records),
                records_created=len(records),
            )
    finally:
        await file.close()


@router.get("/documents/{document_id}/search", response_model=DocumentSearchResponse)
def search_document_endpoint(
    document_id: str,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
) -> DocumentSearchResponse:
    if not normalize_query(q):
        raise HTTPException(
            status_code=422,
            detail="Query must contain at least one searchable term.",
        )

    try:
        matches = search_document(get_database_path(), document_id, q, limit)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Search storage is unavailable.") from exc

    return DocumentSearchResponse(
        document_id=document_id,
        results=[
            SearchResultResponse(
                document_id=match.document_id,
                source_record_id=match.source_record_id,
                source_type=match.source_type,
                page_or_slide_number=match.page_or_slide_number,
                excerpt=match.excerpt,
                score=match.score,
            )
            for match in matches
        ],
    )


@router.post("/documents/{document_id}/ask", response_model=AskResponse)
def ask_document_endpoint(document_id: str, request: AskRequest) -> AskResponse:
    database_path = get_database_path()
    question = request.question

    try:
        evidence = search_document(database_path, document_id, question, limit=5)
        answer_draft = ANSWERER.answer(question, evidence)
        citations = validate_citations(
            database_path,
            document_id,
            evidence,
            answer_draft.citation_record_ids,
        )
        if answer_draft.abstained and citations:
            raise CitationValidationError("Abstained answers cannot cite source records.")
        if not answer_draft.abstained and not citations:
            raise CitationValidationError("Supported answers require a validated citation.")
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except CitationValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Retrieved citations failed source validation.",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Question answering storage is unavailable.") from exc

    return AskResponse(
        document_id=document_id,
        question=question,
        answer=answer_draft.answer,
        citations=[
            CitationResponse(
                source_record_id=citation.source_record_id,
                source_type=citation.source_type,
                page_or_slide_number=citation.page_or_slide_number,
                excerpt=citation.excerpt,
            )
            for citation in citations
        ],
        abstained=answer_draft.abstained,
        abstention_reason=answer_draft.abstention_reason,
    )