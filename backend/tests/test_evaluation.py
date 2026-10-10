from pathlib import Path
import sys

import pytest
import json

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.storage import StoredSourceRecord
from evaluation.runner import (
    BenchmarkDatasetError,
    _question_quality,
    evaluate_qa_case,
    load_dataset,
    rate,
    render_markdown,
    run_evaluation,
    validate_dataset,
)


def test_rate_reports_explicit_numerator_denominator_and_empty_rate() -> None:
    assert rate(3, 4) == {"numerator": 3, "denominator": 4, "value": 0.75}
    assert rate(0, 0) == {"numerator": 0, "denominator": 0, "value": None}


def test_qa_metrics_distinguish_missing_and_incorrect_citations() -> None:
    record = StoredSourceRecord(
        id="source-1",
        document_id="doc-1",
        source_type="page",
        source_number=3,
        extracted_text="The ammeter measures current in the circuit.",
    )
    case = {
        "answerable": True,
        "expected_source": {"type": "pdf_page", "location": 3},
        "expected_answer_terms": ["ammeter", "current"],
    }
    response_missing_citation = {
        "abstained": False,
        "answer": "The ammeter measures current in the circuit.",
        "citations": [],
    }
    missing = evaluate_qa_case(case, response_missing_citation, {record.id: record})
    assert missing["answerable_covered"] is True
    assert missing["evidence_supported"] is True
    assert missing["citation_source_record_correct"] is False
    assert missing["citation_location_correct"] is False

    response_wrong_citation = {
        **response_missing_citation,
        "citations": [{
            "source_record_id": "forged-id",
            "source_type": "pdf_page",
            "page_or_slide_number": 3,
        }],
    }
    incorrect = evaluate_qa_case(case, response_wrong_citation, {record.id: record})
    assert incorrect["evidence_supported"] is True
    assert incorrect["citation_source_record_correct"] is False
    assert incorrect["citation_location_correct"] is True
    assert incorrect["citation_correct"] is False


def test_qa_metrics_score_abstention_separately() -> None:
    case = {
        "answerable": False,
        "expected_source": None,
        "expected_answer_terms": [],
    }
    abstained = evaluate_qa_case(
        case,
        {"abstained": True, "answer": "No evidence.", "citations": []},
        {},
    )
    unsupported = evaluate_qa_case(
        case,
        {"abstained": False, "answer": "Unsupported answer.", "citations": []},
        {},
    )
    assert abstained == {"abstained": True, "unsupported_answer": False}
    assert unsupported == {"abstained": False, "unsupported_answer": True}


def test_quiz_quality_checks_source_backed_unique_answer_and_filters() -> None:
    source = "Photosynthesis stores light energy in sugars. Water supports growth in plants."
    question = {
        "question_text": 'Which source statement on slide 1 explicitly mentions the term "photosynthesis"?',
        "options": [
            {"option_id": "A", "text": "Photosynthesis stores light energy in sugars."},
            {"option_id": "B", "text": "Water supports growth in plants."},
            {"option_id": "C", "text": "Water supports growth in plants."},
            {"option_id": "D", "text": "Water supports growth in plants."},
        ],
        "answer_key": "A",
    }
    blocked = {"url:", "algorithm explanation"}
    is_valid, key_consistent = _question_quality(question, True, blocked)
    assert key_consistent is True
    assert is_valid is False

    unique_question = {
        **question,
        "options": [
            {"option_id": "A", "text": "Photosynthesis stores light energy in sugars."},
            {"option_id": "B", "text": "Water supports growth in plants."},
            {"option_id": "C", "text": "Chlorophyll absorbs red and blue light."},
            {"option_id": "D", "text": "Roots absorb water from the soil."},
        ],
    }
    is_valid, key_consistent = _question_quality(unique_question, True, blocked)
    assert key_consistent is True
    assert is_valid is True

    url_question = {
        **unique_question,
        "options": [
            {"option_id": "A", "text": "https://example.invalid"},
            *unique_question["options"][1:],
        ],
    }
    assert _question_quality(url_question, True, blocked)[0] is False


def test_dataset_validation_rejects_malformed_source_locations() -> None:
    malformed = {
        "dataset_version": "bad",
        "documents": [{
            "id": "doc",
            "format": "pdf",
            "records": [{"location": 0, "text": "Bad page number."}],
        }],
    }
    with pytest.raises(BenchmarkDatasetError, match="positive integers"):
        validate_dataset(malformed)


@pytest.mark.anyio
async def test_benchmark_runner_uses_temp_database_and_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_database_path = "keep-this-user-setting.db"
    monkeypatch.setenv("NEXUS_DATABASE_PATH", original_database_path)
    dataset = load_dataset()

    report = await run_evaluation(dataset)

    assert report["dataset_version"] == "1.0.0"
    assert report["sample_counts"]["qa_cases"] == len(dataset["qa_cases"])
    assert report["metrics"]["grounded_qa"]["citation_location_accuracy"]["denominator"] == 4
    assert report["metrics"]["quiz"]["quality_rule_satisfaction_rate"]["denominator"] > 0
    assert report["metrics"]["personalization"]["weak_concept_prioritized"]["value"] == 1.0
    assert report["metrics"]["personalization"]["adaptive_exact_repeat_avoidance"]["value"] == 1.0
    assert report["metrics"]["personalization"]["retry_not_double_counted"]["value"] == 1.0
    assert report["metrics"]["grounded_qa"]["unsupported_answer_rate"]["value"] == 0.5
    assert not next(
        check for check in report["checks"] if check["name"] == "no_unsupported_answers"
    )["passed"]
    assert "Ammeter measures current" not in json.dumps(report)
    markdown = render_markdown(report)
    assert "## Sample Counts" in markdown
    assert "| qa cases | 6 |" in markdown
    assert "Ammeter measures current" not in markdown
    assert __import__("os").environ["NEXUS_DATABASE_PATH"] == original_database_path
