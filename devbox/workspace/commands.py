"""Click commands for the `devbox workspace` subcommand group."""

import sys
import uuid
from datetime import datetime, timezone

import click
from rich.table import Table
from rich import box

from devbox.utils.console import console
from devbox.workspace.db import (
    DEFAULT_DB_PATH,
    STATE_RUNNING,
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
@click.option(
    "--template",
    default="base",
    show_default=True,
    help="Workspace template (base, python, node, bazel-python, bazel-java)",
)
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
        claimed = pool.acquire(name, template=template)

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
    """List all workspaces with status, uptime, and resource usage."""
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
    table.add_column("Uptime", justify="right")
    table.add_column("CPU", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("Usage", justify="right")
    table.add_column("Container ID", style="dim", no_wrap=True)
    table.add_column("Created", style="dim")

    for ws in workspaces:
        live = _get_live_details(ws.container_id)
        status_text = _state_badge(live.get("state", ws.state))
        uptime = _format_uptime(live.get("uptime_seconds"))

        stats = live.get("stats", {})
        usage = "n/a"
        cpu_display = str(ws.cpu)
        mem_display = ws.memory
        if stats:
            cpu_display = f"{stats.get('cpu_pct', 0):.1f}%"
            mem_pct = stats.get("mem_pct", 0.0)
            usage = f"{stats.get('mem_usage_mb', 0):.1f}/{stats.get('mem_limit_mb', 0):.1f} MiB ({mem_pct:.1f}%)"

        created_str = ws.created_at[:16].replace("T", " ")  # "2025-01-01 12:00"
        table.add_row(
            ws.name,
            status_text,
            ws.template,
            uptime,
            cpu_display,
            mem_display,
            usage,
            ws.container_id[:12],
            created_str,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# workspace connect
# ---------------------------------------------------------------------------

@workspace.command(name="connect")
@click.argument("identifier")
def workspace_connect(identifier: str) -> None:
    """Open an interactive shell inside the workspace."""
    db = _get_db()
    ws = _resolve_workspace_identifier(db, identifier)
    if not ws:
        console.print(
            f"[bold red]Error:[/bold red] No workspace matched '[cyan]{identifier}[/cyan]'. "
            "Use a workspace name, UUID, or container ID prefix."
        )
        sys.exit(1)

    container = dc.get_container(ws.container_id)
    if not container:
        console.print(f"[bold red]Error:[/bold red] Container [cyan]{ws.container_id[:12]}[/cyan] not found in Docker.")
        console.print("It may have been removed outside of devbox. Run [bold]devbox workspace destroy[/bold] to clean up.")
        sys.exit(1)

    if container.status != "running":
        console.print(
            f"[bold red]Error:[/bold red] Workspace [cyan]{ws.name}[/cyan] is not running "
            f"(state: [yellow]{container.status}[/yellow])."
        )
        sys.exit(1)

    console.print(f"[bold green]Connecting to workspace [cyan]{ws.name}[/cyan]...[/bold green]")
    console.print("[dim]Type [bold]exit[/bold] to disconnect.[/dim]\n")
    dc.exec_into_container(ws.container_id)


# ---------------------------------------------------------------------------
# workspace destroy
# ---------------------------------------------------------------------------

@workspace.command(name="destroy")
@click.argument("identifier")
@click.option("--force", is_flag=True, default=False, help="Skip confirmation prompt")
def workspace_destroy(identifier: str, force: bool) -> None:
    """Tear down and remove a workspace."""
    db = _get_db()
    ws = _resolve_workspace_identifier(db, identifier)
    if not ws:
        console.print(
            f"[bold red]Error:[/bold red] No workspace matched '[cyan]{identifier}[/cyan]'. "
            "Use a workspace name, UUID, or container ID prefix."
        )
        sys.exit(1)

    if not force:
        click.confirm(
            f"Destroy workspace '{ws.name}' ({ws.container_id[:12]})? This cannot be undone.",
            abort=True,
        )

    with console.status(f"[bold red]Destroying workspace [cyan]{ws.name}[/cyan]...[/bold red]"):
        try:
            dc.stop_and_remove_container(ws.container_id, force=force)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] Failed to remove container: {exc}")
            sys.exit(1)
        db.delete_workspace(ws.name)

    console.print(f"[bold green]✓[/bold green] Workspace [cyan]{ws.name}[/cyan] destroyed.")


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

    Keeps containers pre-created so `workspace create` returns quickly.
    """
    db = _get_db()
    pool_mgr = PoolManager(db)

    console.print(
        f"[bold]Initializing warm pool[/bold]: [cyan]{size}[/cyan] container(s) "
        f"using template [cyan]{template}[/cyan]"
    )
    console.print()

    with console.status("[green]Preparing warm pool...[/green]"):
        try:
            created = pool_mgr.initialize(size=size, template=template)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] Failed to initialize pool: {exc}")
            sys.exit(1)

    for record in created:
        console.print(
            f"  [green]✓[/green] [dim]{record.name}[/dim] → [cyan]{record.container_id[:12]}[/cyan]"
        )

    console.print()
    status = pool_mgr.status()
    console.print(
        f"[bold green]Pool ready.[/bold green] {status.warm} warm container(s) available "
        f"(target: {status.target}, template: {status.template})."
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
    table.add_row("Target size", _count_badge(status.target, "magenta"))
    table.add_row("Template", f"[bold white]{status.template}[/bold white]")

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


def _get_live_details(container_id: str) -> dict:
    """Return best-effort container state, uptime, and stats."""
    try:
        details = dc.get_container_runtime(container_id)
        stats = dc.get_container_stats(container_id)
        details["stats"] = stats
        return details
    except Exception:
        return {}


def _resolve_workspace_identifier(db: WorkspaceDB, identifier: str) -> WorkspaceRecord | None:
    """Resolve by workspace name, UUID, or container ID prefix."""
    by_name = db.get_workspace(identifier)
    if by_name and not by_name.pool_member:
        return by_name

    by_id = db.get_workspace_by_id(identifier)
    if by_id and not by_id.pool_member:
        return by_id

    all_workspaces = db.list_workspaces(include_pool=False)
    matched = [ws for ws in all_workspaces if ws.container_id.startswith(identifier)]
    if len(matched) == 1:
        return matched[0]
    return None


def _format_uptime(seconds: int | None) -> str:
    if seconds is None:
        return "n/a"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


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
