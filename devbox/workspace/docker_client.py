"""Docker client interactions for workspace management.

Wraps the docker-py SDK to provide high-level operations for creating,
inspecting, and destroying workspace containers. All container-level
Docker calls go through this module — command logic stays in commands.py.
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import docker
import docker.errors
from docker.models.containers import Container

# Label applied to every devbox-managed container so we can filter them.
DEVBOX_LABEL = "devbox.managed"
DEVBOX_LABEL_VALUE = "true"


def get_client() -> docker.DockerClient:
    """Return a connected Docker client.

    Raises:
        SystemExit: If the Docker daemon is not reachable, prints a clear
            error message and exits — the caller does not need to handle this.
    """
    try:
        client = docker.from_env()
        client.ping()
        return client
    except docker.errors.DockerException:
        from devbox.utils.console import console
        console.print(
            "[bold red]Error:[/bold red] Cannot connect to Docker. "
            "Is Docker Desktop running?\n"
            "Start Docker and try again."
        )
        sys.exit(1)


def create_container(
    name: str,
    template: str,
    cpu: int,
    memory: str,
) -> Container:
    """Create and start a new workspace container.

    The container runs a long-lived sleep process so it stays alive
    and we can exec into it. Resource limits are applied via nano_cpus
    and mem_limit.

    Args:
        name:     Docker container name (must be unique on the host).
        template: Template key. Currently maps to a Docker image tag.
                  Templates are defined in TEMPLATE_IMAGES below.
        cpu:      Number of CPUs to allocate.
        memory:   Memory limit string accepted by Docker (e.g. "4g", "512m").

    Returns:
        The newly created and started Container object.
    """
    client = get_client()
    image = ensure_template_image(client, template)

    container = client.containers.run(
        image=image,
        name=name,
        detach=True,
        # Keep the container alive with an infinite sleep
        command="sleep infinity",
        # Resource limits
        nano_cpus=int(cpu * 1e9),  # docker-py takes nanoseconds
        mem_limit=memory,
        # Label so we can identify devbox containers
        labels={
            DEVBOX_LABEL: DEVBOX_LABEL_VALUE,
            "devbox.template": template,
            "devbox.name": name,
        },
        # Give the container a writable home directory
        working_dir="/workspace",
    )
    return container


def get_container(name: str) -> Container | None:
    """Return a Docker container by name, or None if not found."""
    client = get_client()
    try:
        return client.containers.get(name)
    except docker.errors.NotFound:
        return None


def rename_container(container_id: str, new_name: str) -> None:
    """Rename an existing container."""
    client = get_client()
    container = client.containers.get(container_id)
    container.rename(new_name)


def stop_and_remove_container(container_id: str, force: bool = False) -> None:
    """Stop and remove a container by its Docker container ID.

    Args:
        container_id: Full or short Docker container ID.
        force:        If True, sends SIGKILL instead of waiting for graceful stop.
    """
    client = get_client()
    try:
        container = client.containers.get(container_id)
        if not force:
            container.stop(timeout=10)
        container.remove(force=force)
    except docker.errors.NotFound:
        # Already removed — treat as success
        pass


def exec_into_container(container_id: str) -> None:
    """Attach an interactive shell to a running container.

    Uses subprocess + `docker exec` so the user gets a proper TTY,
    signal handling, and terminal resize support — which the docker-py
    SDK doesn't provide for interactive sessions.

    Args:
        container_id: Full or short Docker container ID.
    """
    cmd = ["docker", "exec", "-it", container_id, "/bin/bash"]
    # Fall back to sh if bash is not available in the image
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        subprocess.run(
            ["docker", "exec", "-it", container_id, "/bin/sh"],
            check=True,
        )


def get_container_stats(container_id: str) -> dict:
    """Return a snapshot of CPU/memory usage for a running container.

    Returns an empty dict if the container is not running or stats
    are unavailable.
    """
    client = get_client()
    try:
        container = client.containers.get(container_id)
        if container.status != "running":
            return {}
        stats = container.stats(stream=False)
        return _parse_stats(stats)
    except (docker.errors.NotFound, KeyError):
        return {}


def get_container_runtime(container_id: str) -> dict:
    """Return live state and uptime seconds for a container."""
    client = get_client()
    try:
        container = client.containers.get(container_id)
        container.reload()
        started_at_raw = container.attrs.get("State", {}).get("StartedAt")
        uptime_seconds = None
        if started_at_raw and started_at_raw != "0001-01-01T00:00:00Z":
            started_at = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
            uptime_seconds = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds()))
        return {
            "state": container.status,
            "uptime_seconds": uptime_seconds,
        }
    except (docker.errors.NotFound, ValueError):
        return {}


def _parse_stats(raw: dict) -> dict:
    """Parse raw Docker stats into human-readable CPU % and memory usage."""
    try:
        # CPU %: delta between readings, scaled by number of CPUs
        cpu_delta = (
            raw["cpu_stats"]["cpu_usage"]["total_usage"]
            - raw["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            raw["cpu_stats"]["system_cpu_usage"]
            - raw["precpu_stats"]["system_cpu_usage"]
        )
        num_cpus = raw["cpu_stats"].get("online_cpus") or len(
            raw["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])
        )
        cpu_pct = (cpu_delta / system_delta) * num_cpus * 100.0 if system_delta > 0 else 0.0

        # Memory
        mem_usage = raw["memory_stats"]["usage"]
        mem_limit = raw["memory_stats"]["limit"]
        mem_pct = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0

        return {
            "cpu_pct": round(cpu_pct, 1),
            "mem_usage_mb": round(mem_usage / 1024 / 1024, 1),
            "mem_limit_mb": round(mem_limit / 1024 / 1024, 1),
            "mem_pct": round(mem_pct, 1),
        }
    except (KeyError, ZeroDivisionError):
        return {}


# ---------------------------------------------------------------------------
# Template registry
# Maps template name -> Docker image. In a real system this would be read
# from a config file. For the demo, we use lightweight publicly available images.
# ---------------------------------------------------------------------------

TEMPLATE_IMAGES: dict[str, str] = {
    "base": "ubuntu:22.04",
    "python": "python:3.11-slim",
    "node": "node:20-slim",
    "bazel-python": "python:3.11-slim",
    "bazel-java": "eclipse-temurin:21-jdk",
}


def resolve_template_image(template: str) -> str:
    """Return default image for a template key.

    Falls back to treating the template value as a raw image name if it's
    not in the registry, so users can also pass image names directly.
    """
    return TEMPLATE_IMAGES.get(template, template)


def _template_root() -> Path:
    return Path(__file__).resolve().parents[2] / "templates"


def _template_dockerfile(template: str) -> Path:
    return _template_root() / template / "Dockerfile"


def ensure_template_image(client: docker.DockerClient, template: str) -> str:
    """Build or pull image for a template and return the image tag."""
    dockerfile = _template_dockerfile(template)
    if dockerfile.exists():
        tag = f"devbox-template-{template}:latest"
        from devbox.utils.console import console
        console.print(f"[dim]Building local template image [cyan]{tag}[/cyan]...[/dim]")
        client.images.build(
            path=str(dockerfile.parent),
            tag=tag,
            rm=True,
        )
        return tag

    image = resolve_template_image(template)
    try:
        client.images.get(image)
    except docker.errors.ImageNotFound:
        from devbox.utils.console import console
        console.print(f"[dim]Pulling image [cyan]{image}[/cyan]...[/dim]")
        client.images.pull(image)
    return image


def list_devbox_containers() -> list[Container]:
    """Return all containers managed by devbox (has the devbox label)."""
    client = get_client()
    return client.containers.list(
        all=True,
        filters={"label": f"{DEVBOX_LABEL}={DEVBOX_LABEL_VALUE}"},
    )
