"""Click commands for the `devbox workspace` subcommand group."""

import click

from devbox.utils.console import console, not_implemented_panel


@click.group(name="workspace")
def workspace() -> None:
    """Manage isolated Docker-based development workspaces."""


@workspace.command(name="create")
@click.argument("name")
@click.option("--template", default="base", show_default=True, help="Workspace template name (see templates/)")
@click.option("--cpu", default=2, show_default=True, type=int, help="CPU count")
@click.option("--memory", default="4g", show_default=True, help="Memory limit (e.g. 4g)")
def workspace_create(name: str, template: str, cpu: int, memory: str) -> None:
    """Create a new workspace container named NAME.

    Checks the warm pool first. If a pre-warmed container is available,
    it is claimed immediately (fast path). Otherwise a new container is
    cold-started from the specified template.
    """
    console.print(not_implemented_panel("workspace create"))


@workspace.command(name="list")
def workspace_list() -> None:
    """List all existing workspaces with status, uptime, and resource usage."""
    console.print(not_implemented_panel("workspace list"))


@workspace.command(name="connect")
@click.argument("name")
def workspace_connect(name: str) -> None:
    """Open an interactive shell inside the workspace named NAME."""
    console.print(not_implemented_panel("workspace connect"))


@workspace.command(name="destroy")
@click.argument("name")
@click.option("--force", is_flag=True, default=False, help="Skip confirmation prompt")
def workspace_destroy(name: str, force: bool) -> None:
    """Tear down and remove the workspace named NAME."""
    console.print(not_implemented_panel("workspace destroy"))


# ---------------------------------------------------------------------------
# Nested `pool` subgroup
# Pool commands are nested under `workspace pool` (e.g. `devbox workspace pool init`).
# We define `pool` as its own Click group and register it on `workspace` below.
# ---------------------------------------------------------------------------

@click.group(name="pool")
def pool() -> None:
    """Manage the warm workspace pool."""


@pool.command(name="init")
@click.option(
    "--size",
    default=3,
    show_default=True,
    type=int,
    help="Number of containers to pre-create in the warm pool",
)
@click.option("--template", default="base", show_default=True, help="Workspace template to use for pool containers")
def pool_init(size: int, template: str) -> None:
    """Pre-create SIZE idle containers for instant workspace provisioning.

    Mirrors the warm pool strategy in Snowflake's Cloud Workspaces,
    where containers are kept ready so `create` can return in seconds.
    """
    console.print(not_implemented_panel("workspace pool init"))


@pool.command(name="status")
def pool_status() -> None:
    """Show warm pool health: total capacity, warm containers, and in-use count."""
    console.print(not_implemented_panel("workspace pool status"))


# Register `pool` as a subgroup of `workspace`
workspace.add_command(pool)
