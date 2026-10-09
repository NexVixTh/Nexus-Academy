from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

import fitz
from lxml.etree import XMLSyntaxError
from pptx import Presentation
from pptx.exc import PackageNotFoundError


SourceType = Literal["page", "slide"]


class UnsupportedDocumentError(ValueError):
    pass


class InvalidDocumentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExtractedRecord:
    source_type: SourceType
    source_number: int
    extracted_text: str
    metadata: dict[str, bool | int]


def extract_document(path: Path, extension: str) -> list[ExtractedRecord]:
    normalized_extension = extension.lower()
    if normalized_extension == ".pdf":
        return _extract_pdf(path)
    if normalized_extension == ".pptx":
        return _extract_pptx(path)
    raise UnsupportedDocumentError("Only PDF and PPTX documents are supported.")


def _extract_pdf(path: Path) -> list[ExtractedRecord]:
    with path.open("rb") as document_file:
        if document_file.read(5) != b"%PDF-":
            raise InvalidDocumentError("The uploaded file is not a valid PDF.")

    try:
        with fitz.open(stream=path.read_bytes(), filetype="pdf") as document:
            if document.is_encrypted:
                raise InvalidDocumentError("Password-protected PDFs are not supported.")
            if document.page_count == 0:
                raise InvalidDocumentError("The PDF contains no pages.")

            records = []
            for page_index in range(document.page_count):
                text = document.load_page(page_index).get_text("text") or ""
                records.append(
                    ExtractedRecord(
                        source_type="page",
                        source_number=page_index + 1,
                        extracted_text=text,
                        metadata={"is_empty": not text.strip(), "text_length": len(text)},
                    )
                )
            return records
    except InvalidDocumentError:
        raise
    except (fitz.FileDataError, OSError, RuntimeError) as exc:
        raise InvalidDocumentError("The PDF file is malformed or unreadable.") from exc


def _extract_pptx(path: Path) -> list[ExtractedRecord]:
    try:
        with ZipFile(path) as package:
            package_parts = set(package.namelist())
            if not {"[Content_Types].xml", "ppt/presentation.xml"}.issubset(package_parts):
                raise InvalidDocumentError("The uploaded file is not a valid PPTX presentation.")

        presentation = Presentation(path)
        if not presentation.slides:
            raise InvalidDocumentError("The PPTX contains no slides.")

        records = []
        for slide_number, slide in enumerate(presentation.slides, start=1):
            text_parts = [
                shape.text
                for shape in slide.shapes
                if shape.has_text_frame and shape.text.strip()
            ]
            text = "\n".join(text_parts)
            records.append(
                ExtractedRecord(
                    source_type="slide",
                    source_number=slide_number,
                    extracted_text=text,
                    metadata={"is_empty": not text.strip(), "text_length": len(text)},
                )
            )
        return records
    except InvalidDocumentError:
        raise
    except (BadZipFile, KeyError, OSError, PackageNotFoundError, ValueError, XMLSyntaxError) as exc:
        raise InvalidDocumentError("The PPTX file is malformed or unreadable.") from exc