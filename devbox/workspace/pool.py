"""Warm workspace pool logic."""

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from devbox.workspace.db import (
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
    template: str  # Template used for replenishment


def _pool_container_name_unique() -> str:
    """Generate a unique pool container name using a short UUID."""
    return f"devbox-pool-{uuid.uuid4().hex[:8]}"


class PoolManager:
    """Manages a warm pool of Docker containers for fast workspace provisioning."""

    def __init__(self, db: WorkspaceDB | None = None) -> None:
        self.db = db or WorkspaceDB()

    def initialize(self, size: int, template: str = "base") -> list[WorkspaceRecord]:
        """Set pool target and create warm containers until target is met.

        Containers are named devbox-pool-<uuid> and started with
        `sleep infinity` so they stay alive until claimed.

        Args:
            size:     Number of containers to pre-create.
            template: Template (image) to use for pool containers.

        Returns:
            List of WorkspaceRecords for the created containers.
        """
        self.db.set_pool_target(size)
        self.db.set_pool_template(template)
        return self._replenish(template=template, target=size)

    def acquire(self, new_name: str, template: str | None = None) -> WorkspaceRecord | None:
        """Try to claim a warm container from the pool.

        If successful, the container is renamed, marked as 'running', and
        a background thread is spawned to replenish the pool.

        Args:
            new_name: The user-supplied workspace name to assign.

        Returns:
            The claimed WorkspaceRecord (already updated in DB), or None
            if the pool is empty.
        """
        claimed = self.db.claim_pool_member(new_name, template=template)
        if not claimed:
            return None

        record, old_name = claimed
        try:
            dc.rename_container(record.container_id, new_name)
        except Exception:
            self.db.restore_pool_member(record.id, old_name)
            return None

        # Replenish in the background so the CLI returns immediately.
        target = self.db.get_pool_target(default=0)
        if target > 0:
            replenish_template = self.db.get_pool_template(default=record.template)
            self._replenish_async(template=replenish_template, target=target)
        return record

    def status(self) -> PoolStatus:
        """Return a snapshot of current pool state."""
        counts = self.db.count_pool_members()
        warm = counts.get(STATE_POOL, 0)
        # Count containers that were pool members but are now in use
        in_use = sum(v for k, v in counts.items() if k not in (STATE_POOL, "total"))
        total = counts.get("total", 0)
        return PoolStatus(
            warm=warm,
            in_use=in_use,
            total=total,
            target=self.db.get_pool_target(default=0),
            template=self.db.get_pool_template(default="base"),
        )

    def _replenish(self, template: str = "base", target: int = 1) -> list[WorkspaceRecord]:
        """Create warm containers until pool has `target` ready members."""
        current_warm = len(self.db.list_pool_members())
        needed = max(0, target - current_warm)
        created: list[WorkspaceRecord] = []
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
            created.append(record)
        return created

    def _replenish_async(self, template: str = "base", target: int = 1) -> None:
        """Spawn a daemon thread to replenish the pool without blocking."""
        def run() -> None:
            try:
                self._replenish(template=template, target=target)
            except Exception:
                # Background replenish failure is intentionally non-fatal.
                return

        t = threading.Thread(
            target=run,
            daemon=True,
        )
        t.start()
