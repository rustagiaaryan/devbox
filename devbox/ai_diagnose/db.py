"""SQLite persistence for AI diagnosis history.

Stores diagnosis results locally so developers can review past
diagnoses, spot recurring failures, and avoid redundant API calls
for identical inputs. Default DB location: ~/.devbox/diagnoses.db.

Phase 2 implementation plan:
  Schema:
    diagnoses(
      id TEXT PRIMARY KEY,          -- UUID
      timestamp TEXT NOT NULL,      -- ISO-8601
      model TEXT NOT NULL,
      input_hash TEXT NOT NULL,     -- SHA-256 of raw input log
      failure_type TEXT,
      summary TEXT,
      root_cause TEXT,
      suggested_fixes TEXT,         -- JSON array stored as text
      raw_response TEXT
    )

  DiagnosisDB class:
    - __init__(self, db_path: Path)
    - create_tables() -> None
    - save_diagnosis(result: DiagnosisResult) -> str
        Persists the result and returns the generated UUID.
    - list_diagnoses(limit: int = 20) -> list[DiagnosisResult]
        Returns most-recent diagnoses first.
    - get_diagnosis(id: str) -> DiagnosisResult | None
    - group_by_failure_type() -> dict[str, int]
        Returns counts per failure_type for the --patterns flag.
"""
