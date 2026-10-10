import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol, Sequence
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.ingestion import (
    MAX_DOCUMENT_IMAGE_SIZE,
    MAX_SINGLE_IMAGE_SIZE,
    ExtractedAsset,
    ExtractedRecord,
)


@dataclass(frozen=True, slots=True)
class StoredSourceRecord:
    id: str
    document_id: str
    source_type: Literal["page", "slide"]
    source_number: int
    extracted_text: str


@dataclass(frozen=True, slots=True)
class StoredDocumentAsset:
    asset_id: str
    document_id: str
    slide_number: int
    mime_type: str
    width: int
    height: int
    content_hash: str
    byte_size: int


class QuizOptionData(Protocol):
    option_id: str
    text: str


class QuizQuestionData(Protocol):
    question_id: str
    question_text: str
    options: Sequence[QuizOptionData]
    answer_key: str
    source_record_id: str
    source_type: str
    page_or_slide_number: int
    supporting_excerpt: str
    concept_label: str
    difficulty: Literal["introductory", "standard"]


class QuizAnswerData(Protocol):
    question_id: str
    selected_option_id: str


@dataclass(frozen=True, slots=True)
class StoredQuizOption:
    option_id: str
    text: str


@dataclass(frozen=True, slots=True)
class StoredQuizQuestion:
    question_id: str
    question_text: str
    options: tuple[StoredQuizOption, ...]
    answer_key: str
    source_record_id: str
    source_type: Literal["page", "slide"]
    page_or_slide_number: int
    supporting_excerpt: str
    difficulty: Literal["introductory", "standard"]


@dataclass(frozen=True, slots=True)
class StoredQuizSession:
    quiz_id: str
    document_id: str
    learner_id: str | None
    questions: tuple[StoredQuizQuestion, ...]


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    learner_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class LearnerConceptProgress:
    document_id: str
    concept_label: str
    attempt_count: int
    correct_count: int
    mastery_estimate: float
    recent_performance: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class LearnerProgress:
    profile: LearnerProfile
    quiz_attempt_count: int
    question_attempt_count: int
    correct_question_count: int
    concepts: tuple[LearnerConceptProgress, ...]


@dataclass(frozen=True, slots=True)
class LearnerAdaptiveContext:
    concepts: tuple[LearnerConceptProgress, ...]
    attempted_question_ids: frozenset[str]


class QuizDocumentNotFoundError(LookupError):
    pass


class QuizSourceIntegrityError(ValueError):
    pass


class AssetStorageError(ValueError):
    pass


class LearnerNotFoundError(LookupError):
    pass


class LearnerDocumentNotFoundError(LookupError):
    pass


class LearnerQuizOwnershipError(ValueError):
    pass


_QUIZ_CONCEPT_PATTERN = re.compile(
    r'^Which source statement(?: on (?:page|slide) \d+)? '
    r'explicitly mentions the term "([^\"]+)"\?$'
)


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
        _ensure_asset_tables(connection)
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
        for record in records:
            for asset in record.assets:
                _save_document_asset(
                    connection,
                    database_path,
                    document_id,
                    record.source_number,
                    asset,
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


def get_document_assets(
    database_path: Path,
    document_id: str,
) -> list[StoredDocumentAsset] | None:
    if not database_path.is_file():
        return None

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        _ensure_asset_tables(connection)
        document = connection.execute(
            "SELECT 1 FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            return None
        rows = connection.execute(
            "SELECT a.asset_id, da.document_id, da.slide_number, a.mime_type, "
            "a.width, a.height, a.content_hash, a.byte_size "
            "FROM document_assets da JOIN assets a ON a.asset_id = da.asset_id "
            "WHERE da.document_id = ? ORDER BY da.slide_number, a.asset_id",
            (document_id,),
        ).fetchall()

    return [
        StoredDocumentAsset(
            asset_id=row["asset_id"],
            document_id=row["document_id"],
            slide_number=row["slide_number"],
            mime_type=row["mime_type"],
            width=row["width"],
            height=row["height"],
            content_hash=row["content_hash"],
            byte_size=row["byte_size"],
        )
        for row in rows
    ]


def get_document_asset(
    database_path: Path,
    document_id: str,
    asset_id: str,
) -> StoredDocumentAsset | None:
    if not database_path.is_file():
        return None

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        _ensure_asset_tables(connection)
        row = connection.execute(
            "SELECT a.asset_id, da.document_id, da.slide_number, a.mime_type, "
            "a.width, a.height, a.content_hash, a.byte_size "
            "FROM document_assets da JOIN assets a ON a.asset_id = da.asset_id "
            "WHERE da.document_id = ? AND da.asset_id = ?",
            (document_id, asset_id),
        ).fetchone()
    if row is None:
        return None
    return StoredDocumentAsset(
        asset_id=row["asset_id"],
        document_id=row["document_id"],
        slide_number=row["slide_number"],
        mime_type=row["mime_type"],
        width=row["width"],
        height=row["height"],
        content_hash=row["content_hash"],
        byte_size=row["byte_size"],
    )


def save_quiz_session(
    database_path: Path,
    document_id: str,
    questions: Sequence[QuizQuestionData],
    *,
    learner_id: str | None = None,
) -> str:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    quiz_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _ensure_quiz_tables(connection)
        document = connection.execute(
            "SELECT 1 FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            raise QuizDocumentNotFoundError(document_id)
        if learner_id is not None and connection.execute(
            "SELECT 1 FROM learner_profiles WHERE id = ?",
            (learner_id,),
        ).fetchone() is None:
            raise LearnerNotFoundError(learner_id)

        connection.execute(
            "INSERT INTO quiz_sessions (id, document_id, created_at, learner_id) "
            "VALUES (?, ?, ?, ?)",
            (quiz_id, document_id, created_at, learner_id),
        )

        for question_position, question in enumerate(questions):
            source_record = connection.execute(
                "SELECT source_type, source_number, extracted_text FROM source_records "
                "WHERE id = ? AND document_id = ?",
                (question.source_record_id, document_id),
            ).fetchone()
            expected_source_type = {
                "pdf_page": "page",
                "pptx_slide": "slide",
            }.get(question.source_type)
            if (
                source_record is None
                or source_record[0] != expected_source_type
                or source_record[1] != question.page_or_slide_number
                or question.supporting_excerpt not in source_record[2]
            ):
                raise QuizSourceIntegrityError(
                    "Quiz question source does not match a persisted document record."
                )

            connection.execute(
                "INSERT INTO quiz_questions "
                "(quiz_id, question_id, question_position, question_text, answer_key, "
                "source_record_id, source_type, source_number, supporting_excerpt, difficulty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    quiz_id,
                    question.question_id,
                    question_position,
                    question.question_text,
                    question.answer_key,
                    question.source_record_id,
                    source_record[0],
                    source_record[1],
                    question.supporting_excerpt,
                    question.difficulty,
                ),
            )
            connection.executemany(
                "INSERT INTO quiz_options "
                "(quiz_id, question_id, option_position, option_id, option_text) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (quiz_id, question.question_id, position, option.option_id, option.text)
                    for position, option in enumerate(question.options)
                ],
            )

    return quiz_id


def get_quiz_session(
    database_path: Path,
    document_id: str,
    quiz_id: str,
) -> StoredQuizSession | None:
    if not database_path.is_file():
        return None

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _ensure_quiz_tables(connection)
        session = connection.execute(
            "SELECT id, learner_id FROM quiz_sessions WHERE id = ? AND document_id = ?",
            (quiz_id, document_id),
        ).fetchone()
        if session is None:
            return None

        question_rows = connection.execute(
            "SELECT question_id, question_text, answer_key, source_record_id, source_type, "
            "source_number, supporting_excerpt, difficulty FROM quiz_questions "
            "WHERE quiz_id = ? ORDER BY question_position",
            (quiz_id,),
        ).fetchall()
        questions: list[StoredQuizQuestion] = []
        for row in question_rows:
            option_rows = connection.execute(
                "SELECT option_id, option_text FROM quiz_options "
                "WHERE quiz_id = ? AND question_id = ? ORDER BY option_position",
                (quiz_id, row[0]),
            ).fetchall()
            questions.append(
                StoredQuizQuestion(
                    question_id=row[0],
                    question_text=row[1],
                    options=tuple(
                        StoredQuizOption(option_id=option[0], text=option[1])
                        for option in option_rows
                    ),
                    answer_key=row[2],
                    source_record_id=row[3],
                    source_type=row[4],
                    page_or_slide_number=row[5],
                    supporting_excerpt=row[6],
                    difficulty=row[7],
                )
            )

    return StoredQuizSession(
        quiz_id=quiz_id,
        document_id=document_id,
        learner_id=session[1],
        questions=tuple(questions),
    )


def _ensure_quiz_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS learner_profiles (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS quiz_sessions (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            learner_id TEXT REFERENCES learner_profiles(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS quiz_questions (
            quiz_id TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL,
            question_position INTEGER NOT NULL CHECK (question_position >= 0),
            question_text TEXT NOT NULL,
            answer_key TEXT NOT NULL CHECK (answer_key IN ('A', 'B', 'C', 'D')),
            source_record_id TEXT NOT NULL REFERENCES source_records(id),
            source_type TEXT NOT NULL CHECK (source_type IN ('page', 'slide')),
            source_number INTEGER NOT NULL CHECK (source_number > 0),
            supporting_excerpt TEXT NOT NULL,
            difficulty TEXT NOT NULL DEFAULT 'introductory'
                CHECK (difficulty IN ('introductory', 'standard')),
            PRIMARY KEY (quiz_id, question_id),
            UNIQUE (quiz_id, question_position)
        );
        CREATE TABLE IF NOT EXISTS quiz_options (
            quiz_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            option_position INTEGER NOT NULL CHECK (option_position >= 0),
            option_id TEXT NOT NULL CHECK (option_id IN ('A', 'B', 'C', 'D')),
            option_text TEXT NOT NULL,
            PRIMARY KEY (quiz_id, question_id, option_id),
            UNIQUE (quiz_id, question_id, option_position),
            FOREIGN KEY (quiz_id, question_id)
                REFERENCES quiz_questions(quiz_id, question_id) ON DELETE CASCADE
        );
        """
    )
    quiz_session_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(quiz_sessions)")
    }
    if "learner_id" not in quiz_session_columns:
        connection.execute(
            "ALTER TABLE quiz_sessions ADD COLUMN learner_id TEXT "
            "REFERENCES learner_profiles(id) ON DELETE SET NULL"
        )
    quiz_question_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(quiz_questions)")
    }
    if "difficulty" not in quiz_question_columns:
        connection.execute(
            "ALTER TABLE quiz_questions ADD COLUMN difficulty TEXT NOT NULL "
            "DEFAULT 'introductory' CHECK (difficulty IN ('introductory', 'standard'))"
        )


def create_learner_profile(database_path: Path) -> LearnerProfile:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    learner_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(database_path)) as connection, connection:
        _ensure_learner_tables(connection)
        connection.execute(
            "INSERT INTO learner_profiles (id, created_at) VALUES (?, ?)",
            (learner_id, created_at),
        )
    return LearnerProfile(learner_id=learner_id, created_at=created_at)


def get_learner_progress(
    database_path: Path,
    learner_id: str,
) -> LearnerProgress | None:
    if not database_path.is_file():
        return None

    with closing(sqlite3.connect(database_path)) as connection, connection:
        _ensure_learner_tables(connection)
        profile_row = connection.execute(
            "SELECT id, created_at FROM learner_profiles WHERE id = ?",
            (learner_id,),
        ).fetchone()
        if profile_row is None:
            return None

        quiz_attempt_count = connection.execute(
            "SELECT COUNT(*) FROM learner_quiz_attempts WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()[0]
        question_stats = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_correct), 0) "
            "FROM learner_question_attempts WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        concept_rows = connection.execute(
            "SELECT document_id, concept_label, attempt_count, correct_count, "
            "mastery_estimate, recent_performance "
            "FROM learner_concept_mastery WHERE learner_id = ? "
            "ORDER BY document_id, concept_label",
            (learner_id,),
        ).fetchall()

    return LearnerProgress(
        profile=LearnerProfile(learner_id=profile_row[0], created_at=profile_row[1]),
        quiz_attempt_count=quiz_attempt_count,
        question_attempt_count=question_stats[0],
        correct_question_count=question_stats[1],
        concepts=tuple(
            LearnerConceptProgress(
                document_id=row[0],
                concept_label=row[1],
                attempt_count=row[2],
                correct_count=row[3],
                mastery_estimate=row[4],
                recent_performance=tuple(bool(value) for value in json.loads(row[5])),
            )
            for row in concept_rows
        ),
    )


def get_learner_adaptive_context(
    database_path: Path,
    learner_id: str,
    document_id: str,
) -> LearnerAdaptiveContext:
    if not database_path.is_file():
        raise LearnerNotFoundError(learner_id)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        _ensure_learner_tables(connection)
        if connection.execute(
            "SELECT 1 FROM learner_profiles WHERE id = ?", (learner_id,)
        ).fetchone() is None:
            raise LearnerNotFoundError(learner_id)
        if connection.execute(
            "SELECT 1 FROM documents WHERE id = ?", (document_id,)
        ).fetchone() is None:
            raise LearnerDocumentNotFoundError(document_id)

        concept_rows = connection.execute(
            "SELECT document_id, concept_label, attempt_count, correct_count, "
            "mastery_estimate, recent_performance FROM learner_concept_mastery "
            "WHERE learner_id = ? AND document_id = ? ORDER BY concept_label",
            (learner_id, document_id),
        ).fetchall()
        attempted_question_rows = connection.execute(
            "SELECT DISTINCT question_id FROM learner_question_attempts "
            "WHERE learner_id = ? AND document_id = ?",
            (learner_id, document_id),
        ).fetchall()

    return LearnerAdaptiveContext(
        concepts=tuple(
            LearnerConceptProgress(
                document_id=row[0],
                concept_label=row[1],
                attempt_count=row[2],
                correct_count=row[3],
                mastery_estimate=row[4],
                recent_performance=tuple(bool(value) for value in json.loads(row[5])),
            )
            for row in concept_rows
        ),
        attempted_question_ids=frozenset(row[0] for row in attempted_question_rows),
    )


def record_learner_quiz_attempt(
    database_path: Path,
    learner_id: str,
    document_id: str,
    quiz_id: str,
    answers: Sequence[QuizAnswerData],
) -> bool:
    canonical_answers = sorted(
        (answer.question_id, answer.selected_option_id) for answer in answers
    )
    submission_hash = hashlib.sha256(
        json.dumps(canonical_answers, separators=(",", ":")).encode()
    ).hexdigest()
    attempt_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _ensure_learner_tables(connection)
        if connection.execute(
            "SELECT 1 FROM learner_profiles WHERE id = ?", (learner_id,)
        ).fetchone() is None:
            raise LearnerNotFoundError(learner_id)

        session = connection.execute(
            "SELECT document_id, learner_id FROM quiz_sessions WHERE id = ?",
            (quiz_id,),
        ).fetchone()
        if session is None or session[0] != document_id:
            raise LearnerQuizOwnershipError("Quiz does not belong to this document.")
        if session[1] is not None and session[1] != learner_id:
            raise LearnerQuizOwnershipError("Quiz belongs to a different learner.")
        if session[1] is None:
            claimed = connection.execute(
                "UPDATE quiz_sessions SET learner_id = ? "
                "WHERE id = ? AND learner_id IS NULL",
                (learner_id, quiz_id),
            )
            if claimed.rowcount != 1:
                owner = connection.execute(
                    "SELECT learner_id FROM quiz_sessions WHERE id = ?",
                    (quiz_id,),
                ).fetchone()
                if owner is None or owner[0] != learner_id:
                    raise LearnerQuizOwnershipError("Quiz belongs to a different learner.")

        answer_rows: list[tuple[str, str, bool, str | None, str]] = []
        for answer in answers:
            question = connection.execute(
                "SELECT q.answer_key, q.source_record_id, q.source_type, q.source_number, "
                "q.supporting_excerpt, q.question_text, r.source_type, r.source_number, "
                "r.extracted_text "
                "FROM quiz_questions q JOIN source_records r "
                "ON r.id = q.source_record_id AND r.document_id = ? "
                "WHERE q.quiz_id = ? AND q.question_id = ?",
                (document_id, quiz_id, answer.question_id),
            ).fetchone()
            if (
                question is None
                or question[4] not in question[8]
                or question[2] != question[6]
                or question[3] != question[7]
            ):
                raise QuizSourceIntegrityError(
                    "Quiz answer does not reference a persisted source record."
                )
            valid_option = connection.execute(
                "SELECT 1 FROM quiz_options WHERE quiz_id = ? AND question_id = ? "
                "AND option_id = ?",
                (quiz_id, answer.question_id, answer.selected_option_id),
            ).fetchone()
            if valid_option is None:
                raise ValueError("Selected option does not belong to this quiz question.")

            if question[2] not in ("page", "slide") or question[3] < 1:
                raise QuizSourceIntegrityError("Quiz source location is invalid.")
            concept_match = _QUIZ_CONCEPT_PATTERN.fullmatch(question[5])
            concept_label = concept_match.group(1).casefold() if concept_match else None
            answer_rows.append(
                (
                    answer.question_id,
                    answer.selected_option_id,
                    answer.selected_option_id == question[0],
                    concept_label,
                    question[1],
                )
            )

        inserted = connection.execute(
            "INSERT OR IGNORE INTO learner_quiz_attempts "
            "(id, learner_id, document_id, quiz_id, submission_hash, answered_count, "
            "correct_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                learner_id,
                document_id,
                quiz_id,
                submission_hash,
                len(answer_rows),
                sum(row[2] for row in answer_rows),
                created_at,
            ),
        )
        if inserted.rowcount == 0:
            return False

        recent_by_concept: dict[str, list[bool]] = {}
        for question_id, selected_option_id, is_correct, concept_label, source_record_id in answer_rows:
            connection.execute(
                "INSERT INTO learner_question_attempts "
                "(attempt_id, learner_id, document_id, quiz_id, question_id, concept_label, "
                "selected_option_id, is_correct, source_record_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    learner_id,
                    document_id,
                    quiz_id,
                    question_id,
                    concept_label,
                    selected_option_id,
                    int(is_correct),
                    source_record_id,
                    created_at,
                ),
            )
            if concept_label is not None:
                recent_by_concept.setdefault(concept_label, []).append(is_correct)

        for concept_label, new_results in recent_by_concept.items():
            current = connection.execute(
                "SELECT attempt_count, correct_count, recent_performance "
                "FROM learner_concept_mastery WHERE learner_id = ? AND document_id = ? "
                "AND concept_label = ?",
                (learner_id, document_id, concept_label),
            ).fetchone()
            previous_attempts, previous_correct = (current[0], current[1]) if current else (0, 0)
            recent = json.loads(current[2]) if current else []
            recent.extend(int(result) for result in new_results)
            recent = recent[-5:]
            attempt_count = previous_attempts + len(new_results)
            correct_count = previous_correct + sum(new_results)
            mastery_estimate = (2.0 + correct_count) / (4.0 + attempt_count)
            connection.execute(
                "INSERT INTO learner_concept_mastery "
                "(learner_id, document_id, concept_label, attempt_count, correct_count, "
                "mastery_estimate, recent_performance, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(learner_id, document_id, concept_label) DO UPDATE SET "
                "attempt_count = excluded.attempt_count, "
                "correct_count = excluded.correct_count, "
                "mastery_estimate = excluded.mastery_estimate, "
                "recent_performance = excluded.recent_performance, "
                "updated_at = excluded.updated_at",
                (
                    learner_id,
                    document_id,
                    concept_label,
                    attempt_count,
                    correct_count,
                    mastery_estimate,
                    json.dumps(recent, separators=(",", ":")),
                    created_at,
                ),
            )

    return True


def _ensure_learner_tables(connection: sqlite3.Connection) -> None:
    _ensure_quiz_tables(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS learner_quiz_attempts (
            id TEXT PRIMARY KEY,
            learner_id TEXT NOT NULL REFERENCES learner_profiles(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            quiz_id TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
            submission_hash TEXT NOT NULL,
            answered_count INTEGER NOT NULL CHECK (answered_count >= 0),
            correct_count INTEGER NOT NULL CHECK (correct_count >= 0),
            created_at TEXT NOT NULL,
            UNIQUE (learner_id, quiz_id, submission_hash)
        );
        CREATE TABLE IF NOT EXISTS learner_question_attempts (
            attempt_id TEXT NOT NULL REFERENCES learner_quiz_attempts(id) ON DELETE CASCADE,
            learner_id TEXT NOT NULL REFERENCES learner_profiles(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            quiz_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            concept_label TEXT,
            selected_option_id TEXT NOT NULL,
            is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
            source_record_id TEXT NOT NULL REFERENCES source_records(id),
            created_at TEXT NOT NULL,
            PRIMARY KEY (attempt_id, question_id),
            FOREIGN KEY (quiz_id, question_id)
                REFERENCES quiz_questions(quiz_id, question_id)
        );
        CREATE TABLE IF NOT EXISTS learner_concept_mastery (
            learner_id TEXT NOT NULL REFERENCES learner_profiles(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            concept_label TEXT NOT NULL,
            attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
            correct_count INTEGER NOT NULL CHECK (correct_count >= 0),
            mastery_estimate REAL NOT NULL CHECK (mastery_estimate >= 0 AND mastery_estimate <= 1),
            recent_performance TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (learner_id, document_id, concept_label)
        );
        CREATE INDEX IF NOT EXISTS idx_learner_attempts_profile
            ON learner_quiz_attempts(learner_id);
        CREATE INDEX IF NOT EXISTS idx_learner_questions_concept
            ON learner_question_attempts(learner_id, document_id, concept_label);
        """
    )


def get_asset_directory(database_path: Path) -> Path:
    return database_path.parent / "assets"


def _ensure_asset_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            width INTEGER NOT NULL CHECK (width > 0),
            height INTEGER NOT NULL CHECK (height > 0),
            byte_size INTEGER NOT NULL CHECK (byte_size > 0),
            storage_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS document_assets (
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
            slide_number INTEGER NOT NULL CHECK (slide_number > 0),
            PRIMARY KEY (document_id, asset_id, slide_number)
        );
        CREATE INDEX IF NOT EXISTS idx_document_assets_document_slide
            ON document_assets(document_id, slide_number);
        """
    )


def _save_document_asset(
    connection: sqlite3.Connection,
    database_path: Path,
    document_id: str,
    slide_number: int,
    asset: ExtractedAsset,
) -> None:
    expected_hash = hashlib.sha256(asset.data).hexdigest()
    if (
        slide_number < 1
        or asset.slide_number != slide_number
        or asset.width < 1
        or asset.height < 1
        or asset.width * asset.height > 100_000_000
        or len(asset.data) > MAX_SINGLE_IMAGE_SIZE
        or expected_hash != asset.content_hash
    ):
        raise AssetStorageError("Extracted image failed metadata or size validation.")

    extensions = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tif",
    }
    extension = extensions.get(asset.mime_type)
    if extension is None:
        raise AssetStorageError("Unsupported extracted image format.")

    asset_id = str(uuid5(NAMESPACE_URL, f"nexus-academy:raster:{asset.content_hash}"))
    storage_key = f"{asset.content_hash[:2]}/{asset_id}{extension}"
    existing_document_assets = connection.execute(
        "SELECT DISTINCT a.asset_id, a.byte_size FROM document_assets da "
        "JOIN assets a ON a.asset_id = da.asset_id WHERE da.document_id = ?",
        (document_id,),
    ).fetchall()
    existing_asset_ids = {row[0] for row in existing_document_assets}
    existing_bytes = sum(row[1] for row in existing_document_assets)
    if asset_id not in existing_asset_ids and existing_bytes + len(asset.data) > MAX_DOCUMENT_IMAGE_SIZE:
        raise AssetStorageError("Extracted images exceed the document asset-size limit.")

    connection.execute(
        "INSERT OR IGNORE INTO assets "
        "(asset_id, content_hash, mime_type, width, height, byte_size, storage_key, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            asset_id,
            asset.content_hash,
            asset.mime_type,
            asset.width,
            asset.height,
            len(asset.data),
            storage_key,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    stored = connection.execute(
        "SELECT asset_id, mime_type, width, height, byte_size, storage_key "
        "FROM assets WHERE content_hash = ?",
        (asset.content_hash,),
    ).fetchone()
    if (
        stored is None
        or stored[0] != asset_id
        or stored[1:5] != (asset.mime_type, asset.width, asset.height, len(asset.data))
        or stored[5] != storage_key
    ):
        raise AssetStorageError("Stored image metadata conflicts with its content hash.")

    asset_root = get_asset_directory(database_path).resolve()
    relative_key = Path(storage_key)
    if relative_key.is_absolute() or ".." in relative_key.parts:
        raise AssetStorageError("Invalid managed asset key.")
    asset_path = (asset_root / relative_key).resolve()
    if asset_root not in asset_path.parents:
        raise AssetStorageError("Invalid managed asset location.")
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    if not asset_path.is_file() or hashlib.sha256(asset_path.read_bytes()).hexdigest() != expected_hash:
        temporary_path = asset_path.with_name(f".{asset_path.name}.{uuid4().hex}.tmp")
        try:
            with temporary_path.open("xb") as asset_file:
                asset_file.write(asset.data)
            temporary_path.replace(asset_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    connection.execute(
        "INSERT OR IGNORE INTO document_assets (document_id, asset_id, slide_number) "
        "VALUES (?, ?, ?)",
        (document_id, asset_id, slide_number),
    )