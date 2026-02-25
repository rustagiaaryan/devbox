"""SQLite persistence for workspace state."""

import sqlite3
import os
from dataclasses import dataclass
from pathlib import Path


def _default_db_path() -> Path:
    base = os.getenv("DEVBOX_DB_DIR")
    if base:
        return Path(base) / "workspaces.db"
    return Path.home() / ".devbox" / "workspaces.db"


# Default DB location: $DEVBOX_DB_DIR/workspaces.db or ~/.devbox/workspaces.db
DEFAULT_DB_PATH = _default_db_path()

# Valid workspace states
STATE_RUNNING = "running"
STATE_STOPPED = "stopped"
STATE_POOL = "pool"    # Warm-pool container, not yet claimed by a user
STATE_ERROR = "error"


@dataclass
class WorkspaceRecord:
    """Represents a single workspace row in the database."""
    id: str            # UUID
    name: str          # User-visible name
    container_id: str  # Docker container ID
    state: str         # 'running' | 'stopped' | 'pool' | 'error'
    template: str      # Template name used to create this workspace
    created_at: str    # ISO-8601 timestamp
    pool_member: bool  # True if this container lives in the warm pool
    cpu: int
    memory: str


class WorkspaceDB:
    """SQLite-backed registry for workspace containers."""

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
        """Create persistence tables if they do not exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id           TEXT PRIMARY KEY,
                name         TEXT UNIQUE NOT NULL,
                container_id TEXT NOT NULL,
                state        TEXT NOT NULL,
                template     TEXT NOT NULL DEFAULT 'base',
                created_at   TEXT NOT NULL,
                pool_member  INTEGER NOT NULL DEFAULT 0,
                cpu          INTEGER NOT NULL DEFAULT 2,
                memory       TEXT NOT NULL DEFAULT '4g'
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def insert_workspace(self, ws: WorkspaceRecord) -> None:
        """Insert a new workspace record. Raises sqlite3.IntegrityError if name exists."""
        self._conn.execute(
            """
            INSERT INTO workspaces
                (id, name, container_id, state, template, created_at, pool_member, cpu, memory)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ws.id,
                ws.name,
                ws.container_id,
                ws.state,
                ws.template,
                ws.created_at,
                int(ws.pool_member),
                ws.cpu,
                ws.memory,
            ),
        )
        self._conn.commit()

    def get_workspace(self, name: str) -> WorkspaceRecord | None:
        """Return a workspace by name, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def get_workspace_by_id(self, workspace_id: str) -> WorkspaceRecord | None:
        """Return a workspace by UUID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_workspaces(self, include_pool: bool = False) -> list[WorkspaceRecord]:
        """Return workspaces ordered by created_at descending.

        Args:
            include_pool: If False (default), excludes warm-pool containers.
        """
        if include_pool:
            rows = self._conn.execute(
                "SELECT * FROM workspaces ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM workspaces WHERE pool_member = 0 ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_pool_members(self) -> list[WorkspaceRecord]:
        """Return all warm-pool containers with state='pool'."""
        rows = self._conn.execute(
            "SELECT * FROM workspaces WHERE pool_member = 1 AND state = ? ORDER BY created_at ASC",
            (STATE_POOL,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count_pool_members(self) -> dict[str, int]:
        """Return pool counts by state: {'pool': N, 'running': M, 'total': T}."""
        rows = self._conn.execute(
            "SELECT state, COUNT(*) as cnt FROM workspaces WHERE pool_member = 1 GROUP BY state"
        ).fetchall()
        counts: dict[str, int] = {}
        total = 0
        for row in rows:
            counts[row["state"]] = row["cnt"]
            total += row["cnt"]
        counts["total"] = total
        return counts

    def set_setting(self, key: str, value: str) -> None:
        """Persist a key/value setting."""
        self._conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Return a setting value or `default` when missing."""
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return default
        return row["value"]

    def set_pool_target(self, size: int) -> None:
        """Persist desired warm pool size."""
        self.set_setting("pool.target_size", str(size))

    def get_pool_target(self, default: int = 0) -> int:
        """Return desired warm pool size."""
        value = self.get_setting("pool.target_size")
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def set_pool_template(self, template: str) -> None:
        """Persist template used for warm pool replenishment."""
        self.set_setting("pool.template", template)

    def get_pool_template(self, default: str = "base") -> str:
        """Return template used for warm pool replenishment."""
        value = self.get_setting("pool.template")
        return value if value else default

    def update_state(self, name: str, state: str) -> None:
        """Update the state of a workspace by name."""
        self._conn.execute(
            "UPDATE workspaces SET state = ? WHERE name = ?", (state, name)
        )
        self._conn.commit()

    def update_state_by_id(self, workspace_id: str, state: str) -> None:
        """Update the state of a workspace by UUID."""
        self._conn.execute(
            "UPDATE workspaces SET state = ? WHERE id = ?", (state, workspace_id)
        )
        self._conn.commit()

    def claim_pool_member(
        self,
        new_name: str,
        template: str | None = None,
    ) -> tuple[WorkspaceRecord, str] | None:
        """Atomically claim the oldest warm pool member.

        Returns:
            `(record, old_name)` when successful, else `None`.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        if template:
            row = self._conn.execute(
                """
                SELECT * FROM workspaces
                WHERE pool_member = 1 AND state = ? AND template = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (STATE_POOL, template),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT * FROM workspaces
                WHERE pool_member = 1 AND state = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (STATE_POOL,),
            ).fetchone()

        if not row:
            self._conn.execute("COMMIT")
            return None

        ws_id = row["id"]
        old_name = row["name"]
        self._conn.execute(
            "UPDATE workspaces SET name = ?, state = ?, pool_member = 0 WHERE id = ?",
            (new_name, STATE_RUNNING, ws_id),
        )
        self._conn.commit()
        claimed = self.get_workspace_by_id(ws_id)
        if not claimed:
            return None
        return claimed, old_name

    def restore_pool_member(self, workspace_id: str, old_name: str) -> None:
        """Roll back a failed pool claim."""
        self._conn.execute(
            """
            UPDATE workspaces
            SET name = ?, state = ?, pool_member = 1
            WHERE id = ?
            """,
            (old_name, STATE_POOL, workspace_id),
        )
        self._conn.commit()

    def delete_workspace(self, name: str) -> None:
        """Delete a workspace record by name."""
        self._conn.execute("DELETE FROM workspaces WHERE name = ?", (name,))
        self._conn.commit()

    def delete_workspace_by_id(self, workspace_id: str) -> None:
        """Delete a workspace record by UUID."""
        self._conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            id=row["id"],
            name=row["name"],
            container_id=row["container_id"],
            state=row["state"],
            template=row["template"],
            created_at=row["created_at"],
            pool_member=bool(row["pool_member"]),
            cpu=row["cpu"],
            memory=row["memory"],
        )
