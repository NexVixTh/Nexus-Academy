import sqlite3
from pathlib import Path
from typing import Literal

import httpx
import pytest

from app.concepts import extract_document_concepts, extract_concepts_from_records
from app.ingestion import ExtractedRecord
from app.main import app
from app.storage import get_database_path, save_document, attach_visual_description_to_source_record


SourceLocation = tuple[Literal["page", "slide"], int, str]


@pytest.fixture
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "concepts-test.sqlite3"
    monkeypatch.setenv("NEXUS_DATABASE_PATH", str(path))
    assert get_database_path() == path
    return path


def save_test_document(database_path: Path, locations: list[SourceLocation]) -> str:
    source_type = locations[0][0]
    content_type = (
        "application/pdf"
        if source_type == "page"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    records = [
        ExtractedRecord(
            source_type=record_source_type,
            source_number=source_number,
            extracted_text=text,
            metadata={"is_empty": not text.strip(), "text_length": len(text)},
        )
        for record_source_type, source_number, text in locations
    ]
    return save_document(database_path, "concepts-test", content_type, records)


@pytest.mark.anyio
async def test_extract_concept_from_supported_definition(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [("page", 1, "An ammeter measures current in an electrical circuit. A battery converts chemical energy.")],
    )
    concepts = extract_document_concepts(database_path, doc_id)
    assert len(concepts) >= 1
    ammeter_concept = next((c for c in concepts if c.name == "ammeter"), None)
    assert ammeter_concept is not None
    assert ammeter_concept.document_id == doc_id
    assert ammeter_concept.source_type == "pdf_page"
    assert ammeter_concept.page_or_slide_number == 1
    assert "measures current" in ammeter_concept.evidence_excerpt
    assert "current" in ammeter_concept.related_concept_names
    assert ammeter_concept.is_visual is False


@pytest.mark.anyio
async def test_preserves_source_record_and_slide_provenance(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [
            ("slide", 5, "Chlorophyll absorbs blue and red light in plant leaves."),
            ("slide", 6, "Stomata exchange carbon dioxide and water vapor across the epidermis."),
        ],
    )
    concepts = extract_document_concepts(database_path, doc_id)
    assert len(concepts) == 2
    c1, c2 = concepts[0], concepts[1]
    assert c1.source_type == "pptx_slide"
    assert c1.page_or_slide_number == 5
    assert c2.source_type == "pptx_slide"
    assert c2.page_or_slide_number == 6
    assert c1.source_record_id != c2.source_record_id


@pytest.mark.anyio
async def test_avoids_unsupported_concept_creation_for_urls_headings(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [
            ("slide", 1, "https://example.com/notes\nURL:\nAlgorithm Explanation\nOverview"),
            ("slide", 2, "A fuse melts when circuit current exceeds its rated limit."),
        ],
    )
    concepts = extract_document_concepts(database_path, doc_id)
    # Only the fuse statement should yield a concept, not URLs or headings
    assert len(concepts) == 1
    assert concepts[0].name == "fuse"
    assert "melts" in concepts[0].evidence_excerpt


@pytest.mark.anyio
async def test_deduplicates_repeated_mentions_without_merging_unrelated(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [
            ("page", 1, "Photosynthesis converts sunlight into sugars. Photosynthesis stores light in plant cells."),
            ("page", 2, "Photosynthesis happens in leaves. Resistors limit electric current in a circuit."),
        ],
    )
    concepts = extract_document_concepts(database_path, doc_id)
    names = [c.name for c in concepts]
    assert names.count("photosynthesis") == 1
    assert "resistors" in names


@pytest.mark.anyio
async def test_visual_description_provenance_marked_accurately(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [("slide", 3, "Circuits require conductors for charge movement.")],
    )
    attach_visual_description_to_source_record(
        database_path, doc_id, 3, "Schematic diagram depicting parallel branches with multiple resistors."
    )
    concepts = extract_document_concepts(database_path, doc_id)
    visual_c = next((c for c in concepts if c.is_visual), None)
    assert visual_c is not None
    assert visual_c.page_or_slide_number == 3
    assert "[Visual Content on Slide 3]:" in visual_c.evidence_excerpt
    assert visual_c.is_visual is True


@pytest.mark.anyio
async def test_concepts_api_endpoint(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [("page", 1, "Voltage measures electrical potential difference between points.")],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/documents/{doc_id}/concepts")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["concept_count"] >= 1
    assert data["concepts"][0]["name"] == "voltage"
    assert data["concepts"][0]["page_or_slide_number"] == 1


@pytest.mark.anyio
async def test_cross_document_concept_isolation(database_path: Path) -> None:
    doc1 = save_test_document(
        database_path,
        [("page", 1, "Ammeter measures current.")],
    )
    doc2 = save_test_document(
        database_path,
        [("page", 1, "Galvanometer detects tiny currents.")],
    )
    c1 = extract_document_concepts(database_path, doc1)
    c2 = extract_document_concepts(database_path, doc2)

    assert all(c.document_id == doc1 for c in c1)
    assert all(c.document_id == doc2 for c in c2)
    assert {c.name for c in c1} != {c.name for c in c2}


@pytest.mark.anyio
async def test_concept_generates_definition_and_cause_effect_questions(database_path: Path) -> None:
    from app.quiz import generate_quiz

    statements = [
        "Ammeter measures electrical current flowing through an active circuit.",
        "A fuse melts when circuit current exceeds safe operating limits.",
        "Resistors limit electric charge without storing energy in fields.",
        "Capacitors store potential in electrostatic charges across dielectric plates.",
        "Inductors resist fluctuations in direct electrical currents.",
    ]
    doc_id = save_test_document(database_path, [("page", 1, " ".join(statements))])

    questions = generate_quiz(database_path, doc_id, question_count=5)
    assert len(questions) >= 2

    # Check definition question
    def_q = next((q for q in questions if "explicitly defines or explains" in q.question_text), None)
    assert def_q is not None
    assert def_q.concept_label in {"ammeter", "resistors", "capacitors", "inductors"}
    assert def_q.supporting_excerpt in " ".join(statements)
    assert def_q.answer_key in {"A", "B", "C", "D"}

    # Check cause and effect question
    cause_q = next((q for q in questions if "explicitly explains the cause or effect of" in q.question_text), None)
    assert cause_q is not None
    assert cause_q.concept_label == "fuse"
    assert "melts when" in cause_q.supporting_excerpt


@pytest.mark.anyio
async def test_concept_quiz_rejects_unsupported_distractors_and_forgeries(database_path: Path) -> None:
    from app.quiz import generate_quiz, validate_quiz_questions, QuizValidationError
    from dataclasses import replace

    statements = [
        "Photosynthesis converts solar light into stable chemical carbohydrates.",
        "Chlorophyll absorbs blue and red wavelengths inside green plant leaves.",
        "Stomata exchange carbon dioxide and moisture vapor during transpiration.",
        "Mitochondria generate cellular energy using oxidative phosphorylation reactions.",
    ]
    doc_id = save_test_document(database_path, [("page", 2, " ".join(statements))])

    questions = generate_quiz(database_path, doc_id, question_count=2)
    assert len(questions) > 0

    valid_q = questions[0]
    # Forged distractor with text not in source record (ensure we replace a distractor, not the answer key)
    fake_options = list(valid_q.options)
    distractor_idx = next(i for i, opt in enumerate(fake_options) if opt.option_id != valid_q.answer_key)
    fake_options[distractor_idx] = replace(fake_options[distractor_idx], text="Ungrounded hallucinated fact not present in document.")
    forged_q = replace(valid_q, options=tuple(fake_options))

    with pytest.raises(QuizValidationError, match="must be source-backed statements"):
        validate_quiz_questions(database_path, doc_id, [forged_q], skip_invalid=False)


@pytest.mark.anyio
async def test_adaptive_practice_prioritizes_weak_concept_and_reduces_mastered(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [
            (
                "page",
                1,
                "Ammeter measures electrical current flowing through an active circuit. "
                "A fuse melts when circuit current exceeds safe operating limits. "
                "Resistors limit electric charge without storing energy in fields. "
                "Capacitors store potential in electrostatic charges across dielectric plates.",
            ),
            (
                "page",
                2,
                "Ammeter measures current intensity across standardized laboratory components. "
                "A fuse melts when current exceeds rated amperage values. "
                "Resistors reduce overall system load efficiently. "
                "Capacitors discharge rapid energy into connected circuits.",
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create learner
        learner_res = await client.post("/learners")
        learner_id = learner_res.json()["learner_id"]

        # First quiz
        q_res = await client.post(
            f"/documents/{doc_id}/quiz",
            json={"question_count": 2, "learner_id": learner_id},
        )
        assert q_res.status_code == 200
        quiz_data = q_res.json()
        questions = quiz_data["questions"]

        # Fail first question (e.g. ammeter), get second question right (e.g. fuse)
        q1 = questions[0]
        q2 = questions[1]
        wrong_opt1 = next(o["option_id"] for o in q1["options"] if o["option_id"] != q1["answer_key"])
        correct_opt2 = q2["answer_key"]

        submit_res = await client.post(
            f"/documents/{doc_id}/quiz/submit",
            json={
                "quiz_id": quiz_data["quiz_id"],
                "learner_id": learner_id,
                "answers": [
                    {"question_id": q1["question_id"], "selected_option_id": wrong_opt1},
                    {"question_id": q2["question_id"], "selected_option_id": correct_opt2},
                ],
            },
        )
        assert submit_res.status_code == 200

        # Check learner progress: q1 concept is weak, q2 concept is stronger
        prog_res = await client.get(f"/learners/{learner_id}/progress")
        assert prog_res.status_code == 200
        progress = prog_res.json()
        weak_concepts = [c["concept_label"] for c in progress["weak_concepts"]]
        assert q1["concept_label"] in weak_concepts

        # Request adaptive quiz: weak concept must be prioritized
        adaptive_res = await client.post(
            f"/learners/{learner_id}/documents/{doc_id}/quiz",
            json={"question_count": 2},
        )
        assert adaptive_res.status_code == 200
        adaptive_questions = adaptive_res.json()["questions"]
        assert len(adaptive_questions) > 0
        assert adaptive_questions[0]["concept_label"] == q1["concept_label"]
        assert adaptive_questions[0]["question_id"] != q1["question_id"]
        assert adaptive_questions[0]["page_or_slide_number"] == 2

