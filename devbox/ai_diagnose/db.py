"""SQLite persistence for AI diagnosis history."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from devbox.ai_diagnose.analyzer import DiagnosisResult


def _default_db_path() -> Path:
    base = os.getenv("DEVBOX_DB_DIR")
    if base:
        return Path(base) / "diagnoses.db"
    return Path.home() / ".devbox" / "diagnoses.db"


DEFAULT_DB_PATH = _default_db_path()


@dataclass
class StoredDiagnosis:
    """Persisted diagnosis row."""

    id: str
    timestamp: str
    target: str | None
    model: str
    input_hash: str
    failure_type: str
    summary: str
    root_cause: str
    suggested_fixes: list[str]
    raw_response: str


class DiagnosisDB:
    """SQLite-backed store for diagnosis results."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        except (OSError, sqlite3.OperationalError):
            fallback = Path.cwd() / ".devbox" / db_path.name
            fallback.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = fallback
            self._conn = sqlite3.connect(str(fallback), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self) -> None:
        """Create diagnosis table and indexes."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnoses (
                id              TEXT PRIMARY KEY,
                timestamp       TEXT NOT NULL,
                target          TEXT,
                model           TEXT NOT NULL,
                input_hash      TEXT NOT NULL,
                failure_type    TEXT NOT NULL,
                summary         TEXT NOT NULL,
                root_cause      TEXT NOT NULL,
                suggested_fixes TEXT NOT NULL,
                raw_response    TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_diagnoses_timestamp ON diagnoses(timestamp DESC)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_diagnoses_target ON diagnoses(target)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_diagnoses_failure_type ON diagnoses(failure_type)"
        )
        self._conn.commit()

    def save_diagnosis(self, result: DiagnosisResult) -> str:
        """Persist a diagnosis and return the generated row ID."""
        diagnosis_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO diagnoses (
                id, timestamp, target, model, input_hash, failure_type,
                summary, root_cause, suggested_fixes, raw_response
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                diagnosis_id,
                timestamp,
                result.target,
                result.model,
                result.input_hash,
                result.failure_type,
                result.summary,
                result.root_cause,
                json.dumps(result.suggested_fixes),
                result.raw_response,
            ),
        )
        self._conn.commit()
        return diagnosis_id

    def list_diagnoses(self, limit: int = 20) -> list[StoredDiagnosis]:
        """Return most recent diagnoses first."""
        rows = self._conn.execute(
            """
            SELECT * FROM diagnoses
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def group_by_failure_type(self) -> list[tuple[str, int]]:
        """Aggregate diagnosis counts by failure type."""
        rows = self._conn.execute(
            """
            SELECT failure_type, COUNT(*) AS cnt
            FROM diagnoses
            GROUP BY failure_type
            ORDER BY cnt DESC, failure_type ASC
            """
        ).fetchall()
        return [(row["failure_type"], row["cnt"]) for row in rows]

    def group_by_target(self, limit: int = 10) -> list[tuple[str, int]]:
        """Aggregate diagnosis counts by target label."""
        rows = self._conn.execute(
            """
            SELECT COALESCE(target, '(unknown)') AS target_name, COUNT(*) AS cnt
            FROM diagnoses
            GROUP BY target_name
            ORDER BY cnt DESC, target_name ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [(row["target_name"], row["cnt"]) for row in rows]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> StoredDiagnosis:
        fixes_raw = row["suggested_fixes"]
        try:
            fixes = json.loads(fixes_raw)
            if not isinstance(fixes, list):
                fixes = []
        except json.JSONDecodeError:
            fixes = []
        return StoredDiagnosis(
            id=row["id"],
            timestamp=row["timestamp"],
            target=row["target"],
            model=row["model"],
            input_hash=row["input_hash"],
            failure_type=row["failure_type"],
            summary=row["summary"],
            root_cause=row["root_cause"],
            suggested_fixes=[str(item) for item in fixes],
            raw_response=row["raw_response"],
        )
