import sqlite3
from pathlib import Path
from typing import Literal

import httpx
import pytest

from app.ingestion import ExtractedRecord
from app.main import app
from app.storage import get_database_path, save_document


SourceLocation = tuple[Literal["page", "slide"], int, str]


@pytest.fixture
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "search-test.sqlite3"
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
    return save_document(database_path, "search-test", content_type, records)


async def request_search(
    document_id: str,
    query: str,
    limit: int | None = None,
) -> httpx.Response:
    params: dict[str, str | int] = {"q": query}
    if limit is not None:
        params["limit"] = limit

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(f"/documents/{document_id}/search", params=params)


@pytest.mark.anyio
async def test_search_matches_exact_terms_only(database_path: Path) -> None:
    document_id = save_test_document(
        database_path,
        [("page", 1, "Concatenate strings safely."), ("page", 2, "A cat sits here.")],
    )

    response = await request_search(document_id, "CAT")

    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["page_or_slide_number"] for result in results] == [2]
    assert results[0]["source_type"] == "pdf_page"
    assert "cat" in results[0]["excerpt"].casefold()


@pytest.mark.anyio
async def test_search_ranks_matches_deterministically(database_path: Path) -> None:
    document_id = save_test_document(
        database_path,
        [("page", 1, "alpha beta"), ("page", 2, "alpha"), ("page", 3, "beta")],
    )

    first_response = await request_search(document_id, "alpha beta")
    second_response = await request_search(document_id, "alpha beta")

    assert first_response.status_code == 200
    results = first_response.json()["results"]
    assert [result["page_or_slide_number"] for result in results] == [1, 2, 3]
    assert [result["score"] for result in results] == sorted(
        (result["score"] for result in results), reverse=True
    )
    assert first_response.json() == second_response.json()


@pytest.mark.anyio
async def test_search_returns_no_results_for_irrelevant_query(database_path: Path) -> None:
    document_id = save_test_document(database_path, [("page", 1, "algebra equations")])

    response = await request_search(document_id, "volcano")

    assert response.status_code == 200
    assert response.json() == {"document_id": document_id, "results": []}


@pytest.mark.anyio
async def test_search_excerpt_is_bounded_and_taken_from_source_text(
    database_path: Path,
) -> None:
    source_text = f"{'before ' * 100}target {'after ' * 100}"
    document_id = save_test_document(database_path, [("page", 1, source_text)])

    response = await request_search(document_id, "target")

    excerpt = response.json()["results"][0]["excerpt"]
    assert len(excerpt) <= 500
    assert excerpt in source_text
    assert "target" in excerpt


@pytest.mark.anyio
@pytest.mark.parametrize("query", ["", "   ", "!!!"])
async def test_search_rejects_blank_or_non_searchable_queries(
    database_path: Path, query: str
) -> None:
    document_id = save_test_document(database_path, [("page", 1, "sample text")])

    response = await request_search(document_id, query)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_search_enforces_result_limit_and_validates_bounds(
    database_path: Path,
) -> None:
    document_id = save_test_document(
        database_path,
        [("page", number, "common keyword") for number in range(1, 8)],
    )

    default_response = await request_search(document_id, "keyword")
    limited_response = await request_search(document_id, "keyword", limit=2)
    zero_limit_response = await request_search(document_id, "keyword", limit=0)
    excessive_limit_response = await request_search(document_id, "keyword", limit=51)

    assert len(default_response.json()["results"]) == 5
    assert len(limited_response.json()["results"]) == 2
    assert zero_limit_response.status_code == 422
    assert excessive_limit_response.status_code == 422


@pytest.mark.anyio
async def test_search_returns_404_for_missing_document(database_path: Path) -> None:
    existing_document_id = save_test_document(
        database_path, [("page", 1, "should not be returned")]
    )

    response = await request_search("missing-document-id", "returned")

    assert response.status_code == 404
    assert existing_document_id not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("locations", "query", "expected_source_type", "expected_number"),
    [
        ([("page", 4, "pdf provenance marker")], "provenance", "pdf_page", 4),
        ([("slide", 3, "pptx provenance marker")], "provenance", "pptx_slide", 3),
    ],
)
async def test_search_returns_persisted_pdf_and_pptx_provenance(
    database_path: Path,
    locations: list[SourceLocation],
    query: str,
    expected_source_type: str,
    expected_number: int,
) -> None:
    document_id = save_test_document(database_path, locations)

    with sqlite3.connect(database_path) as connection:
        expected_record_id = connection.execute(
            "SELECT id FROM source_records WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]

    response = await request_search(document_id, query)

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["document_id"] == document_id
    assert result["source_record_id"] == expected_record_id
    assert result["source_type"] == expected_source_type
    assert result["page_or_slide_number"] == expected_number
    assert query in result["excerpt"]
    assert result["score"] > 0


@pytest.mark.anyio
async def test_search_is_isolated_to_requested_document(database_path: Path) -> None:
    first_document_id = save_test_document(
        database_path, [("page", 1, "shared keyword first document")]
    )
    second_document_id = save_test_document(
        database_path, [("slide", 1, "shared keyword second document")]
    )

    response = await request_search(first_document_id, "shared")

    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["document_id"] for result in results] == [first_document_id]
    assert all(result["document_id"] != second_document_id for result in results)