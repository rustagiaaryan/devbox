"""Click commands for the `devbox workspace` subcommand group."""

import sys
import uuid
from datetime import datetime, timezone

import click
from rich.table import Table
from rich.text import Text
from rich import box

from devbox.utils.console import console
from devbox.workspace.db import (
    DEFAULT_DB_PATH,
    STATE_RUNNING,
    STATE_POOL,
    STATE_ERROR,
    WorkspaceDB,
    WorkspaceRecord,
)
from devbox.workspace import docker_client as dc
from devbox.workspace.pool import PoolManager


def _get_db() -> WorkspaceDB:
    return WorkspaceDB(DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# workspace group
# ---------------------------------------------------------------------------

@click.group(name="workspace")
def workspace() -> None:
    """Manage isolated Docker-based development workspaces."""


# ---------------------------------------------------------------------------
# workspace create
# ---------------------------------------------------------------------------

@workspace.command(name="create")
@click.argument("name")
@click.option("--template", default="base", show_default=True, help="Workspace template (base, python, node)")
@click.option("--cpu", default=2, show_default=True, type=int, help="CPU count")
@click.option("--memory", default="4g", show_default=True, help="Memory limit (e.g. 4g, 512m)")
def workspace_create(name: str, template: str, cpu: int, memory: str) -> None:
    """Create a new workspace container named NAME.

    Checks the warm pool first for an instant claim. Falls back to
    cold-starting a new container if the pool is empty.
    """
    db = _get_db()

    # Guard: reject duplicate names
    if db.get_workspace(name):
        console.print(f"[bold red]Error:[/bold red] A workspace named '[cyan]{name}[/cyan]' already exists.")
        console.print("Use [bold]devbox workspace list[/bold] to see existing workspaces.")
        sys.exit(1)

    pool = PoolManager(db)

    # --- Fast path: claim from warm pool ---
    with console.status(f"[bold green]Checking warm pool...[/bold green]"):
        claimed = pool.acquire(name)

    if claimed:
        console.print(
            f"[bold green]✓[/bold green] Claimed warm container from pool "
            f"([cyan]{claimed.container_id[:12]}[/cyan])"
        )
        console.print(
            f"\n[bold]Workspace [cyan]{name}[/cyan] is ready![/bold] "
            f"(fast path — pool hit)\n"
        )
        _print_workspace_info(claimed)
        return

    # --- Slow path: cold-start a new container ---
    console.print("[dim]Pool is empty — cold-starting a new container...[/dim]")

    with console.status(f"[bold green]Creating workspace [cyan]{name}[/cyan]...[/bold green]"):
        try:
            container = dc.create_container(
                name=name,
                template=template,
                cpu=cpu,
                memory=memory,
            )
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] Failed to create container: {exc}")
            sys.exit(1)

        record = WorkspaceRecord(
            id=str(uuid.uuid4()),
            name=name,
            container_id=container.id,
            state=STATE_RUNNING,
            template=template,
            created_at=datetime.now(timezone.utc).isoformat(),
            pool_member=False,
            cpu=cpu,
            memory=memory,
        )
        db.insert_workspace(record)

    console.print(f"[bold green]✓[/bold green] Created container [cyan]{container.id[:12]}[/cyan]")
    console.print(f"\n[bold]Workspace [cyan]{name}[/cyan] is ready![/bold] (cold start)\n")
    _print_workspace_info(record)


# ---------------------------------------------------------------------------
# workspace list
# ---------------------------------------------------------------------------

@workspace.command(name="list")
def workspace_list() -> None:
    """List all workspaces with their status, template, and resource config."""
    db = _get_db()
    workspaces = db.list_workspaces(include_pool=False)

    if not workspaces:
        console.print("[dim]No workspaces found. Run [bold]devbox workspace create <name>[/bold] to get started.[/dim]")
        return

    table = Table(
        title="Workspaces",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Name", style="bold white", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Template", style="dim")
    table.add_column("CPU", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Container ID", style="dim", no_wrap=True)
    table.add_column("Created", style="dim")

    for ws in workspaces:
        status_text = _state_badge(ws.state)
        # Try to get live container status from Docker
        live_state = _get_live_state(ws.container_id)
        if live_state and live_state != ws.state:
            status_text = _state_badge(live_state)

        created_str = ws.created_at[:16].replace("T", " ")  # "2025-01-01 12:00"
        table.add_row(
            ws.name,
            status_text,
            ws.template,
            str(ws.cpu),
            ws.memory,
            ws.container_id[:12],
            created_str,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# workspace connect
# ---------------------------------------------------------------------------

@workspace.command(name="connect")
@click.argument("name")
def workspace_connect(name: str) -> None:
    """Open an interactive shell inside the workspace named NAME."""
    db = _get_db()
    ws = db.get_workspace(name)
    if not ws:
        console.print(f"[bold red]Error:[/bold red] No workspace named '[cyan]{name}[/cyan]'.")
        sys.exit(1)

    container = dc.get_container(ws.container_id)
    if not container:
        console.print(f"[bold red]Error:[/bold red] Container [cyan]{ws.container_id[:12]}[/cyan] not found in Docker.")
        console.print("It may have been removed outside of devbox. Run [bold]devbox workspace destroy[/bold] to clean up.")
        sys.exit(1)

    if container.status != "running":
        console.print(
            f"[bold red]Error:[/bold red] Workspace [cyan]{name}[/cyan] is not running "
            f"(state: [yellow]{container.status}[/yellow])."
        )
        sys.exit(1)

    console.print(f"[bold green]Connecting to workspace [cyan]{name}[/cyan]...[/bold green]")
    console.print("[dim]Type [bold]exit[/bold] to disconnect.[/dim]\n")
    dc.exec_into_container(ws.container_id)


# ---------------------------------------------------------------------------
# workspace destroy
# ---------------------------------------------------------------------------

@workspace.command(name="destroy")
@click.argument("name")
@click.option("--force", is_flag=True, default=False, help="Skip confirmation prompt")
def workspace_destroy(name: str, force: bool) -> None:
    """Tear down and remove the workspace named NAME."""
    db = _get_db()
    ws = db.get_workspace(name)
    if not ws:
        console.print(f"[bold red]Error:[/bold red] No workspace named '[cyan]{name}[/cyan]'.")
        sys.exit(1)

    if not force:
        click.confirm(
            f"Destroy workspace '{name}' ({ws.container_id[:12]})? This cannot be undone.",
            abort=True,
        )

    with console.status(f"[bold red]Destroying workspace [cyan]{name}[/cyan]...[/bold red]"):
        try:
            dc.stop_and_remove_container(ws.container_id, force=force)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] Failed to remove container: {exc}")
            sys.exit(1)
        db.delete_workspace(name)

    console.print(f"[bold green]✓[/bold green] Workspace [cyan]{name}[/cyan] destroyed.")


# ---------------------------------------------------------------------------
# pool subgroup
# ---------------------------------------------------------------------------

@click.group(name="pool")
def pool() -> None:
    """Manage the warm workspace pool."""


@pool.command(name="init")
@click.option("--size", default=3, show_default=True, type=int,
              help="Number of containers to pre-create in the warm pool")
@click.option("--template", default="base", show_default=True,
              help="Template to use for pool containers")
def pool_init(size: int, template: str) -> None:
    """Pre-create SIZE idle containers for instant workspace provisioning.

    Mirrors the warm pool strategy used in Snowflake's Cloud Workspaces,
    where containers are kept ready so `workspace create` returns in seconds.
    """
    db = _get_db()
    pool_mgr = PoolManager(db)

    console.print(
        f"[bold]Initializing warm pool[/bold]: [cyan]{size}[/cyan] container(s) "
        f"using template [cyan]{template}[/cyan]"
    )
    console.print()

    created = []
    for i in range(size):
        with console.status(f"[green]Creating pool container {i + 1}/{size}...[/green]"):
            try:
                records = pool_mgr.initialize(size=1, template=template)
                created.extend(records)
                r = records[0]
                console.print(
                    f"  [green]✓[/green] [dim]{r.name}[/dim] → [cyan]{r.container_id[:12]}[/cyan]"
                )
            except Exception as exc:
                console.print(f"  [red]✗[/red] Failed: {exc}")

    console.print()
    status = pool_mgr.status()
    console.print(
        f"[bold green]Pool ready.[/bold green] "
        f"{status.warm} warm container(s) available."
    )


@pool.command(name="status")
def pool_status() -> None:
    """Show warm pool health: warm containers ready, in-use, and total."""
    db = _get_db()
    pool_mgr = PoolManager(db)
    status = pool_mgr.status()

    table = Table(
        title="Warm Pool Status",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Metric", style="bold white")
    table.add_column("Count", justify="right")

    table.add_row("Warm (ready to claim)", _count_badge(status.warm, "green"))
    table.add_row("In use (claimed)", _count_badge(status.in_use, "yellow"))
    table.add_row("Total pool containers", _count_badge(status.total, "cyan"))

    console.print(table)

    # Show individual pool members
    members = db.list_pool_members()
    if members:
        console.print()
        mem_table = Table(
            title="Pool Containers",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
        )
        mem_table.add_column("Name", style="dim")
        mem_table.add_column("Container ID", style="dim")
        mem_table.add_column("Template", style="dim")
        mem_table.add_column("State", style="dim")

        for m in members:
            mem_table.add_row(
                m.name,
                m.container_id[:12],
                m.template,
                _state_badge(m.state),
            )
        console.print(mem_table)


# Register pool as a subgroup of workspace
workspace.add_command(pool)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_badge(state: str) -> str:
    """Return a Rich-formatted state string."""
    colors = {
        "running": "[bold green]● running[/bold green]",
        "pool":    "[bold blue]◌ warm[/bold blue]",
        "stopped": "[bold yellow]○ stopped[/bold yellow]",
        "error":   "[bold red]✗ error[/bold red]",
    }
    return colors.get(state, f"[dim]{state}[/dim]")


def _count_badge(count: int, color: str) -> str:
    return f"[bold {color}]{count}[/bold {color}]"


def _get_live_state(container_id: str) -> str | None:
    """Query Docker for the live container state. Returns None on failure."""
    try:
        container = dc.get_container(container_id)
        if container:
            return container.status  # 'running', 'exited', etc.
        return None
    except Exception:
        return None


def _print_workspace_info(ws: WorkspaceRecord) -> None:
    """Print a summary panel for a newly created workspace."""
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value", style="white")

    table.add_row("Container ID", ws.container_id[:12])
    table.add_row("Template", ws.template)
    table.add_row("CPU", str(ws.cpu))
    table.add_row("Memory", ws.memory)
    table.add_row("State", _state_badge(ws.state))

    console.print(table)
    console.print(
        f"\n[dim]Connect with:[/dim] [bold]devbox workspace connect {ws.name}[/bold]"
    )
