"""SQLite persistence for workspace state.

Tracks container metadata so workspaces survive Docker daemon restarts
and CLI invocations. All workspace state lives in a local SQLite file
(default: ~/.devbox/workspaces.db).

Phase 2 implementation plan:
  Schema:
    workspaces(
      id TEXT PRIMARY KEY,
      name TEXT UNIQUE NOT NULL,
      container_id TEXT,
      state TEXT,          -- 'running' | 'stopped' | 'pool' | 'error'
      image TEXT,
      created_at TEXT,
      pool_member INTEGER  -- 1 if this container is part of the warm pool
    )

  WorkspaceDB class:
    - __init__(self, db_path: Path)
    - create_tables() -> None
    - insert_workspace(workspace: WorkspaceRecord) -> None
    - get_workspace(name: str) -> WorkspaceRecord | None
    - list_workspaces() -> list[WorkspaceRecord]
    - delete_workspace(name: str) -> None
    - update_state(name: str, state: str) -> None
"""
