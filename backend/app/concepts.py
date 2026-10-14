import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence
from uuid import NAMESPACE_URL, uuid5

from app.storage import StoredSourceRecord, get_document_source_records


_WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_URL_PATTERN = re.compile(r"^(?:https?://|www\.)\S+$", flags=re.IGNORECASE)
_VISUAL_CONTENT_MARKER_PATTERN = re.compile(
    r"^\[Visual Content on Slide (\d+)\]:\s*(.*)$",
    flags=re.IGNORECASE,
)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|[\r\n]+")

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
    "while", "would", "where", "what", "when", "with",
    "high", "excess", "normal", "broken", "clean", "large", "small",
}

_DEFINITION_VERB_PATTERN = re.compile(
    r"\b(measures?|converts?|stores?|absorbs?|carries|carry|transports?|resists?|allows?|"
    r"interrupts?|controls?|melts?|forms?|rotates?|reshapes?|classifies|classify|produces?|"
    r"generates?|prevents?|limits?|opposes?|depicting|illustrates?|"
    r"is the|are the|refers to|defined as|consists of)\b",
    flags=re.IGNORECASE,
)

_CAUSE_EFFECT_PATTERN = re.compile(
    r"\b(when|because|causes|resulting in|leads to|results in|due to|therefore|consequently)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExtractedConcept:
    concept_id: str
    document_id: str
    name: str
    description: str
    source_record_id: str
    source_type: Literal["pdf_page", "pptx_slide"]
    page_or_slide_number: int
    evidence_excerpt: str
    is_visual: bool
    related_concept_names: tuple[str, ...]


def extract_document_concepts(
    database_path: Path,
    document_id: str,
) -> list[ExtractedConcept]:
    records = get_document_source_records(database_path, document_id)
    if records is None:
        return []

    return extract_concepts_from_records(document_id, records)


def extract_concepts_from_records(
    document_id: str,
    records: Sequence[StoredSourceRecord],
) -> list[ExtractedConcept]:
    concepts: list[ExtractedConcept] = []
    seen_concept_names: set[str] = set()

    ordered_records = sorted(
        records,
        key=lambda r: (r.source_type, r.source_number, r.id),
    )

    for record in ordered_records:
        source_label: Literal["pdf_page", "pptx_slide"] = (
            "pdf_page" if record.source_type == "page" else "pptx_slide"
        )
        statements = _extract_substantive_statements(record.extracted_text)

        for stmt in statements:
            visual_match = _VISUAL_CONTENT_MARKER_PATTERN.match(stmt.strip())
            is_visual = visual_match is not None
            text_body = visual_match.group(2).strip() if is_visual else stmt.strip()

            terms = [
                term
                for term in _extract_terms(text_body)
                if len(term) >= 4 and term not in _STOP_WORDS and term not in _GENERIC_HEADING_TERMS
            ]
            if not terms:
                continue

            # Candidate concept name is the leading primary subject term
            primary_term = terms[0]
            if primary_term in seen_concept_names:
                continue

            # Only qualify as an educational concept if supported by definition or explanatory phrasing
            has_definition = bool(_DEFINITION_VERB_PATTERN.search(text_body))
            has_cause_effect = bool(_CAUSE_EFFECT_PATTERN.search(text_body))

            if not (has_definition or has_cause_effect or is_visual or len(terms) >= 3):
                continue

            concept_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"nexus-academy:concept:{document_id}:{primary_term}",
                )
            )

            # Identify related concept terms from the same evidence statement
            related_terms = tuple(t for t in terms[1:4] if t != primary_term)

            concept = ExtractedConcept(
                concept_id=concept_id,
                document_id=document_id,
                name=primary_term,
                description=stmt.strip(),
                source_record_id=record.id,
                source_type=source_label,
                page_or_slide_number=record.source_number,
                evidence_excerpt=stmt.strip(),
                is_visual=is_visual,
                related_concept_names=related_terms,
            )
            concepts.append(concept)
            seen_concept_names.add(primary_term)

    return concepts


def _extract_substantive_statements(text: str) -> list[str]:
    statements: list[str] = []
    seen: set[str] = set()
    for part in _SENTENCE_SPLIT_PATTERN.split(text):
        cleaned = part.strip()
        if not cleaned:
            continue
        if _URL_PATTERN.fullmatch(cleaned) or "https://" in cleaned.casefold() or "http://" in cleaned.casefold():
            continue
        normalized = _normalize_text(cleaned)
        if normalized in seen:
            continue
        terms = _extract_terms(cleaned)
        if 1 <= len(terms) <= 3 and set(terms).issubset(_GENERIC_HEADING_TERMS):
            continue
        if len(cleaned) >= 20:
            statements.append(cleaned)
            seen.add(normalized)
    return statements


def _extract_terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return [term for term in _WORD_PATTERN.findall(normalized) if term.isalpha()]


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


LearningStatus = Literal["not_attempted", "struggling", "learning", "proficient"]


def evaluate_concept_learning_status(
    attempt_count: int,
    correct_count: int,
    mastery_estimate: float | None,
    recent_performance: Sequence[bool],
    source_type_label: str = "source",
    page_or_slide_number: int | None = None,
) -> tuple[LearningStatus, str, str]:
    """Evaluate learning status, explanation, and next recommended action.

    Thresholds and statuses are explainable product heuristics based on evidence,
    not validated psychometric models:
    - not_attempted: 0 attempts recorded
    - struggling: >= 2 attempts with low mastery (< 0.50) or consecutive recent incorrect answers
    - proficient: >= 2 attempts with high mastery (>= 0.70) and consecutive recent correct answers
    - learning: 1 attempt (preliminary sample size) or mixed performance (>= 0.50 and < 0.70)
    """
    location_str = (
        f" on {source_type_label.replace('_', ' ')} {page_or_slide_number}"
        if page_or_slide_number
        else ""
    )

    if attempt_count == 0 or mastery_estimate is None:
        return (
            "not_attempted",
            "This concept has not been tested yet; no learner attempts recorded.",
            f"Review the primary definition{location_str} and attempt an introductory diagnostic question.",
        )

    recent_consistent = (
        len(recent_performance) >= 2
        and all(recent_performance[-2:])
    )
    recent_struggling = (
        len(recent_performance) >= 2
        and not any(recent_performance[-2:])
    )

    if attempt_count >= 2 and (mastery_estimate < 0.50 or recent_struggling):
        return (
            "struggling",
            f"Demonstrated low accuracy ({correct_count}/{attempt_count}) with recent incorrect responses.",
            f"Revisit cited evidence{location_str} and practice simpler introductory questions.",
        )

    if attempt_count >= 2 and mastery_estimate >= 0.70 and recent_consistent:
        return (
            "proficient",
            f"Demonstrated consistent accuracy ({correct_count}/{attempt_count}) with consecutive correct responses.",
            "Concept is well understood; maintain retention through periodic review while prioritizing weaker concepts.",
        )

    if attempt_count < 2:
        return (
            "learning",
            f"Preliminary evidence ({correct_count}/{attempt_count}); sample size is too small to establish proficiency with confidence.",
            "Complete additional practice questions to establish a reliable mastery estimate.",
        )

    return (
        "learning",
        f"Mixed performance ({correct_count}/{attempt_count}); learner shows emerging understanding with occasional errors.",
        "Engage in targeted practice addressing distractor distinctions and concept applications.",
    )

