"""Warm workspace pool logic.

Manages a pool of pre-created Docker containers to minimize workspace
creation latency. This mirrors the warm-pool strategy in Snowflake's
Cloud Workspaces, where idle containers are kept ready so that
`devbox workspace create` can return in seconds instead of minutes.

How it works:
  1. `pool init --size N` pre-creates N containers with placeholder names
     like `devbox-pool-0`, `devbox-pool-1`, ... and marks them state='pool'.
  2. When `workspace create` is called, the PoolManager checks for a warm
     container. If found, it claims it (renames + marks running) immediately.
     It then triggers a background replenish to bring the pool back to
     its target size.
  3. If no warm container is available, `create` falls back to cold-starting
     a new container (slower path).
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from devbox.workspace.db import (
    DEFAULT_DB_PATH,
    STATE_POOL,
    WorkspaceDB,
    WorkspaceRecord,
)
from devbox.workspace import docker_client as dc


@dataclass
class PoolStatus:
    """Snapshot of current pool state."""
    warm: int      # Containers ready to be claimed (state='pool')
    in_use: int    # Containers claimed from pool and now running
    total: int     # warm + in_use (all pool-origin containers)
    target: int    # Desired pool size (set at init time, stored in DB)


def _pool_container_name(index: int) -> str:
    """Generate a deterministic pool container name."""
    return f"devbox-pool-{index}"


def _pool_container_name_unique() -> str:
    """Generate a unique pool container name using a short UUID."""
    return f"devbox-pool-{uuid.uuid4().hex[:8]}"


class PoolManager:
    """Manages a warm pool of Docker containers for fast workspace provisioning."""

    def __init__(self, db: WorkspaceDB | None = None) -> None:
        self.db = db or WorkspaceDB()

    def initialize(self, size: int, template: str = "base") -> list[WorkspaceRecord]:
        """Pre-create `size` idle containers and register them in the pool.

        Containers are named devbox-pool-<uuid> and started with
        `sleep infinity` so they stay alive until claimed.

        Args:
            size:     Number of containers to pre-create.
            template: Template (image) to use for pool containers.

        Returns:
            List of WorkspaceRecords for the created containers.
        """
        created: list[WorkspaceRecord] = []
        for _ in range(size):
            name = _pool_container_name_unique()
            container = dc.create_container(
                name=name,
                template=template,
                cpu=2,
                memory="4g",
            )
            record = WorkspaceRecord(
                id=str(uuid.uuid4()),
                name=name,
                container_id=container.id,
                state=STATE_POOL,
                template=template,
                created_at=datetime.now(timezone.utc).isoformat(),
                pool_member=True,
                cpu=2,
                memory="4g",
            )
            self.db.insert_workspace(record)
            created.append(record)
        return created

    def acquire(self, new_name: str) -> WorkspaceRecord | None:
        """Try to claim a warm container from the pool.

        If successful, the container is renamed, marked as 'running', and
        a background thread is spawned to replenish the pool.

        Args:
            new_name: The user-supplied workspace name to assign.

        Returns:
            The claimed WorkspaceRecord (already updated in DB), or None
            if the pool is empty.
        """
        record = self.db.claim_pool_member(new_name)
        if record:
            # Replenish in the background so the CLI returns immediately
            self._replenish_async(template=record.template)
        return record

    def status(self) -> PoolStatus:
        """Return a snapshot of current pool state."""
        counts = self.db.count_pool_members()
        warm = counts.get(STATE_POOL, 0)
        # Count containers that were pool members but are now in use
        in_use = sum(v for k, v in counts.items() if k not in (STATE_POOL, "total"))
        total = counts.get("total", 0)
        return PoolStatus(warm=warm, in_use=in_use, total=total, target=0)

    def _replenish(self, template: str = "base", target: int = 1) -> None:
        """Create new pool containers to restore the pool to `target` size.

        Called in a background thread — errors are swallowed so they
        don't crash the main CLI process.
        """
        try:
            current_warm = self.db.count_pool_members().get(STATE_POOL, 0)
            needed = max(0, target - current_warm)
            for _ in range(needed):
                name = _pool_container_name_unique()
                container = dc.create_container(
                    name=name,
                    template=template,
                    cpu=2,
                    memory="4g",
                )
                record = WorkspaceRecord(
                    id=str(uuid.uuid4()),
                    name=name,
                    container_id=container.id,
                    state=STATE_POOL,
                    template=template,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    pool_member=True,
                    cpu=2,
                    memory="4g",
                )
                self.db.insert_workspace(record)
        except Exception:
            # Background replenish failure is non-fatal
            pass

    def _replenish_async(self, template: str = "base", target: int = 1) -> None:
        """Spawn a daemon thread to replenish the pool without blocking."""
        t = threading.Thread(
            target=self._replenish,
            kwargs={"template": template, "target": target},
            daemon=True,
        )
        t.start()
