import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from app.storage import StoredSourceRecord, get_document_source_records


MAX_SOURCE_STATEMENT_LENGTH = 300
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_URL_ONLY_PATTERN = re.compile(r"^(?:https?://|www\.)\S+$", flags=re.IGNORECASE)
_QUESTION_TERM_PATTERN = re.compile(
    r'^Which source statement(?: on (?:page|slide) \d+)? '
    r'explicitly mentions the term "([^\"]+)"\?$'
)
_GENERIC_HEADING_TERMS = {
    "algorithm", "analysis", "approach", "coding", "complexity", "conclusion",
    "description", "explanation", "implementation", "input", "introduction",
    "interview", "method", "naive", "output", "overview", "practice", "program",
    "question", "questions", "reference", "references", "result", "sample", "step",
    "steps", "time", "topic", "topics", "url", "qr", "code",
}
_STOP_WORDS = {
    "about", "after", "again", "also", "among", "because", "before", "being",
    "between", "could", "does", "each", "from", "have", "into", "more", "most",
    "other", "over", "same", "should", "some", "such", "than", "that", "their",
    "there", "these", "they", "this", "those", "through", "under", "very", "which",
    "while", "would",
}
_OPTION_IDS = ("A", "B", "C", "D")
_SOURCE_TYPE_LABELS: dict[str, Literal["pdf_page", "pptx_slide"]] = {
    "page": "pdf_page",
    "slide": "pptx_slide",
}


class DocumentNotFoundError(LookupError):
    pass


class QuizValidationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QuizOption:
    option_id: str
    text: str


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    question_id: str
    question_text: str
    options: tuple[QuizOption, ...]
    answer_key: str
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    supporting_excerpt: str
    concept_label: str
    difficulty: Literal["introductory", "standard"]


def generate_quiz(
    database_path: Path,
    document_id: str,
    question_count: int,
    *,
    concept_priorities: Mapping[str, tuple[int, float]] | None = None,
    difficulty_preferences: Mapping[str, Literal["introductory", "standard"]] | None = None,
    excluded_question_ids: set[str] | None = None,
) -> list[QuizQuestion]:
    records = get_document_source_records(database_path, document_id)
    if records is None:
        raise DocumentNotFoundError(document_id)

    candidates: list[QuizQuestion] = []
    seen_question_text: set[str] = set()
    ordered_records = sorted(
        records,
        key=lambda record: (record.source_type, record.source_number, record.id),
    )

    for record in ordered_records:
        source_type = _SOURCE_TYPE_LABELS.get(record.source_type)
        if source_type is None:
            continue

        statements = _unique_statements(record.extracted_text)
        if len(statements) < 4:
            continue

        for statement in statements:
            candidate = _make_question(
                record,
                source_type,
                statement,
                statements,
                excluded_question_ids or set(),
            )
            if candidate is None:
                continue

            normalized_question = _normalize_text(candidate.question_text)
            if normalized_question in seen_question_text:
                continue
            seen_question_text.add(normalized_question)
            candidates.append(candidate)

    validated_candidates = validate_quiz_questions(
        database_path, document_id, candidates, skip_invalid=True
    )
    if concept_priorities:
        validated_candidates.sort(
            key=lambda question: (
                concept_priorities.get(question.concept_label, (1, 0.5)),
                0
                if difficulty_preferences is None
                or difficulty_preferences.get(question.concept_label) == question.difficulty
                else 1,
            )
        )
    return validated_candidates[:question_count]


def question_concept(question_text: str) -> str | None:
    match = _QUESTION_TERM_PATTERN.fullmatch(question_text)
    return match.group(1) if match else None


def validate_quiz_questions(
    database_path: Path,
    document_id: str,
    questions: Sequence[QuizQuestion],
    *,
    skip_invalid: bool = False,
) -> list[QuizQuestion]:
    records = get_document_source_records(database_path, document_id)
    if records is None:
        raise DocumentNotFoundError(document_id)

    records_by_id = {record.id: record for record in records}
    validated_questions: list[QuizQuestion] = []
    seen_question_ids: set[str] = set()

    for question in questions:
        try:
            _validate_quiz_question(question, records_by_id, seen_question_ids)
        except QuizValidationError:
            if not skip_invalid:
                raise
            continue
        validated_questions.append(question)

    return validated_questions


def _validate_quiz_question(
    question: QuizQuestion,
    records_by_id: dict[str, StoredSourceRecord],
    seen_question_ids: set[str],
) -> None:
    record = records_by_id.get(question.source_record_id)
    option_ids = [option.option_id for option in question.options]
    normalized_options = [_normalize_text(option.text) for option in question.options]
    correct_options = [
        option for option in question.options if option.option_id == question.answer_key
    ]

    if (
        record is None
        or question.question_id in seen_question_ids
        or len(question.options) != 4
        or len(set(option_ids)) != 4
        or set(option_ids) != set(_OPTION_IDS)
        or len(set(normalized_options)) != 4
        or len(correct_options) != 1
        or question.source_type != _SOURCE_TYPE_LABELS.get(record.source_type)
        or question.page_or_slide_number != record.source_number
        or not question.supporting_excerpt
        or question.supporting_excerpt not in record.extracted_text
        or correct_options[0].text != question.supporting_excerpt
    ):
        raise QuizValidationError("Generated quiz question failed source validation.")

    if any(
        not option.text or option.text not in record.extracted_text
        for option in question.options
    ):
        raise QuizValidationError("Quiz options must be source-backed statements.")

    correct_text = correct_options[0].text
    correct_terms = set(_terms(correct_text))
    question_term_match = _QUESTION_TERM_PATTERN.fullmatch(question.question_text)
    if (
        question_term_match is None
        or question.concept_label != question_term_match.group(1)
        or question_term_match.group(1) not in correct_terms
        or any(
            question_term_match.group(1) in _terms(option.text)
            for option in question.options
            if option.option_id != question.answer_key
        )
    ):
        raise QuizValidationError("Quiz answer is not uniquely supported by its source.")

    seen_question_ids.add(question.question_id)


def _make_question(
    record: StoredSourceRecord,
    source_type: Literal["pdf_page", "pptx_slide"],
    correct_statement: str,
    statements: list[str],
    excluded_question_ids: set[str],
) -> QuizQuestion | None:
    if not 20 <= len(correct_statement) <= MAX_SOURCE_STATEMENT_LENGTH:
        return None

    distractors = [
        statement
        for statement in statements
        if statement != correct_statement
        and len(statement) <= MAX_SOURCE_STATEMENT_LENGTH
    ]
    if len(distractors) < 3:
        return None

    correct_terms = set(_terms(correct_statement))
    candidate_terms = sorted(
        (
            term
            for term in correct_terms
            if len(term) >= 4 and term not in _STOP_WORDS
        ),
        key=lambda term: (-len(term), term),
    )

    for term in candidate_terms:
        unrelated_distractors = [
            statement
            for statement in distractors
            if term not in _terms(statement)
        ]
        if len(unrelated_distractors) < 3:
            continue

        source_location = "page" if source_type == "pdf_page" else "slide"
        question_text = (
            f'Which source statement on {source_location} {record.source_number} '
            f'explicitly mentions the term "{term}"?'
        )
        question_id = str(
            uuid5(
                NAMESPACE_URL,
                "nexus-academy:quiz:"
                f"{record.document_id}:{record.id}:{term}:"
                f"{_normalize_text(correct_statement)}",
            )
        )
        if question_id in excluded_question_ids:
            continue
        distractors = sorted(
            unrelated_distractors,
            key=lambda statement: (
                abs(len(_terms(statement)) - len(correct_terms)),
                _stable_order_key(question_id, statement),
            ),
        )[:3]
        answer_terms = correct_terms - {term}
        distractor_overlap = max(
            (
                len(answer_terms.intersection(_terms(distractor)))
                / max(len(answer_terms), 1)
                for distractor in distractors
            ),
            default=0.0,
        )
        difficulty: Literal["introductory", "standard"] = (
            "standard" if distractor_overlap >= 0.35 else "introductory"
        )
        option_texts = [correct_statement, *distractors]
        option_texts.sort(key=lambda text: _stable_order_key(question_id, text))
        options = tuple(
            QuizOption(option_id=option_id, text=text)
            for option_id, text in zip(_OPTION_IDS, option_texts, strict=True)
        )
        answer_key = next(
            option.option_id for option in options if option.text == correct_statement
        )
        return QuizQuestion(
            question_id=question_id,
            question_text=question_text,
            options=options,
            answer_key=answer_key,
            source_record_id=record.id,
            source_type=source_type,
            page_or_slide_number=record.source_number,
            supporting_excerpt=correct_statement,
            concept_label=term,
            difficulty=difficulty,
        )

    return None


def _unique_statements(text: str) -> list[str]:
    statements: list[str] = []
    seen: set[str] = set()
    for part in _SENTENCE_SPLIT_PATTERN.split(text):
        statement = part.strip()
        normalized = _normalize_text(statement)
        if (
            statement
            and normalized not in seen
            and _is_substantive_statement(statement)
        ):
            statements.append(statement)
            seen.add(normalized)
    return statements


def _is_substantive_statement(statement: str) -> bool:
    if _URL_ONLY_PATTERN.fullmatch(statement.strip()):
        return False

    terms = _terms(statement)
    if 1 <= len(terms) <= 3 and set(terms).issubset(_GENERIC_HEADING_TERMS):
        return False
    return True


def _terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return [term for term in _WORD_PATTERN.findall(normalized) if term.isalpha()]


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _stable_order_key(question_id: str, text: str) -> str:
    return hashlib.sha256(f"{question_id}:{_normalize_text(text)}".encode()).hexdigest()