import sqlite3
from pathlib import Path
from typing import Literal

import httpx
import pytest
from fastapi import FastAPI

from app.documents import router as documents_router
from app.ingestion import ExtractedRecord
from app.main import app
from app.storage import get_database_path, save_document


SourceLocation = tuple[Literal["page", "slide"], int, str]
REVIEW_STATEMENTS = [
    "Photosynthesis uses light in plant cells.",
    "Water supports healthy growth in plants.",
    "Green leaves contain many small cells.",
    "Sunlight helps plants make food each day.",
]


@pytest.fixture
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "learner-test.sqlite3"
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
    return save_document(
        database_path,
        "learner-test",
        content_type,
        [
            ExtractedRecord(
                source_type=kind,
                source_number=number,
                extracted_text=text,
                metadata={"is_empty": not text.strip(), "text_length": len(text)},
            )
            for kind, number, text in locations
        ],
    )


async def create_learner(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post("/learners")
    assert response.status_code == 201
    return response.json()


async def make_quiz(
    client: httpx.AsyncClient,
    document_id: str,
    learner_id: str,
    *,
    count: int = 1,
    adaptive: bool = False,
) -> dict[str, object]:
    if adaptive:
        response = await client.post(
            f"/learners/{learner_id}/documents/{document_id}/quiz",
            json={"question_count": count},
        )
    else:
        response = await client.post(
            f"/documents/{document_id}/quiz",
            json={"question_count": count, "learner_id": learner_id},
        )
    assert response.status_code == 200, response.text
    return response.json()


async def submit_answers(
    client: httpx.AsyncClient,
    document_id: str,
    learner_id: str,
    quiz: dict[str, object],
    answers: list[dict[str, str]],
) -> httpx.Response:
    return await client.post(
        f"/documents/{document_id}/quiz/submit",
        json={"quiz_id": quiz["quiz_id"], "learner_id": learner_id, "answers": answers},
    )


@pytest.mark.anyio
async def test_new_learner_progress_defaults(database_path: Path) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        response = await client.get(f"/learners/{learner['learner_id']}/progress")

    assert response.status_code == 200
    progress = response.json()
    assert progress["learner_id"] == learner["learner_id"]
    assert progress["quiz_attempt_count"] == 0
    assert progress["question_attempt_count"] == 0
    assert progress["correct_answer_rate"] == 0.0
    assert progress["concepts_attempted"] == []
    assert progress["weak_concepts"] == []
    assert progress["insufficient_evidence_concepts"] == []


@pytest.mark.anyio
async def test_correct_incorrect_and_retried_submissions_update_mastery_once(
    database_path: Path,
) -> None:
    document_id = save_test_document(
        database_path, [("page", 1, " ".join(REVIEW_STATEMENTS))]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        learner_id = learner["learner_id"]

        first_quiz = await make_quiz(client, document_id, learner_id)
        first_question = first_quiz["questions"][0]
        correct_answers = [{
            "question_id": first_question["question_id"],
            "selected_option_id": first_question["answer_key"],
        }]
        first_submission = await submit_answers(
            client, document_id, learner_id, first_quiz, correct_answers
        )
        retry_submission = await submit_answers(
            client, document_id, learner_id, first_quiz, correct_answers
        )
        assert first_submission.status_code == retry_submission.status_code == 200

        first_progress_response = await client.get(f"/learners/{learner_id}/progress")
        first_progress = first_progress_response.json()
        concept_label = first_question["concept_label"]
        mastery_after_correct = next(
            concept["mastery_estimate"]
            for concept in first_progress["concepts_attempted"]
            if concept["concept_label"] == concept_label
        )
        assert first_progress["quiz_attempt_count"] == 1
        assert first_progress["question_attempt_count"] == 1
        assert mastery_after_correct > 0.5

        second_quiz = await make_quiz(client, document_id, learner_id)
        second_question = second_quiz["questions"][0]
        assert second_question["concept_label"] == concept_label
        wrong_option = next(
            option["option_id"]
            for option in second_question["options"]
            if option["option_id"] != second_question["answer_key"]
        )
        wrong_submission = await submit_answers(
            client,
            document_id,
            learner_id,
            second_quiz,
            [{
                "question_id": second_question["question_id"],
                "selected_option_id": wrong_option,
            }],
        )
        assert wrong_submission.status_code == 200

        final_progress_response = await client.get(f"/learners/{learner_id}/progress")

    assert final_progress_response.status_code == 200
    final_progress = final_progress_response.json()
    concept = next(
        concept
        for concept in final_progress["concepts_attempted"]
        if concept["concept_label"] == concept_label
    )
    assert final_progress["quiz_attempt_count"] == 2
    assert final_progress["question_attempt_count"] == 2
    assert concept["question_attempt_count"] == 2
    assert concept["correct_count"] == 1
    assert concept["mastery_estimate"] < mastery_after_correct
    assert concept["recent_accuracy"] == 0.5
    assert concept["evidence_sufficient"] is True


@pytest.mark.anyio
async def test_adaptive_quiz_prioritizes_weak_concepts_and_skips_exact_repeat(
    database_path: Path,
) -> None:
    document_id = save_test_document(
        database_path,
        [
            ("page", 1, " ".join(REVIEW_STATEMENTS)),
            (
                "page",
                2,
                "Photosynthesis converts sunlight into sugars. "
                "Roots absorb water from the soil. Green leaves capture energy. "
                "Flowers need space to grow well.",
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        learner_id = learner["learner_id"]
        first_quiz = await make_quiz(client, document_id, learner_id)
        first_question = first_quiz["questions"][0]
        wrong_option = next(
            option["option_id"]
            for option in first_question["options"]
            if option["option_id"] != first_question["answer_key"]
        )
        submission = await submit_answers(
            client,
            document_id,
            learner_id,
            first_quiz,
            [{"question_id": first_question["question_id"], "selected_option_id": wrong_option}],
        )
        assert submission.status_code == 200

        adaptive_quiz = await make_quiz(
            client, document_id, learner_id, count=5, adaptive=True
        )

    assert adaptive_quiz["questions"]
    assert adaptive_quiz["questions"][0]["concept_label"] == first_question["concept_label"]
    assert adaptive_quiz["questions"][0]["question_id"] != first_question["question_id"]
    assert adaptive_quiz["questions"][0]["page_or_slide_number"] == 2


@pytest.mark.anyio
async def test_adaptive_quiz_and_progress_are_isolated_by_learner_and_document(
    database_path: Path,
) -> None:
    first_document_id = save_test_document(
        database_path, [("page", 1, " ".join(REVIEW_STATEMENTS))]
    )
    second_document_id = save_test_document(
        database_path,
        [("slide", 8, " ".join([*REVIEW_STATEMENTS, "Nebulas contain gas and dust."]))],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner_a = await create_learner(client)
        learner_b = await create_learner(client)
        quiz = await make_quiz(client, first_document_id, learner_a["learner_id"])
        question = quiz["questions"][0]
        wrong_option = next(
            option["option_id"]
            for option in question["options"]
            if option["option_id"] != question["answer_key"]
        )
        await submit_answers(
            client,
            first_document_id,
            learner_a["learner_id"],
            quiz,
            [{"question_id": question["question_id"], "selected_option_id": wrong_option}],
        )

        isolated_adaptive = await make_quiz(
            client, second_document_id, learner_a["learner_id"], adaptive=True
        )
        other_learner_progress = await client.get(
            f"/learners/{learner_b['learner_id']}/progress"
        )

    assert isolated_adaptive["questions"]
    assert all(
        question["source_type"] == "pptx_slide"
        and question["page_or_slide_number"] == 8
        for question in isolated_adaptive["questions"]
    )
    assert other_learner_progress.status_code == 200
    assert other_learner_progress.json()["quiz_attempt_count"] == 0
    assert other_learner_progress.json()["concepts_attempted"] == []


@pytest.mark.anyio
async def test_unknown_learner_and_document_are_rejected(database_path: Path) -> None:
    document_id = save_test_document(
        database_path, [("page", 1, " ".join(REVIEW_STATEMENTS))]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        unknown_progress = await client.get("/learners/unknown-learner/progress")
        unknown_learner_quiz = await client.post(
            f"/learners/unknown-learner/documents/{document_id}/quiz",
            json={"question_count": 1},
        )
        learner = await create_learner(client)
        unknown_document_quiz = await client.post(
            f"/learners/{learner['learner_id']}/documents/unknown-document/quiz",
            json={"question_count": 1},
        )

    assert unknown_progress.status_code == 404
    assert unknown_learner_quiz.status_code == 404
    assert unknown_document_quiz.status_code == 404


@pytest.mark.anyio
async def test_learner_attempts_survive_fresh_application_and_database_connections(
    database_path: Path,
) -> None:
    document_id = save_test_document(
        database_path, [("page", 1, " ".join(REVIEW_STATEMENTS))]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        learner_id = learner["learner_id"]
        quiz = await make_quiz(client, document_id, learner_id)
        question = quiz["questions"][0]
        result = await submit_answers(
            client,
            document_id,
            learner_id,
            quiz,
            [{"question_id": question["question_id"], "selected_option_id": question["answer_key"]}],
        )
        assert result.status_code == 200

    fresh_app = FastAPI()
    fresh_app.include_router(documents_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fresh_app), base_url="http://test"
    ) as new_client:
        progress_response = await new_client.get(f"/learners/{learner_id}/progress")

    assert progress_response.status_code == 200
    assert progress_response.json()["quiz_attempt_count"] == 1
    assert progress_response.json()["question_attempt_count"] == 1