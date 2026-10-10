import sqlite3
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Path as PathParameter, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.answering import (
    Answerer,
    CitationValidationError,
    RoutedEvidenceAnswerer,
    validate_citations,
)
from app.ingestion import (
    InvalidDocumentError,
    UnsupportedDocumentError,
    extract_document,
)
from app.model_routing import ModelRouter
from app.retrieval import DocumentNotFoundError, normalize_query, search_document
from app.quiz import (
    DocumentNotFoundError as QuizDocumentNotFoundError,
    QuizOption,
    QuizQuestion,
    QuizValidationError,
    generate_quiz,
    question_concept,
    validate_quiz_questions,
)
from app.storage import (
    AssetStorageError,
    LearnerDocumentNotFoundError,
    LearnerNotFoundError,
    LearnerQuizOwnershipError,
    QuizDocumentNotFoundError as StoredQuizDocumentNotFoundError,
    QuizSourceIntegrityError,
    create_learner_profile,
    get_database_path,
    get_document_asset,
    get_document_assets,
    get_learner_adaptive_context,
    get_learner_progress,
    get_quiz_session,
    record_learner_quiz_attempt,
    save_document,
    save_quiz_session,
)


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


class DocumentAssetResponse(BaseModel):
    asset_id: str
    slide_number: int
    mime_type: str
    width: int
    height: int
    content_hash: str
    byte_size: int


class DocumentAssetsResponse(BaseModel):
    document_id: str
    assets: list[DocumentAssetResponse]


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


class QuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_count: int = Field(default=5, ge=1, le=10)
    learner_id: str | None = Field(default=None, min_length=1, max_length=100)


class AdaptiveQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_count: int = Field(default=5, ge=1, le=10)


class QuizOptionResponse(BaseModel):
    option_id: Literal["A", "B", "C", "D"]
    text: str


class QuizQuestionResponse(BaseModel):
    question_id: str
    question_text: str
    concept_label: str
    difficulty: Literal["introductory", "standard"]
    options: list[QuizOptionResponse]
    answer_key: Literal["A", "B", "C", "D"]
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    supporting_excerpt: str


class QuizResponse(BaseModel):
    quiz_id: str
    document_id: str
    learner_id: str | None = None
    requested_question_count: int
    generated_question_count: int
    limitation: str | None
    questions: list[QuizQuestionResponse]


class QuizAnswerSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=100)
    selected_option_id: Literal["A", "B", "C", "D"]


class QuizSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_id: str = Field(min_length=1, max_length=100)
    learner_id: str | None = Field(default=None, min_length=1, max_length=100)
    answers: list[QuizAnswerSelection] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "May be omitted or empty; unanswered questions are scored as unanswered. "
            "Each question ID may appear at most once."
        ),
    )

    @model_validator(mode="after")
    def reject_duplicate_questions(self) -> "QuizSubmissionRequest":
        question_ids = [answer.question_id for answer in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Each quiz question may be answered only once per submission.")
        return self


class QuizQuestionResultResponse(BaseModel):
    question_id: str
    concept_label: str | None
    selected_option_id: str | None
    is_correct: bool | None
    correct_option_id: str
    feedback: str
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    supporting_excerpt: str


class QuizSubmissionResponse(BaseModel):
    quiz_id: str
    document_id: str
    total_questions: int
    answered_count: int
    correct_count: int
    score_percentage_of_answered: float
    results: list[QuizQuestionResultResponse]


class LearnerProfileResponse(BaseModel):
    learner_id: str
    created_at: str


class LearnerConceptProgressResponse(BaseModel):
    document_id: str
    concept_label: str
    label_basis: Literal["source_term_from_quiz_prompt"]
    question_attempt_count: int
    correct_count: int
    mastery_estimate: float
    recent_accuracy: float | None
    evidence_sufficient: bool


class LearnerProgressResponse(BaseModel):
    learner_id: str
    created_at: str
    quiz_attempt_count: int
    question_attempt_count: int
    correct_answer_rate: float
    concepts_attempted: list[LearnerConceptProgressResponse]
    weak_concepts: list[LearnerConceptProgressResponse]
    insufficient_evidence_concepts: list[LearnerConceptProgressResponse]


class ModelTaskStatusResponse(BaseModel):
    task: str
    enabled: bool
    provider: str
    model: str | None
    capabilities: list[str]
    fallback_provider: str | None
    fallback_model: str | None


class ModelStatusResponse(BaseModel):
    tasks: list[ModelTaskStatusResponse]


MODEL_ROUTER = ModelRouter()
ANSWERER: Answerer = RoutedEvidenceAnswerer(MODEL_ROUTER)


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
            except AssetStorageError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Extracted images failed validation or exceeded storage limits.",
                ) from exc
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


@router.get("/documents/{document_id}/assets", response_model=DocumentAssetsResponse)
def list_document_assets_endpoint(document_id: str) -> DocumentAssetsResponse:
    try:
        assets = get_document_assets(get_database_path(), document_id)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Asset storage is unavailable.") from exc
    if assets is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentAssetsResponse(
        document_id=document_id,
        assets=[
            DocumentAssetResponse(
                asset_id=asset.asset_id,
                slide_number=asset.slide_number,
                mime_type=asset.mime_type,
                width=asset.width,
                height=asset.height,
                content_hash=asset.content_hash,
                byte_size=asset.byte_size,
            )
            for asset in assets
        ],
    )


@router.get(
    "/documents/{document_id}/assets/{asset_id}",
    response_model=DocumentAssetResponse,
)
def get_document_asset_endpoint(
    document_id: str,
    asset_id: Annotated[
        str,
        PathParameter(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
    ],
) -> DocumentAssetResponse:
    try:
        asset = get_document_asset(get_database_path(), document_id, asset_id)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Asset storage is unavailable.") from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="Document asset not found.")
    return DocumentAssetResponse(
        asset_id=asset.asset_id,
        slide_number=asset.slide_number,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        content_hash=asset.content_hash,
        byte_size=asset.byte_size,
    )


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


@router.get("/models/status", response_model=ModelStatusResponse)
def get_model_status_endpoint() -> ModelStatusResponse:
    return ModelStatusResponse(
        tasks=[
            ModelTaskStatusResponse(
                task=status.task,
                enabled=status.enabled,
                provider=status.provider,
                model=status.model,
                capabilities=list(status.capabilities),
                fallback_provider=status.fallback_provider,
                fallback_model=status.fallback_model,
            )
            for status in MODEL_ROUTER.status()
        ]
    )


@router.post("/learners", response_model=LearnerProfileResponse, status_code=201)
def create_learner_endpoint() -> LearnerProfileResponse:
    try:
        profile = create_learner_profile(get_database_path())
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Learner storage is unavailable.") from exc
    return LearnerProfileResponse(
        learner_id=profile.learner_id,
        created_at=profile.created_at,
    )


@router.get("/learners/{learner_id}/progress", response_model=LearnerProgressResponse)
def get_learner_progress_endpoint(learner_id: str) -> LearnerProgressResponse:
    try:
        progress = get_learner_progress(get_database_path(), learner_id)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Learner storage is unavailable.") from exc
    if progress is None:
        raise HTTPException(status_code=404, detail="Learner not found.")

    concepts = [
        LearnerConceptProgressResponse(
            document_id=concept.document_id,
            concept_label=concept.concept_label,
            label_basis="source_term_from_quiz_prompt",
            question_attempt_count=concept.attempt_count,
            correct_count=concept.correct_count,
            mastery_estimate=concept.mastery_estimate,
            recent_accuracy=(
                sum(concept.recent_performance) / len(concept.recent_performance)
                if concept.recent_performance
                else None
            ),
            evidence_sufficient=concept.attempt_count >= 2,
        )
        for concept in progress.concepts
    ]
    correct_answer_rate = (
        progress.correct_question_count / progress.question_attempt_count
        if progress.question_attempt_count
        else 0.0
    )
    return LearnerProgressResponse(
        learner_id=progress.profile.learner_id,
        created_at=progress.profile.created_at,
        quiz_attempt_count=progress.quiz_attempt_count,
        question_attempt_count=progress.question_attempt_count,
        correct_answer_rate=correct_answer_rate,
        concepts_attempted=concepts,
        weak_concepts=[concept for concept in concepts if concept.mastery_estimate < 0.5],
        insufficient_evidence_concepts=[
            concept for concept in concepts if not concept.evidence_sufficient
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


@router.post("/learners", response_model=LearnerProfileResponse, status_code=201)
def create_learner_endpoint() -> LearnerProfileResponse:
    try:
        profile = create_learner_profile(get_database_path())
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Learner storage is unavailable.") from exc
    return LearnerProfileResponse(
        learner_id=profile.learner_id,
        created_at=profile.created_at,
    )


@router.get("/learners/{learner_id}/progress", response_model=LearnerProgressResponse)
def get_learner_progress_endpoint(learner_id: str) -> LearnerProgressResponse:
    try:
        progress = get_learner_progress(get_database_path(), learner_id)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Learner storage is unavailable.") from exc
    if progress is None:
        raise HTTPException(status_code=404, detail="Learner not found.")

    concepts = [
        LearnerConceptProgressResponse(
            document_id=concept.document_id,
            concept_label=concept.concept_label,
            label_basis="source_term_from_quiz_prompt",
            question_attempt_count=concept.attempt_count,
            correct_count=concept.correct_count,
            mastery_estimate=concept.mastery_estimate,
            recent_accuracy=(
                sum(concept.recent_performance) / len(concept.recent_performance)
                if concept.recent_performance
                else None
            ),
            evidence_sufficient=concept.attempt_count >= 2,
        )
        for concept in progress.concepts
    ]
    correct_answer_rate = (
        progress.correct_question_count / progress.question_attempt_count
        if progress.question_attempt_count
        else 0.0
    )
    return LearnerProgressResponse(
        learner_id=progress.profile.learner_id,
        created_at=progress.profile.created_at,
        quiz_attempt_count=progress.quiz_attempt_count,
        question_attempt_count=progress.question_attempt_count,
        correct_answer_rate=correct_answer_rate,
        concepts_attempted=concepts,
        weak_concepts=[concept for concept in concepts if concept.mastery_estimate < 0.5],
        insufficient_evidence_concepts=[
            concept for concept in concepts if not concept.evidence_sufficient
        ],
    )


@router.post(
    "/learners/{learner_id}/documents/{document_id}/quiz",
    response_model=QuizResponse,
)
def generate_adaptive_quiz_endpoint(
    learner_id: str,
    document_id: str,
    request: AdaptiveQuizRequest,
) -> QuizResponse:
    database_path = get_database_path()
    try:
        context = get_learner_adaptive_context(database_path, learner_id, document_id)
        priorities: dict[str, tuple[int, float]] = {}
        difficulty_preferences: dict[str, Literal["introductory", "standard"]] = {}
        for concept in context.concepts:
            recent_consistent = (
                len(concept.recent_performance) >= 2
                and all(concept.recent_performance[-2:])
            )
            if concept.mastery_estimate < 0.5 or (
                concept.recent_performance and not concept.recent_performance[-1]
            ):
                priority = 0
            elif concept.attempt_count < 2 or not recent_consistent:
                priority = 1
            else:
                priority = 2
            priorities[concept.concept_label] = (priority, concept.mastery_estimate)
            difficulty_preferences[concept.concept_label] = (
                "standard"
                if concept.attempt_count >= 3
                and recent_consistent
                and concept.mastery_estimate >= 0.75
                else "introductory"
            )

        questions = generate_quiz(
            database_path,
            document_id,
            question_count=10,
            concept_priorities=priorities,
            difficulty_preferences=difficulty_preferences,
            excluded_question_ids=set(context.attempted_question_ids),
        )[: request.question_count]
        quiz_id = save_quiz_session(
            database_path,
            document_id,
            questions,
            learner_id=learner_id,
        )
    except LearnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Learner not found.") from exc
    except LearnerDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except StoredQuizDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except QuizValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated quiz failed source validation.",
        ) from exc
    except QuizSourceIntegrityError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated quiz failed source validation.",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Quiz storage is unavailable.") from exc

    generated_count = len(questions)
    limitation = None
    if generated_count < request.question_count:
        limitation = (
            "Only non-repeated questions with four distinct source-backed statements "
            "were included; the document may not support more suitable questions."
        )
    return QuizResponse(
        quiz_id=quiz_id,
        document_id=document_id,
        learner_id=learner_id,
        requested_question_count=request.question_count,
        generated_question_count=generated_count,
        limitation=limitation,
        questions=[
            QuizQuestionResponse(
                question_id=question.question_id,
                question_text=question.question_text,
                concept_label=question.concept_label,
                difficulty=question.difficulty,
                options=[
                    QuizOptionResponse(option_id=option.option_id, text=option.text)
                    for option in question.options
                ],
                answer_key=question.answer_key,
                source_record_id=question.source_record_id,
                source_type=question.source_type,
                page_or_slide_number=question.page_or_slide_number,
                supporting_excerpt=question.supporting_excerpt,
            )
            for question in questions
        ],
    )


@router.post(
    "/learners/{learner_id}/documents/{document_id}/quiz",
    response_model=QuizResponse,
)
def generate_adaptive_quiz_endpoint(
    learner_id: str,
    document_id: str,
    request: AdaptiveQuizRequest,
) -> QuizResponse:
    database_path = get_database_path()
    try:
        context = get_learner_adaptive_context(database_path, learner_id, document_id)
        priorities: dict[str, tuple[int, float]] = {}
        difficulty_preferences: dict[str, Literal["introductory", "standard"]] = {}
        for concept in context.concepts:
            recent_consistent = (
                len(concept.recent_performance) >= 2
                and all(concept.recent_performance[-2:])
            )
            if concept.mastery_estimate < 0.5 or (
                concept.recent_performance and not concept.recent_performance[-1]
            ):
                priority = 0
            elif concept.attempt_count < 2 or not recent_consistent:
                priority = 1
            else:
                priority = 2
            priorities[concept.concept_label] = (priority, concept.mastery_estimate)
            difficulty_preferences[concept.concept_label] = (
                "standard"
                if concept.attempt_count >= 3
                and recent_consistent
                and concept.mastery_estimate >= 0.75
                else "introductory"
            )

        questions = generate_quiz(
            database_path,
            document_id,
            question_count=10,
            concept_priorities=priorities,
            difficulty_preferences=difficulty_preferences,
            excluded_question_ids=set(context.attempted_question_ids),
        )[: request.question_count]
        quiz_id = save_quiz_session(
            database_path,
            document_id,
            questions,
            learner_id=learner_id,
        )
    except LearnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Learner not found.") from exc
    except LearnerDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except QuizDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except StoredQuizDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except QuizValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated quiz failed source validation.",
        ) from exc
    except QuizSourceIntegrityError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated quiz failed source validation.",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Quiz storage is unavailable.") from exc

    generated_count = len(questions)
    limitation = None
    if generated_count < request.question_count:
        limitation = (
            "Only non-repeated questions with four distinct source-backed statements "
            "were included; the document may not support more suitable questions."
        )
    return QuizResponse(
        quiz_id=quiz_id,
        document_id=document_id,
        learner_id=learner_id,
        requested_question_count=request.question_count,
        generated_question_count=generated_count,
        limitation=limitation,
        questions=[
            QuizQuestionResponse(
                question_id=question.question_id,
                question_text=question.question_text,
                concept_label=question.concept_label,
                difficulty=question.difficulty,
                options=[
                    QuizOptionResponse(option_id=option.option_id, text=option.text)
                    for option in question.options
                ],
                answer_key=question.answer_key,
                source_record_id=question.source_record_id,
                source_type=question.source_type,
                page_or_slide_number=question.page_or_slide_number,
                supporting_excerpt=question.supporting_excerpt,
            )
            for question in questions
        ],
    )


@router.post("/documents/{document_id}/quiz", response_model=QuizResponse)
def generate_document_quiz_endpoint(
    document_id: str,
    request: QuizRequest,
) -> QuizResponse:
    database_path = get_database_path()
    try:
        if request.learner_id is not None and get_learner_progress(
            database_path, request.learner_id
        ) is None:
            raise LearnerNotFoundError(request.learner_id)
        questions = generate_quiz(database_path, document_id, request.question_count)
        quiz_id = save_quiz_session(
            database_path,
            document_id,
            questions,
            learner_id=request.learner_id,
        )
    except QuizDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except LearnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Learner not found.") from exc
    except StoredQuizDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except QuizValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated quiz failed source validation.",
        ) from exc
    except QuizSourceIntegrityError as exc:
        raise HTTPException(
            status_code=500,
            detail="Generated quiz failed source validation.",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Quiz storage is unavailable.") from exc

    generated_count = len(questions)
    limitation = None
    if generated_count < request.question_count:
        limitation = (
            f"Requested {request.question_count} questions, but only {generated_count} "
            "reliable questions could be formed from source statements with three "
            "distinct in-document distractors."
        )

    return QuizResponse(
        quiz_id=quiz_id,
        document_id=document_id,
        learner_id=request.learner_id,
        requested_question_count=request.question_count,
        generated_question_count=generated_count,
        limitation=limitation,
        questions=[
            QuizQuestionResponse(
                question_id=question.question_id,
                question_text=question.question_text,
                concept_label=question.concept_label,
                difficulty=question.difficulty,
                options=[
                    QuizOptionResponse(option_id=option.option_id, text=option.text)
                    for option in question.options
                ],
                answer_key=question.answer_key,
                source_record_id=question.source_record_id,
                source_type=question.source_type,
                page_or_slide_number=question.page_or_slide_number,
                supporting_excerpt=question.supporting_excerpt,
            )
            for question in questions
        ],
    )


@router.post(
    "/documents/{document_id}/quiz/submit",
    response_model=QuizSubmissionResponse,
)
def submit_document_quiz_endpoint(
    document_id: str,
    request: QuizSubmissionRequest,
) -> QuizSubmissionResponse:
    database_path = get_database_path()
    try:
        session = get_quiz_session(database_path, document_id, request.quiz_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Quiz or document not found.")
        if session.learner_id is not None and request.learner_id is None:
            raise HTTPException(
                status_code=422,
                detail="This quiz submission requires its learner ID.",
            )
        if session.learner_id is not None and request.learner_id != session.learner_id:
            raise HTTPException(status_code=404, detail="Quiz or document not found.")

        question_ids = {question.question_id for question in session.questions}
        selected_options: dict[str, str] = {}
        for answer in request.answers:
            if answer.question_id not in question_ids:
                raise HTTPException(
                    status_code=422,
                    detail="An answer references a question outside this quiz.",
                )
            question = next(
                item for item in session.questions if item.question_id == answer.question_id
            )
            allowed_options = {option.option_id for option in question.options}
            if answer.selected_option_id not in allowed_options:
                raise HTTPException(
                    status_code=422,
                    detail="An answer references an option outside its question.",
                )
            selected_options[answer.question_id] = answer.selected_option_id

        persisted_questions = [
            QuizQuestion(
                question_id=question.question_id,
                question_text=question.question_text,
                concept_label=question_concept(question.question_text) or "",
                difficulty=question.difficulty,
                options=tuple(
                    QuizOption(option_id=option.option_id, text=option.text)
                    for option in question.options
                ),
                answer_key=question.answer_key,
                source_record_id=question.source_record_id,
                source_type=(
                    "pdf_page" if question.source_type == "page" else "pptx_slide"
                ),
                page_or_slide_number=question.page_or_slide_number,
                supporting_excerpt=question.supporting_excerpt,
            )
            for question in session.questions
        ]
        validate_quiz_questions(database_path, document_id, persisted_questions)
        if request.learner_id is not None:
            record_learner_quiz_attempt(
                database_path,
                request.learner_id,
                document_id,
                request.quiz_id,
                request.answers,
            )
    except HTTPException:
        raise
    except LearnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Learner not found.") from exc
    except LearnerQuizOwnershipError as exc:
        raise HTTPException(status_code=404, detail="Quiz or document not found.") from exc
    except (QuizValidationError, QuizSourceIntegrityError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Saved quiz evidence failed source validation.",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Quiz storage is unavailable.") from exc

    results: list[QuizQuestionResultResponse] = []
    correct_count = 0
    for question in session.questions:
        selected_option_id = selected_options.get(question.question_id)
        is_correct = (
            selected_option_id == question.answer_key
            if selected_option_id is not None
            else None
        )
        if is_correct:
            correct_count += 1

        if is_correct is None:
            feedback = f'Not answered. The source states: "{question.supporting_excerpt}"'
        elif is_correct:
            feedback = f'Correct. The source states: "{question.supporting_excerpt}"'
        else:
            feedback = f'Not correct. The source states: "{question.supporting_excerpt}"'

        source_type: Literal["pdf_page", "pptx_slide"] = (
            "pdf_page" if question.source_type == "page" else "pptx_slide"
        )
        results.append(
            QuizQuestionResultResponse(
                question_id=question.question_id,
                concept_label=question_concept(question.question_text),
                selected_option_id=selected_option_id,
                is_correct=is_correct,
                correct_option_id=question.answer_key,
                feedback=feedback,
                source_record_id=question.source_record_id,
                source_type=source_type,
                page_or_slide_number=question.page_or_slide_number,
                supporting_excerpt=question.supporting_excerpt,
            )
        )

    answered_count = len(selected_options)
    score_percentage = (
        correct_count / answered_count * 100.0 if answered_count else 0.0
    )
    return QuizSubmissionResponse(
        quiz_id=session.quiz_id,
        document_id=session.document_id,
        total_questions=len(session.questions),
        answered_count=answered_count,
        correct_count=correct_count,
        score_percentage_of_answered=score_percentage,
        results=results,
    )