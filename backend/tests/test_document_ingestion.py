import json
import sqlite3
from pathlib import Path
from typing import Callable

import fitz
import httpx
import pytest
from pptx import Presentation
from pptx.util import Inches

from app.ingestion import extract_document
from app.main import app
from app.storage import get_database_path


def create_pdf(path: Path) -> bytes:
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "First page")
    document.new_page()
    third_page = document.new_page()
    third_page.insert_text((72, 72), "Third page")
    document.save(path)
    document.close()
    return path.read_bytes()


def create_pptx(path: Path) -> bytes:
    presentation = Presentation()
    first_slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    text_box = first_slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    text_box.text_frame.text = "First slide"
    presentation.slides.add_slide(presentation.slide_layouts[6])
    presentation.save(path)
    return path.read_bytes()


@pytest.fixture
def database_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "test-nexus.sqlite3"
    monkeypatch.setenv("NEXUS_DATABASE_PATH", str(path))
    return path


@pytest.mark.anyio
async def test_health_endpoint_remains_available() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pdf_extraction_preserves_page_numbers_and_empty_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "lesson.pdf"
    create_pdf(pdf_path)

    records = extract_document(pdf_path, ".pdf")

    assert [record.source_number for record in records] == [1, 2, 3]
    assert [record.source_type for record in records] == ["page", "page", "page"]
    assert "First page" in records[0].extracted_text
    assert records[1].extracted_text == ""
    assert records[1].metadata["is_empty"] is True
    assert "Third page" in records[2].extracted_text


def test_pptx_extraction_preserves_slide_numbers_and_empty_slides(tmp_path: Path) -> None:
    pptx_path = tmp_path / "lesson.pptx"
    create_pptx(pptx_path)

    records = extract_document(pptx_path, ".pptx")

    assert [record.source_number for record in records] == [1, 2]
    assert [record.source_type for record in records] == ["slide", "slide"]
    assert records[0].extracted_text == "First slide"
    assert records[1].extracted_text == ""
    assert records[1].metadata["is_empty"] is True


@pytest.mark.anyio
async def test_upload_rejects_unsupported_extension() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/documents", files={"file": ("notes.docx", b"not supported")}
        )

    assert response.status_code == 415


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("broken.pdf", b"%PDF-1.7 malformed"),
        ("broken.pptx", b"not a zip package"),
    ],
)
async def test_upload_rejects_malformed_documents(filename: str, content: bytes) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/documents", files={"file": (filename, content)})

    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_rejects_files_over_20_mib() -> None:
    oversized_pdf = b"%PDF-1.7" + b"x" * (20 * 1024 * 1024)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/documents", files={"file": ("large.pdf", oversized_pdf)}
        )

    assert response.status_code == 413


@pytest.mark.parametrize(
    ("filename", "create_document", "source_type", "expected_records"),
    [
        (
            "course-notes.pdf",
            create_pdf,
            "page",
            [("First page", False), ("", True), ("Third page", False)],
        ),
        (
            "course-slides.pptx",
            create_pptx,
            "slide",
            [("First slide", False), ("", True)],
        ),
    ],
)
@pytest.mark.anyio
async def test_upload_persists_document_and_source_records(
    database_path: Path,
    tmp_path: Path,
    filename: str,
    create_document: Callable[[Path], bytes],
    source_type: str,
    expected_records: list[tuple[str, bool]],
) -> None:
    assert get_database_path() == database_path
    document_content = create_document(tmp_path / filename)
    content_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/documents",
            files={"file": (filename, document_content, content_type)},
        )

    assert response.status_code == 201
    result = response.json()
    assert result["pages_or_slides_processed"] == len(expected_records)
    assert result["records_created"] == len(expected_records)
    assert "extracted_text" not in result

    with sqlite3.connect(database_path) as connection:
        document = connection.execute(
            "SELECT id, original_filename, content_type, ingested_at "
            "FROM documents WHERE id = ?",
            (result["document_id"],),
        ).fetchone()
        records = connection.execute(
            "SELECT id, document_id, source_type, source_number, extracted_text, metadata_json "
            "FROM source_records WHERE document_id = ? ORDER BY source_number",
            (result["document_id"],),
        ).fetchall()

    assert document is not None
    assert document[0] == result["document_id"]
    assert document[1:3] == (filename, content_type)
    assert document[3]
    assert len(records) == len(expected_records)
    assert len({record[0] for record in records}) == len(expected_records)
    assert all(record[0] for record in records)
    assert all(record[1] == result["document_id"] for record in records)
    assert [(record[2], record[3]) for record in records] == [
        (source_type, source_number)
        for source_number in range(1, len(expected_records) + 1)
    ]
    assert [record[4].strip() for record in records] == [
        expected_text for expected_text, _ in expected_records
    ]
    assert [json.loads(record[5])["is_empty"] for record in records] == [
        is_empty for _, is_empty in expected_records
    ]