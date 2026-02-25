"""Docker client interactions for workspace management.

This module wraps the docker-py SDK and provides high-level operations
used by workspace commands.

Phase 2 implementation plan:
  - create_workspace_container(name, image, cpu, memory) -> Container
  - list_workspace_containers() -> list[Container]
  - get_workspace_container(name) -> Container | None
  - destroy_workspace_container(name, force) -> None
  - exec_into_container(name) -> None  (subprocess for interactive TTY)
"""
