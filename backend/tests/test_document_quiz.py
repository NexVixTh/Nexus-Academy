import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Literal

import httpx
import pytest
from fastapi import FastAPI

from app.documents import router as documents_router
from app.ingestion import ExtractedRecord
from app.main import app
from app.quiz import generate_quiz, validate_quiz_questions
from app.storage import get_database_path, save_document


SourceLocation = tuple[Literal["page", "slide"], int, str]
SUITABLE_STATEMENTS = [
    "Mercury rotates slowly around the distant Sun.",
    "Glaciers reshape valleys through persistent erosion.",
    "Photosynthesis converts sunlight into chemical energy.",
    "Granite forms when magma cools beneath Earth's surface.",
    "Astronomers classify stars according to their spectral properties.",
]


@pytest.fixture
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "quiz-test.sqlite3"
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
    return save_document(database_path, "quiz-test", content_type, records)


async def request_quiz(
    document_id: str,
    question_count: int | None = None,
) -> httpx.Response:
    payload = {} if question_count is None else {"question_count": question_count}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            f"/documents/{document_id}/quiz",
            json=payload,
        )


async def submit_quiz(
    document_id: str,
    quiz_id: str,
    answers: list[dict[str, str]] | None = None,
    *,
    fresh_app: bool = False,
) -> httpx.Response:
    target_app = FastAPI() if fresh_app else app
    if fresh_app:
        target_app.include_router(documents_router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=target_app), base_url="http://test"
    ) as client:
        return await client.post(
            f"/documents/{document_id}/quiz/submit",
            json={"quiz_id": quiz_id, "answers": answers or []},
        )


async def create_suitable_quiz(database_path: Path) -> tuple[str, dict[str, object]]:
    document_id = save_test_document(
        database_path, [("page", 6, " ".join(SUITABLE_STATEMENTS))]
    )
    response = await request_quiz(document_id, question_count=3)
    assert response.status_code == 200
    return document_id, response.json()


def _all_source_records(database_path: Path, document_id: str) -> dict[str, tuple[str, int, str]]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id, source_type, source_number, extracted_text "
            "FROM source_records WHERE document_id = ?",
            (document_id,),
        ).fetchall()
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


@pytest.mark.anyio
async def test_quiz_generates_source_backed_questions_with_four_options(
    database_path: Path,
) -> None:
    document_id = save_test_document(
        database_path,
        [("page", 2, " ".join(SUITABLE_STATEMENTS))],
    )

    response = await request_quiz(document_id, question_count=4)

    assert response.status_code == 200
    result = response.json()
    assert result["document_id"] == document_id
    assert result["requested_question_count"] == 4
    assert result["generated_question_count"] == 4
    assert result["limitation"] is None

    persisted_records = _all_source_records(database_path, document_id)
    questions = result["questions"]
    assert len(questions) == 4
    assert len({question["question_id"] for question in questions}) == 4
    assert len({question["question_text"] for question in questions}) == 4

    for question in questions:
        options = question["options"]
        assert len(options) == 4
        assert {option["option_id"] for option in options} == {"A", "B", "C", "D"}
        assert len({option["text"] for option in options}) == 4
        assert question["answer_key"] in {option["option_id"] for option in options}
        correct_option = next(
            option for option in options if option["option_id"] == question["answer_key"]
        )
        assert correct_option["text"] == question["supporting_excerpt"]

        stored_source_type, stored_number, stored_text = persisted_records[
            question["source_record_id"]
        ]
        assert question["source_type"] == "pdf_page"
        assert stored_source_type == "page"
        assert question["page_or_slide_number"] == stored_number == 2
        assert question["supporting_excerpt"] in stored_text
        assert all(option["text"] in stored_text for option in options)


@pytest.mark.anyio
async def test_quiz_preserves_source_whitespace_and_skips_invalid_candidates(
    database_path: Path,
) -> None:
    statements = [
        "Mercury rotates  slowly around the distant Sun.",
        "Glaciers reshape valleys through persistent erosion.",
        "Photosynthesis converts sunlight into chemical energy.",
        "Granite forms when magma cools beneath Earth's surface.",
        "Astronomers classify stars according to their spectral properties.",
    ]
    source_text = " ".join(statements)
    document_id = save_test_document(database_path, [("slide", 15, source_text)])

    response = await request_quiz(document_id, question_count=2)

    assert response.status_code == 200
    questions = response.json()["questions"]
    assert len(questions) == 2
    assert all(question["supporting_excerpt"] in source_text for question in questions)
    assert all(
        option["text"] in source_text
        for question in questions
        for option in question["options"]
    )

    generated = generate_quiz(database_path, document_id, question_count=10)
    invalid_candidate = replace(
        generated[0],
        supporting_excerpt=f"not persisted: {generated[0].supporting_excerpt}",
    )
    remaining_valid = validate_quiz_questions(
        database_path,
        document_id,
        [invalid_candidate, *generated],
        skip_invalid=True,
    )
    assert remaining_valid == generated


@pytest.mark.anyio
async def test_quiz_filters_urls_and_generic_headings_but_keeps_acronyms(
    database_path: Path,
) -> None:
    statements = [
        "https://forms.gle/example-form",
        "URL:",
        "QR CODE:",
        "Algorithm Explanation",
        "Naive Method",
        "NASA uses radar to map distant galaxies.",
        *SUITABLE_STATEMENTS,
    ]
    document_id = save_test_document(database_path, [("slide", 3, "\n".join(statements))])

    response = await request_quiz(document_id, question_count=10)

    assert response.status_code == 200
    questions = response.json()["questions"]
    all_option_text = [
        option["text"]
        for question in questions
        for option in question["options"]
    ]
    assert questions
    assert any("NASA" in question["supporting_excerpt"] for question in questions)
    assert not any("https://" in option for option in all_option_text)
    assert not any(
        option.casefold() in {"url:", "qr code:", "algorithm explanation", "naive method"}
        for option in all_option_text
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("source_type", "source_number", "expected_label"),
    [("page", 7, "pdf_page"), ("slide", 5, "pptx_slide")],
)
async def test_quiz_citations_preserve_pdf_and_pptx_locations(
    database_path: Path,
    source_type: Literal["page", "slide"],
    source_number: int,
    expected_label: str,
) -> None:
    document_id = save_test_document(
        database_path,
        [(source_type, source_number, " ".join(SUITABLE_STATEMENTS))],
    )

    response = await request_quiz(document_id, question_count=1)

    assert response.status_code == 200
    question = response.json()["questions"][0]
    stored_record = _all_source_records(database_path, document_id)[
        question["source_record_id"]
    ]
    assert question["source_type"] == expected_label
    assert stored_record[0] == source_type
    assert question["page_or_slide_number"] == stored_record[1] == source_number
    assert question["supporting_excerpt"] in stored_record[2]


@pytest.mark.anyio
async def test_quiz_does_not_leak_records_from_another_document(
    database_path: Path,
) -> None:
    first_document_id = save_test_document(
        database_path,
        [("page", 1, " ".join(SUITABLE_STATEMENTS))],
    )
    second_document_id = save_test_document(
        database_path,
        [("slide", 9, " ".join(SUITABLE_STATEMENTS))],
    )
    second_source_ids = set(_all_source_records(database_path, second_document_id))

    response = await request_quiz(first_document_id, question_count=5)

    assert response.status_code == 200
    questions = response.json()["questions"]
    assert questions
    assert all(question["source_record_id"] not in second_source_ids for question in questions)
    assert all(question["source_type"] == "pdf_page" for question in questions)
    assert all(question["page_or_slide_number"] == 1 for question in questions)


@pytest.mark.anyio
async def test_quiz_deduplicates_repeated_source_statements(database_path: Path) -> None:
    statements = [*SUITABLE_STATEMENTS, SUITABLE_STATEMENTS[0], SUITABLE_STATEMENTS[1]]
    document_id = save_test_document(database_path, [("page", 1, " ".join(statements))])

    first_response = await request_quiz(document_id, question_count=10)
    second_response = await request_quiz(document_id, question_count=10)

    assert first_response.status_code == 200
    questions = first_response.json()["questions"]
    assert len({question["question_text"] for question in questions}) == len(questions)
    assert len({question["question_id"] for question in questions}) == len(questions)
    assert first_response.json()["quiz_id"] != second_response.json()["quiz_id"]
    assert first_response.json()["questions"] == second_response.json()["questions"]


@pytest.mark.anyio
async def test_quiz_returns_fewer_questions_with_explanation_for_short_source(
    database_path: Path,
) -> None:
    document_id = save_test_document(
        database_path,
        [("page", 1, "The sun is bright. The moon is visible. Stars appear at night.")],
    )

    response = await request_quiz(document_id, question_count=5)

    assert response.status_code == 200
    result = response.json()
    assert result["questions"] == []
    assert result["generated_question_count"] == 0
    assert result["limitation"]


@pytest.mark.anyio
@pytest.mark.parametrize("question_count", [0, 11, -1])
async def test_quiz_rejects_invalid_question_counts(
    database_path: Path,
    question_count: int,
) -> None:
    document_id = save_test_document(
        database_path, [("page", 1, " ".join(SUITABLE_STATEMENTS))]
    )

    response = await request_quiz(document_id, question_count)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_quiz_defaults_to_five_questions(database_path: Path) -> None:
    document_id = save_test_document(
        database_path, [("page", 1, " ".join(SUITABLE_STATEMENTS))]
    )

    response = await request_quiz(document_id)

    assert response.status_code == 200
    assert response.json()["requested_question_count"] == 5
    assert len(response.json()["questions"]) <= 5


@pytest.mark.anyio
async def test_quiz_returns_not_found_for_missing_document(database_path: Path) -> None:
    response = await request_quiz("missing-document-id", question_count=1)

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


@pytest.mark.anyio
async def test_submit_quiz_scores_all_correct_answers_and_validates_feedback(
    database_path: Path,
) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)
    answers = [
        {
            "question_id": question["question_id"],
            "selected_option_id": question["answer_key"],
        }
        for question in quiz["questions"]
    ]

    response = await submit_quiz(document_id, quiz["quiz_id"], answers)

    assert response.status_code == 200
    result = response.json()
    assert result["total_questions"] == 3
    assert result["answered_count"] == 3
    assert result["correct_count"] == 3
    assert result["score_percentage_of_answered"] == 100.0
    for submitted, question_result in zip(answers, result["results"], strict=True):
        assert question_result["question_id"] == submitted["question_id"]
        assert question_result["selected_option_id"] == submitted["selected_option_id"]
        assert question_result["is_correct"] is True
        assert question_result["correct_option_id"] == submitted["selected_option_id"]
        assert question_result["feedback"].startswith("Correct. The source states:")
        with sqlite3.connect(database_path) as connection:
            source_record = connection.execute(
                "SELECT document_id, source_type, source_number, extracted_text "
                "FROM source_records WHERE id = ?",
                (question_result["source_record_id"],),
            ).fetchone()
        assert source_record is not None
        assert source_record[0] == document_id
        assert source_record[1] == "page"
        assert source_record[2] == question_result["page_or_slide_number"] == 6
        assert question_result["source_type"] == "pdf_page"
        assert question_result["supporting_excerpt"] in source_record[3]
        assert question_result["supporting_excerpt"] in question_result["feedback"]


@pytest.mark.anyio
async def test_submit_quiz_scores_all_incorrect_answers(database_path: Path) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)
    answers = []
    for question in quiz["questions"]:
        wrong_option = next(
            option["option_id"]
            for option in question["options"]
            if option["option_id"] != question["answer_key"]
        )
        answers.append(
            {"question_id": question["question_id"], "selected_option_id": wrong_option}
        )

    response = await submit_quiz(document_id, quiz["quiz_id"], answers)

    assert response.status_code == 200
    result = response.json()
    assert result["total_questions"] == 3
    assert result["answered_count"] == 3
    assert result["correct_count"] == 0
    assert result["score_percentage_of_answered"] == 0.0
    assert all(question["is_correct"] is False for question in result["results"])
    assert all(
        question["feedback"].startswith("Not correct. The source states:")
        for question in result["results"]
    )


@pytest.mark.anyio
async def test_submit_quiz_scores_only_answered_questions(database_path: Path) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)
    questions = quiz["questions"]
    wrong_option = next(
        option["option_id"]
        for option in questions[1]["options"]
        if option["option_id"] != questions[1]["answer_key"]
    )
    answers = [
        {
            "question_id": questions[0]["question_id"],
            "selected_option_id": questions[0]["answer_key"],
        },
        {
            "question_id": questions[1]["question_id"],
            "selected_option_id": wrong_option,
        },
    ]

    response = await submit_quiz(document_id, quiz["quiz_id"], answers)

    assert response.status_code == 200
    result = response.json()
    assert result["total_questions"] == 3
    assert result["answered_count"] == 2
    assert result["correct_count"] == 1
    assert result["score_percentage_of_answered"] == 50.0
    assert [question["is_correct"] for question in result["results"]] == [True, False, None]
    assert result["results"][2]["selected_option_id"] is None
    assert result["results"][2]["feedback"].startswith("Not answered. The source states:")


@pytest.mark.anyio
async def test_empty_quiz_submission_is_allowed_and_scores_zero(database_path: Path) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)

    response = await submit_quiz(document_id, quiz["quiz_id"])

    assert response.status_code == 200
    result = response.json()
    assert result["total_questions"] == 3
    assert result["answered_count"] == 0
    assert result["correct_count"] == 0
    assert result["score_percentage_of_answered"] == 0.0
    assert all(question["is_correct"] is None for question in result["results"])


@pytest.mark.anyio
async def test_submit_rejects_unknown_questions_and_forged_options(
    database_path: Path,
) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)
    unknown_question = await submit_quiz(
        document_id,
        quiz["quiz_id"],
        [{"question_id": "not-in-this-quiz", "selected_option_id": "A"}],
    )
    forged_option = await submit_quiz(
        document_id,
        quiz["quiz_id"],
        [{"question_id": quiz["questions"][0]["question_id"], "selected_option_id": "Z"}],
    )

    assert unknown_question.status_code == 422
    assert forged_option.status_code == 422


@pytest.mark.anyio
async def test_submit_rejects_duplicate_answers_and_client_supplied_keys(
    database_path: Path,
) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)
    question_id = quiz["questions"][0]["question_id"]
    duplicate_answers = await submit_quiz(
        document_id,
        quiz["quiz_id"],
        [
            {"question_id": question_id, "selected_option_id": "A"},
            {"question_id": question_id, "selected_option_id": "B"},
        ],
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        supplied_key = await client.post(
            f"/documents/{document_id}/quiz/submit",
            json={
                "quiz_id": quiz["quiz_id"],
                "answers": [{
                    "question_id": question_id,
                    "selected_option_id": "A",
                    "answer_key": "A",
                    "source_record_id": "forged-source",
                }],
            },
        )

    assert duplicate_answers.status_code == 422
    assert supplied_key.status_code == 422


@pytest.mark.anyio
async def test_submit_rejects_quiz_from_another_document(database_path: Path) -> None:
    first_document_id, first_quiz = await create_suitable_quiz(database_path)
    second_document_id = save_test_document(
        database_path, [("slide", 2, " ".join(SUITABLE_STATEMENTS))]
    )

    response = await submit_quiz(
        second_document_id,
        first_quiz["quiz_id"],
        [],
    )

    assert first_document_id != second_document_id
    assert response.status_code == 404


@pytest.mark.anyio
async def test_quiz_submission_survives_new_app_and_database_connections(
    database_path: Path,
) -> None:
    document_id, quiz = await create_suitable_quiz(database_path)
    question = quiz["questions"][0]
    answers = [
        {"question_id": question["question_id"], "selected_option_id": question["answer_key"]}
    ]

    response = await submit_quiz(
        document_id,
        quiz["quiz_id"],
        answers,
        fresh_app=True,
    )

    assert response.status_code == 200
    assert response.json()["correct_count"] == 1
    assert response.json()["total_questions"] == 3