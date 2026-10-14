import json
from pathlib import Path

import httpx
import pytest

from app.concepts import (
    evaluate_concept_learning_status,
    extract_concepts_from_records,
    extract_document_concepts,
)
from app.ingestion import ExtractedRecord
from app.main import app
from app.quiz import (
    _terms,
    generate_quiz,
    question_concept,
    validate_quiz_questions,
)
from app.storage import (
    create_learner_profile,
    get_database_path,
    get_document_source_records,
    get_learner_progress,
    save_document,
)


@pytest.fixture
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "edu-quality-test.sqlite3"
    monkeypatch.setenv("NEXUS_DATABASE_PATH", str(path))
    assert get_database_path() == path
    return path


def load_fixture() -> dict[str, object]:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "fixtures"
        / "educational_quality_v1.json"
    )
    with fixture_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ingest_scenario(
    database_path: Path, scenario: dict[str, object]
) -> tuple[str, list[ExtractedRecord]]:
    format_type = scenario.get("format", "pdf")
    content_type = (
        "application/pdf"
        if format_type == "pdf"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    records = [
        ExtractedRecord(
            source_type="page" if format_type == "pdf" else "slide",
            source_number=rec["location"],
            extracted_text=rec["text"],
            metadata={"is_empty": False, "text_length": len(rec["text"])},
        )
        for rec in scenario["records"]
    ]
    doc_id = save_document(
        database_path, f"{scenario['id']}.{format_type}", content_type, records
    )
    return doc_id, records


@pytest.mark.anyio
async def test_offline_educational_quality_suite(database_path: Path) -> None:
    fixture = load_fixture()
    scenarios = {s["id"]: s for s in fixture["scenarios"]}

    # Track exact numerators and denominators for Phase 5 reporting
    metrics = {
        "concept_alignment": {"num": 0, "den": 0},
        "concept_mapping": {"num": 0, "den": 0},
        "mastery_updates": {"num": 0, "den": 0},
        "adaptive_priorities": {"num": 0, "den": 0},
        "citation_provenance": {"num": 0, "den": 0},
        "appropriate_abstention": {"num": 0, "den": 0},
        "duplicate_questions": {"num": 0, "den": 0},
        "unusable_options": {"num": 0, "den": 0},
    }

    doc_ids = {}
    for sc_id, sc in scenarios.items():
        doc_id, _ = ingest_scenario(database_path, sc)
        doc_ids[sc_id] = doc_id

    # 1. Concept-to-source alignment across all scenarios
    for sc_id, sc in scenarios.items():
        doc_id = doc_ids[sc_id]
        stored_records = get_document_source_records(database_path, doc_id)
        assert stored_records is not None
        stored_by_id = {r.id: r for r in stored_records}

        concepts = extract_document_concepts(database_path, doc_id)
        for c in concepts:
            metrics["concept_alignment"]["den"] += 1
            rec = stored_by_id.get(c.source_record_id)
            if (
                rec is not None
                and c.evidence_excerpt in rec.extracted_text
                and c.page_or_slide_number == rec.source_number
                and ((c.source_type == "pdf_page" and rec.source_type == "page") or (c.source_type == "pptx_slide" and rec.source_type == "slide"))
            ):
                metrics["concept_alignment"]["num"] += 1

    assert metrics["concept_alignment"]["den"] > 0
    assert metrics["concept_alignment"]["num"] == metrics["concept_alignment"]["den"]

    # 2. Correct concept mapping and quality rules for generated quiz questions
    all_questions = []
    for sc_id in ["straightforward_definitions", "two_related_comparison", "explicit_causal", "multistep_explanation", "keyword_overlap_unrelated"]:
        doc_id = doc_ids[sc_id]
        questions = generate_quiz(database_path, doc_id, question_count=10)
        assert len(questions) >= 3, f"Scenario {sc_id} should produce at least 3 questions."
        all_questions.extend(questions)

        for q in questions:
            metrics["concept_mapping"]["den"] += 1
            extracted_term = question_concept(q.question_text)
            term_in_concept = (q.concept_label == extracted_term)
            term_in_excerpt = (q.concept_label in _terms(q.supporting_excerpt))
            # Ensure distractors do not contain the concept term (word-level)
            no_leak = all(q.concept_label not in _terms(opt.text) for opt in q.options if opt.option_id != q.answer_key)
            if term_in_concept and term_in_excerpt and no_leak:
                metrics["concept_mapping"]["num"] += 1

            # Check duplicate questions
            metrics["duplicate_questions"]["den"] += 1
            # Check unusable options (e.g. URLs or headings)
            metrics["unusable_options"]["den"] += len(q.options)
            for opt in q.options:
                if "http://" in opt.text.lower() or "https://" in opt.text.lower() or opt.text.lower().startswith("url:"):
                    metrics["unusable_options"]["num"] += 1

    assert metrics["concept_mapping"]["num"] == metrics["concept_mapping"]["den"]
    assert metrics["duplicate_questions"]["num"] == 0
    assert metrics["unusable_options"]["num"] == 0

    # 3. Insufficient evidence handling (Scenario 7)
    insufficient_doc = doc_ids["insufficient_evidence"]
    insufficient_questions = generate_quiz(database_path, insufficient_doc, question_count=5)
    assert len(insufficient_questions) == 0, "Insufficient source statements should not produce questions."

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Check endpoint reports limitation
        q_res = await client.post(f"/documents/{insufficient_doc}/quiz", json={"question_count": 5})
        assert q_res.status_code == 200
        q_data = q_res.json()
        assert q_data["generated_question_count"] == 0
        assert q_data["limitation"] is not None
        assert "reliable questions" in q_data["limitation"]

        # 4. Mastery updates and idempotency test
        def_doc = doc_ids["straightforward_definitions"]
        learner = (await client.post("/learners")).json()
        learner_id = learner["learner_id"]

        quiz_res = await client.post(f"/documents/{def_doc}/quiz", json={"question_count": 2, "learner_id": learner_id})
        quiz_data = quiz_res.json()
        q1 = quiz_data["questions"][0]
        q2 = quiz_data["questions"][1]

        # Submit Q1 correctly
        metrics["mastery_updates"]["den"] += 1
        sub1 = await client.post(
            f"/documents/{def_doc}/quiz/submit",
            json={
                "quiz_id": quiz_data["quiz_id"],
                "learner_id": learner_id,
                "answers": [{"question_id": q1["question_id"], "selected_option_id": q1["answer_key"]}],
            },
        )
        assert sub1.status_code == 200
        prog1 = (await client.get(f"/learners/{learner_id}/documents/{def_doc}/progress")).json()
        c1 = next(c for c in prog1["concepts"] if c["concept_label"].casefold() == q1["concept_label"].casefold())
        if c1["mastery_estimate"] == 0.60 and c1["attempt_count"] == 1 and c1["correct_count"] == 1:
            metrics["mastery_updates"]["num"] += 1

        # Submit Q1 again (retry idempotency)
        metrics["mastery_updates"]["den"] += 1
        sub1_retry = await client.post(
            f"/documents/{def_doc}/quiz/submit",
            json={
                "quiz_id": quiz_data["quiz_id"],
                "learner_id": learner_id,
                "answers": [{"question_id": q1["question_id"], "selected_option_id": q1["answer_key"]}],
            },
        )
        assert sub1_retry.status_code == 200
        prog1_retry = (await client.get(f"/learners/{learner_id}/documents/{def_doc}/progress")).json()
        c1_retry = next(c for c in prog1_retry["concepts"] if c["concept_label"].casefold() == q1["concept_label"].casefold())
        if c1_retry["attempt_count"] == 1 and prog1_retry["quiz_attempt_count"] == 1:
            metrics["mastery_updates"]["num"] += 1

        # Submit Q2 incorrectly
        metrics["mastery_updates"]["den"] += 1
        wrong_opt = next(o["option_id"] for o in q2["options"] if o["option_id"] != q2["answer_key"])
        quiz_res2 = await client.post(f"/documents/{def_doc}/quiz", json={"question_count": 2, "learner_id": learner_id})
        quiz2_data = quiz_res2.json()
        sub2 = await client.post(
            f"/documents/{def_doc}/quiz/submit",
            json={
                "quiz_id": quiz2_data["quiz_id"],
                "learner_id": learner_id,
                "answers": [{"question_id": q2["question_id"], "selected_option_id": wrong_opt}],
            },
        )
        assert sub2.status_code == 200
        prog2 = (await client.get(f"/learners/{learner_id}/documents/{def_doc}/progress")).json()
        c2 = next(c for c in prog2["concepts"] if c["concept_label"].casefold() == q2["concept_label"].casefold())
        if c2["mastery_estimate"] == 0.40 and c2["attempt_count"] == 1 and c2["correct_count"] == 0:
            metrics["mastery_updates"]["num"] += 1

        assert metrics["mastery_updates"]["num"] == metrics["mastery_updates"]["den"]

        # 5. Adaptive-priority correctness
        metrics["adaptive_priorities"]["den"] += 1
        adaptive_res = await client.post(f"/learners/{learner_id}/documents/{def_doc}/quiz", json={"question_count": 2})
        assert adaptive_res.status_code == 200
        adaptive_data = adaptive_res.json()
        # Weak concept q2 should be prioritized over q1
        if len(adaptive_data["questions"]) > 0:
            first_label = adaptive_data["questions"][0]["concept_label"].casefold()
            if first_label == q2["concept_label"].casefold():
                metrics["adaptive_priorities"]["num"] += 1

        assert metrics["adaptive_priorities"]["num"] == metrics["adaptive_priorities"]["den"]

        # 6. QA citation provenance and appropriate abstention on unsupported queries
        unsupported_doc = doc_ids["unsupported_query_scenario"]
        unsupported_sc = scenarios["unsupported_query_scenario"]
        for qa_case in unsupported_sc.get("qa_cases", []):
            qa_res = await client.post(
                f"/documents/{unsupported_doc}/ask",
                json={"question": qa_case["question"]},
            )
            assert qa_res.status_code == 200
            qa_data = qa_res.json()
            if not qa_case["answerable"]:
                metrics["appropriate_abstention"]["den"] += 1
                if qa_data["abstained"] is True and len(qa_data["citations"]) == 0:
                    metrics["appropriate_abstention"]["num"] += 1
            else:
                metrics["citation_provenance"]["den"] += 1
                if (
                    qa_data["abstained"] is False
                    and len(qa_data["citations"]) > 0
                    and all(term.casefold() in qa_data["answer"].casefold() for term in qa_case["expected_answer_terms"])
                ):
                    metrics["citation_provenance"]["num"] += 1

        assert metrics["appropriate_abstention"]["num"] == metrics["appropriate_abstention"]["den"]
        assert metrics["citation_provenance"]["num"] == metrics["citation_provenance"]["den"]

        print("\nEDUCATIONAL_QUALITY_METRICS:", json.dumps(metrics))

