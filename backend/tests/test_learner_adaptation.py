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


@pytest.mark.anyio
async def test_simulated_learners_differential_mastery_and_adaptation_audit(
    database_path: Path,
) -> None:
    doc_id = save_test_document(
        database_path,
        [
            (
                "page",
                1,
                "Photosynthesis uses light in plant cells. "
                "Water supports healthy growth in plants. "
                "Green leaves contain many small cells. "
                "Sunlight helps plants make food each day.",
            ),
            (
                "page",
                2,
                "Photosynthesis converts sunlight into sugars. "
                "Roots absorb water from the soil. "
                "Green leaves capture energy from the environment. "
                "Flowers need space to grow well.",
            ),
            (
                "page",
                3,
                "Photosynthesis produces glucose during daytime light cycles. "
                "Water molecules move up through plant vascular channels. "
                "Chloroplasts reside inside active leaf cells. "
                "Stems support leaves above soil level.",
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create Learner 1 (Struggling with photosynthesis) and Learner 2 (Mastering photosynthesis)
        learner1 = await create_learner(client)
        learner2 = await create_learner(client)
        l1_id, l2_id = learner1["learner_id"], learner2["learner_id"]

        # Initial quiz for both learners
        quiz1 = await make_quiz(client, doc_id, l1_id, count=2)
        quiz2 = await make_quiz(client, doc_id, l2_id, count=2)
        assert len(quiz1["questions"]) >= 1
        assert len(quiz2["questions"]) >= 1

        # Learner 1 answers incorrectly on first question
        q1 = quiz1["questions"][0]
        wrong_opt1 = next(o["option_id"] for o in q1["options"] if o["option_id"] != q1["answer_key"])
        sub1 = await submit_answers(
            client, doc_id, l1_id, quiz1,
            [{"question_id": q1["question_id"], "selected_option_id": wrong_opt1}]
        )
        assert sub1.status_code == 200

        # Repeated submission for Learner 1 (must be idempotent, not double-counted)
        sub1_retry = await submit_answers(
            client, doc_id, l1_id, quiz1,
            [{"question_id": q1["question_id"], "selected_option_id": wrong_opt1}]
        )
        assert sub1_retry.status_code == 200

        # Learner 2 answers correctly on the same question
        q2 = quiz2["questions"][0]
        sub2 = await submit_answers(
            client, doc_id, l2_id, quiz2,
            [{"question_id": q2["question_id"], "selected_option_id": q2["answer_key"]}]
        )
        assert sub2.status_code == 200

        # Inspect progress for both learners
        p1 = (await client.get(f"/learners/{l1_id}/progress")).json()
        p2 = (await client.get(f"/learners/{l2_id}/progress")).json()

        # Verify retry idempotency: exactly 1 attempt counted despite retry
        assert p1["quiz_attempt_count"] == 1
        assert p1["question_attempt_count"] == 1
        assert p2["quiz_attempt_count"] == 1
        assert p2["question_attempt_count"] == 1

        # Verify mastery divergence
        c1_label = q1["concept_label"]
        c1_prog = next(c for c in p1["concepts_attempted"] if c["concept_label"] == c1_label)
        c2_prog = next(c for c in p2["concepts_attempted"] if c["concept_label"] == c1_label)
        assert c1_prog["correct_count"] == 0
        assert c2_prog["correct_count"] == 1
        assert c1_prog["mastery_estimate"] < c2_prog["mastery_estimate"]

        # Learner 1 must have c1_label in weak concepts
        assert any(c["concept_label"] == c1_label for c in p1["weak_concepts"])
        # Learner 2 must NOT have c1_label in weak concepts
        assert not any(c["concept_label"] == c1_label for c in p2["weak_concepts"])

        # Request adaptive follow-up quiz for Learner 1: struggling concept must be prioritized
        l1_adaptive = await make_quiz(client, doc_id, l1_id, count=2, adaptive=True)
        assert len(l1_adaptive["questions"]) > 0
        assert l1_adaptive["questions"][0]["concept_label"] == c1_label
        # Must not repeat the exact same question already attempted
        assert l1_adaptive["questions"][0]["question_id"] != q1["question_id"]
        # Next question comes from subsequent pages
        assert l1_adaptive["questions"][0]["page_or_slide_number"] >= 2

        # Check total learner isolation: Learner 1's questions and attempts did not affect Learner 2
        fresh_p2 = (await client.get(f"/learners/{l2_id}/progress")).json()
        assert fresh_p2["question_attempt_count"] == 1
        assert fresh_p2["correct_answer_rate"] == 1.0


@pytest.mark.anyio
async def test_document_progress_endpoint_explainability_and_boundaries(
    database_path: Path,
) -> None:
    doc_id = save_test_document(
        database_path,
        [
            (
                "page",
                1,
                "Photosynthesis uses light in plant cells. "
                "Water supports healthy growth in plants. "
                "Green leaves contain many small cells. "
                "Sunlight helps plants make food each day.",
            ),
            (
                "page",
                2,
                "Photosynthesis converts sunlight into sugars. "
                "Roots absorb water from the soil. "
                "Chloroplasts capture solar energy in leaves. "
                "Flowers need space to grow well.",
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        learner_id = learner["learner_id"]

        # Step 0: Check initial document progress before any attempts
        prog0_res = await client.get(
            f"/learners/{learner_id}/documents/{doc_id}/progress"
        )
        assert prog0_res.status_code == 200
        prog0 = prog0_res.json()
        assert prog0["learner_id"] == learner_id
        assert prog0["document_id"] == doc_id
        assert prog0["quiz_attempt_count"] == 0
        assert prog0["question_attempt_count"] == 0
        assert prog0["correct_answer_rate"] == 0.0
        assert prog0["summary"]["total_document_concepts"] >= 2
        assert prog0["summary"]["attempted_concept_count"] == 0
        assert prog0["summary"]["not_attempted_concept_count"] == prog0["summary"]["total_document_concepts"]
        assert prog0["summary"]["overall_mastery_estimate"] is None

        # Verify unattempted concept properties
        unattempted_c = prog0["concepts"][0]
        assert unattempted_c["learning_status"] == "not_attempted"
        assert unattempted_c["mastery_estimate"] is None
        assert unattempted_c["attempt_count"] == 0
        assert unattempted_c["correct_count"] == 0
        assert unattempted_c["incorrect_count"] == 0
        assert unattempted_c["evidence_sufficient"] is False
        assert "not been tested yet" in unattempted_c["explanation"]
        assert "introductory diagnostic question" in unattempted_c["recommended_action"]
        assert unattempted_c["source_record_id"]
        assert unattempted_c["evidence_excerpt"]

        # Step 1: Exactly 1 correct attempt on concept A
        quiz1 = await make_quiz(client, doc_id, learner_id, count=1)
        q1 = quiz1["questions"][0]
        c1_label = q1["concept_label"]
        await submit_answers(
            client, doc_id, learner_id, quiz1,
            [{"question_id": q1["question_id"], "selected_option_id": q1["answer_key"]}]
        )

        prog1 = (await client.get(f"/learners/{learner_id}/documents/{doc_id}/progress")).json()
        item1 = next(c for c in prog1["concepts"] if c["concept_label"].casefold() == c1_label.casefold())
        # Honest small sample size: 1 attempt gives 3/5 = 0.60, but status is 'learning' with preliminary notice
        assert item1["attempt_count"] == 1
        assert item1["correct_count"] == 1
        assert item1["incorrect_count"] == 0
        assert item1["mastery_estimate"] == 0.60
        assert item1["evidence_sufficient"] is False
        assert item1["learning_status"] == "learning"
        assert "Preliminary evidence (1/1)" in item1["explanation"]
        assert "sample size is too small" in item1["explanation"]

        # Step 2: Second attempt on concept A is incorrect (now 1/2)
        quiz2 = await make_quiz(client, doc_id, learner_id, count=1)
        q2 = quiz2["questions"][0]
        wrong_opt2 = next(o["option_id"] for o in q2["options"] if o["option_id"] != q2["answer_key"])
        await submit_answers(
            client, doc_id, learner_id, quiz2,
            [{"question_id": q2["question_id"], "selected_option_id": wrong_opt2}]
        )

        prog2 = (await client.get(f"/learners/{learner_id}/documents/{doc_id}/progress")).json()
        item2 = next(c for c in prog2["concepts"] if c["concept_label"].casefold() == c1_label.casefold())
        # 1 correct out of 2: (2+1)/(4+2) = 3/6 = 0.50
        assert item2["attempt_count"] == 2
        assert item2["correct_count"] == 1
        assert item2["incorrect_count"] == 1
        assert item2["mastery_estimate"] == 0.50
        assert item2["evidence_sufficient"] is True
        assert item2["learning_status"] == "learning"
        assert "Mixed performance (1/2)" in item2["explanation"]

        # Step 3: Third attempt on concept A is also incorrect (now 1/3) -> transitions to 'struggling'
        quiz3 = await make_quiz(client, doc_id, learner_id, count=1)
        q3 = quiz3["questions"][0]
        wrong_opt3 = next(o["option_id"] for o in q3["options"] if o["option_id"] != q3["answer_key"])
        await submit_answers(
            client, doc_id, learner_id, quiz3,
            [{"question_id": q3["question_id"], "selected_option_id": wrong_opt3}]
        )

        prog3 = (await client.get(f"/learners/{learner_id}/documents/{doc_id}/progress")).json()
        item3 = next(c for c in prog3["concepts"] if c["concept_label"].casefold() == c1_label.casefold())
        # (2+1)/(4+3) = 3/7 = ~0.428 < 0.50 -> struggling
        assert item3["attempt_count"] == 3
        assert item3["correct_count"] == 1
        assert item3["incorrect_count"] == 2
        assert item3["mastery_estimate"] < 0.50
        assert item3["learning_status"] == "struggling"
        assert "Demonstrated low accuracy" in item3["explanation"]
        assert "Revisit cited evidence" in item3["recommended_action"]


@pytest.mark.anyio
async def test_correct_answers_update_only_intended_concept(database_path: Path) -> None:
    doc_id = save_test_document(
        database_path,
        [
            (
                "page",
                1,
                "Photosynthesis uses light in plant cells. "
                "Water supports healthy growth in plants. "
                "Green leaves contain many small cells. "
                "Sunlight helps plants make food each day.",
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        learner_id = learner["learner_id"]

        quiz = await make_quiz(client, doc_id, learner_id, count=1)
        question = quiz["questions"][0]
        target_concept = question["concept_label"].casefold()

        await submit_answers(
            client, doc_id, learner_id, quiz,
            [{"question_id": question["question_id"], "selected_option_id": question["answer_key"]}]
        )

        prog = (await client.get(f"/learners/{learner_id}/documents/{doc_id}/progress")).json()
        target_item = next(c for c in prog["concepts"] if c["concept_label"].casefold() == target_concept)
        assert target_item["attempt_count"] == 1
        assert target_item["correct_count"] == 1

        # All other concepts in the document must remain unattempted
        other_items = [c for c in prog["concepts"] if c["concept_label"].casefold() != target_concept]
        assert len(other_items) >= 1
        assert all(c["attempt_count"] == 0 for c in other_items)
        assert all(c["learning_status"] == "not_attempted" for c in other_items)
        assert all(c["mastery_estimate"] is None for c in other_items)


@pytest.mark.anyio
async def test_two_learners_receive_differential_recommendations_and_priorities(
    database_path: Path,
) -> None:
    doc_id = save_test_document(
        database_path,
        [
            (
                "page",
                1,
                "Photosynthesis uses light in plant cells. "
                "Water supports healthy growth in plants. "
                "Green leaves contain many small cells. "
                "Sunlight helps plants make food each day.",
            ),
            (
                "page",
                2,
                "Photosynthesis converts sunlight into sugars. "
                "Water moves through plant roots from soil. "
                "Green leaves capture energy from surroundings. "
                "Flowers need space to grow well.",
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        l1 = (await create_learner(client))["learner_id"]
        l2 = (await create_learner(client))["learner_id"]

        quiz1 = await make_quiz(client, doc_id, l1, count=2)
        q_photo = next(q for q in quiz1["questions"] if "photo" in q["concept_label"].casefold())
        q_water = next(q for q in quiz1["questions"] if "water" in q["concept_label"].casefold())

        # Learner 1 fails photosynthesis, passes water
        wrong_photo = next(o["option_id"] for o in q_photo["options"] if o["option_id"] != q_photo["answer_key"])
        await submit_answers(
            client, doc_id, l1, quiz1,
            [
                {"question_id": q_photo["question_id"], "selected_option_id": wrong_photo},
                {"question_id": q_water["question_id"], "selected_option_id": q_water["answer_key"]},
            ]
        )

        # Learner 2 fails water, passes photosynthesis
        quiz2 = await make_quiz(client, doc_id, l2, count=2)
        q2_photo = next(q for q in quiz2["questions"] if "photo" in q["concept_label"].casefold())
        q2_water = next(q for q in quiz2["questions"] if "water" in q["concept_label"].casefold())
        wrong_water = next(o["option_id"] for o in q2_water["options"] if o["option_id"] != q2_water["answer_key"])
        await submit_answers(
            client, doc_id, l2, quiz2,
            [
                {"question_id": q2_photo["question_id"], "selected_option_id": q2_photo["answer_key"]},
                {"question_id": q2_water["question_id"], "selected_option_id": wrong_water},
            ]
        )

        # Inspect document progress for both learners
        p1 = (await client.get(f"/learners/{l1}/documents/{doc_id}/progress")).json()
        p2 = (await client.get(f"/learners/{l2}/documents/{doc_id}/progress")).json()

        p1_photo = next(c for c in p1["concepts"] if "photo" in c["concept_label"].casefold())
        p1_water = next(c for c in p1["concepts"] if "water" in c["concept_label"].casefold())
        p2_photo = next(c for c in p2["concepts"] if "photo" in c["concept_label"].casefold())
        p2_water = next(c for c in p2["concepts"] if "water" in c["concept_label"].casefold())

        assert p1_photo["mastery_estimate"] < p1_water["mastery_estimate"]
        assert p2_water["mastery_estimate"] < p2_photo["mastery_estimate"]

        # Adaptive quiz for Learner 1 prioritizes photosynthesis
        adapt1 = await make_quiz(client, doc_id, l1, count=1, adaptive=True)
        assert "photo" in adapt1["questions"][0]["concept_label"].casefold()

        # Adaptive quiz for Learner 2 prioritizes water
        adapt2 = await make_quiz(client, doc_id, l2, count=1, adaptive=True)
        assert "water" in adapt2["questions"][0]["concept_label"].casefold()


@pytest.mark.anyio
async def test_document_progress_404_for_unknown_learner_or_document(
    database_path: Path,
) -> None:
    doc_id = save_test_document(
        database_path, [("page", 1, " ".join(REVIEW_STATEMENTS))]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        learner = await create_learner(client)
        learner_id = learner["learner_id"]

        unknown_l = await client.get(f"/learners/nonexistent-id/documents/{doc_id}/progress")
        assert unknown_l.status_code == 404
        assert "Learner not found" in unknown_l.json()["detail"]

        unknown_d = await client.get(f"/learners/{learner_id}/documents/nonexistent-doc/progress")
        assert unknown_d.status_code == 404
        assert "Document not found" in unknown_d.json()["detail"]
