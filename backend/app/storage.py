import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.ingestion import ExtractedRecord


@dataclass(frozen=True, slots=True)
class StoredSourceRecord:
    id: str
    document_id: str
    source_type: Literal["page", "slide"]
    source_number: int
    extracted_text: str


def get_database_path() -> Path:
    configured_path = os.environ.get("NEXUS_DATABASE_PATH")
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parents[2] / "data" / "nexus.db"


def save_document(
    database_path: Path,
    original_filename: str,
    content_type: str,
    records: list[ExtractedRecord],
) -> str:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    document_id = str(uuid4())
    ingested_at = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_records (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                source_type TEXT NOT NULL CHECK (source_type IN ('page', 'slide')),
                source_number INTEGER NOT NULL CHECK (source_number > 0),
                extracted_text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                UNIQUE (document_id, source_type, source_number)
            );
            CREATE INDEX IF NOT EXISTS idx_source_records_document
                ON source_records(document_id);
            """
        )
        connection.execute(
            "INSERT INTO documents (id, original_filename, content_type, ingested_at) "
            "VALUES (?, ?, ?, ?)",
            (document_id, original_filename, content_type, ingested_at),
        )
        connection.executemany(
            "INSERT INTO source_records "
            "(id, document_id, source_type, source_number, extracted_text, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    str(uuid4()),
                    document_id,
                    record.source_type,
                    record.source_number,
                    record.extracted_text,
                    json.dumps(record.metadata, separators=(",", ":")),
                )
                for record in records
            ],
        )

    return document_id


def get_document_source_records(
    database_path: Path,
    document_id: str,
) -> list[StoredSourceRecord] | None:
    if not database_path.is_file():
        return None

    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        document = connection.execute(
            "SELECT 1 FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            return None

        rows = connection.execute(
            "SELECT id, document_id, source_type, source_number, extracted_text "
            "FROM source_records WHERE document_id = ?",
            (document_id,),
        ).fetchall()

    return [
        StoredSourceRecord(
            id=row["id"],
            document_id=row["document_id"],
            source_type=row["source_type"],
            source_number=row["source_number"],
            extracted_text=row["extracted_text"],
        )
        for row in rows
    ]