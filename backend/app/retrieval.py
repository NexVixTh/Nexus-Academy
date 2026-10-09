import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.storage import get_document_source_records


MAX_EXCERPT_LENGTH = 500
_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_SOURCE_TYPE_LABELS: dict[str, Literal["pdf_page", "pptx_slide"]] = {
    "page": "pdf_page",
    "slide": "pptx_slide",
}


class DocumentNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class SearchMatch:
    document_id: str
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    excerpt: str
    score: float


def normalize_query(query: str) -> list[str]:
    return sorted({term for term, _, _ in _tokenize(query)})


def search_document(
    database_path: Path,
    document_id: str,
    query: str,
    limit: int,
) -> list[SearchMatch]:
    records = get_document_source_records(database_path, document_id)
    if records is None:
        raise DocumentNotFoundError(document_id)

    query_terms = normalize_query(query)
    if not query_terms or not records:
        return []

    tokenized_records = [_tokenize(record.extracted_text) for record in records]
    term_frequencies = [
        Counter(term for term, _, _ in tokens)
        for tokens in tokenized_records
    ]
    document_count = len(records)
    average_length = (
        sum(len(tokens) for tokens in tokenized_records) / document_count
    ) or 1.0
    document_frequencies = {
        term: sum(term in frequencies for frequencies in term_frequencies)
        for term in query_terms
    }

    ranked_matches: list[SearchMatch] = []
    for record, tokens, frequencies in zip(
        records, tokenized_records, term_frequencies, strict=True
    ):
        score = 0.0
        document_length = len(tokens)
        for term in query_terms:
            term_frequency = frequencies[term]
            if not term_frequency:
                continue

            document_frequency = document_frequencies[term]
            inverse_document_frequency = math.log(
                1
                + (document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            length_normalization = 1.2 * (
                0.25 + 0.75 * document_length / average_length
            )
            score += (
                inverse_document_frequency
                * term_frequency
                * 2.2
                / (term_frequency + length_normalization)
            )

        source_type = _SOURCE_TYPE_LABELS.get(record.source_type)
        if score <= 0 or source_type is None:
            continue

        ranked_matches.append(
            SearchMatch(
                document_id=record.document_id,
                source_record_id=record.id,
                source_type=source_type,
                page_or_slide_number=record.source_number,
                excerpt=_make_excerpt(record.extracted_text, tokens, set(query_terms)),
                score=score,
            )
        )

    ranked_matches.sort(
        key=lambda match: (
            -match.score,
            match.page_or_slide_number,
            match.source_record_id,
        )
    )
    return ranked_matches[:limit]


def _tokenize(text: str) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    for match in _WORD_PATTERN.finditer(text):
        normalized = unicodedata.normalize("NFKC", match.group()).casefold()
        tokens.extend(
            (term, match.start(), match.end())
            for term in _WORD_PATTERN.findall(normalized)
        )
    return tokens


def _make_excerpt(
    text: str,
    tokens: list[tuple[str, int, int]],
    query_terms: set[str],
) -> str:
    if len(text) <= MAX_EXCERPT_LENGTH:
        return text

    match_start = next(start for term, start, _ in tokens if term in query_terms)
    start = max(0, match_start - MAX_EXCERPT_LENGTH // 3)
    start = min(start, len(text) - MAX_EXCERPT_LENGTH)
    return text[start : start + MAX_EXCERPT_LENGTH]