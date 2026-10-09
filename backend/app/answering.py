from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, Sequence

from app.retrieval import DocumentNotFoundError, SearchMatch
from app.storage import get_document_source_records


SourceType = Literal["pdf_page", "pptx_slide"]
_SOURCE_TYPE_LABELS: dict[str, SourceType] = {
    "page": "pdf_page",
    "slide": "pptx_slide",
}


class CitationValidationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AnswerDraft:
    answer: str
    abstained: bool
    abstention_reason: str | None
    citation_record_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedCitation:
    source_record_id: str
    source_type: SourceType
    page_or_slide_number: int
    excerpt: str


class Answerer(Protocol):
    def answer(self, question: str, evidence: Sequence[SearchMatch]) -> AnswerDraft:
        """Produce an answer draft and identify the evidence records it uses."""


class QuotedEvidenceAnswerer:
    def answer(self, question: str, evidence: Sequence[SearchMatch]) -> AnswerDraft:
        del question
        if not evidence:
            return AnswerDraft(
                answer="I could not find supporting evidence in this document.",
                abstained=True,
                abstention_reason="No matching source records were retrieved.",
                citation_record_ids=(),
            )

        best_match = evidence[0]
        excerpt = best_match.excerpt.strip()
        if not excerpt:
            return AnswerDraft(
                answer="I could not find supporting evidence in this document.",
                abstained=True,
                abstention_reason="The retrieved source contains no answerable text.",
                citation_record_ids=(),
            )

        return AnswerDraft(
            answer=f'The document states: "{excerpt}"',
            abstained=False,
            abstention_reason=None,
            citation_record_ids=(best_match.source_record_id,),
        )


def validate_citations(
    database_path: Path,
    document_id: str,
    evidence: Sequence[SearchMatch],
    citation_record_ids: Sequence[str],
) -> list[ValidatedCitation]:
    stored_records = get_document_source_records(database_path, document_id)
    if stored_records is None:
        raise DocumentNotFoundError(document_id)

    records_by_id = {record.id: record for record in stored_records}
    evidence_by_id = {match.source_record_id: match for match in evidence}
    citations: list[ValidatedCitation] = []
    seen_ids: set[str] = set()

    for record_id in citation_record_ids:
        if record_id in seen_ids:
            raise CitationValidationError("Duplicate citation record ID.")
        seen_ids.add(record_id)

        record = records_by_id.get(record_id)
        match = evidence_by_id.get(record_id)
        if record is None or match is None:
            raise CitationValidationError("Citation is not part of retrieved evidence.")

        source_type = _SOURCE_TYPE_LABELS.get(record.source_type)
        if (
            source_type is None
            or record.document_id != document_id
            or match.document_id != record.document_id
            or match.source_type != source_type
            or match.page_or_slide_number != record.source_number
            or not match.excerpt
            or match.excerpt not in record.extracted_text
        ):
            raise CitationValidationError("Citation does not match its persisted source.")

        citations.append(
            ValidatedCitation(
                source_record_id=record.id,
                source_type=source_type,
                page_or_slide_number=record.source_number,
                excerpt=match.excerpt,
            )
        )

    return citations