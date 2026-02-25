"""Warm workspace pool logic.

Manages a pool of pre-created Docker containers to minimize
workspace creation latency — mirroring the warm pool strategy
used in Snowflake's Cloud Workspaces product.

Phase 2 implementation plan:
  PoolManager class:
    - __init__(self, db: WorkspaceDB, docker: DockerClient)
    - initialize(size: int) -> None
        Pre-creates `size` containers from the configured template.
    - acquire() -> Container
        Returns a warm container and triggers background refill to
        maintain pool size.
    - release(container_id: str) -> None
        Returns a container to the pool (or destroys it if pool is full).
    - status() -> PoolStatus
        Returns a dataclass: total, warm, in_use counts.
"""
