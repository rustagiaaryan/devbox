"""Shared Rich console instance and formatting helpers."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Single shared console instance used throughout devbox.
# All modules import from here to ensure consistent theme and output routing.
console = Console()


def not_implemented_panel(command_name: str) -> Panel:
    """Return a styled Rich Panel for unimplemented stub commands."""
    message = Text()
    message.append("Not yet implemented", style="bold yellow")
    message.append(" — coming soon", style="dim")
    return Panel(
        message,
        title=f"[bold cyan]{command_name}[/bold cyan]",
        subtitle="[dim]Phase 1 stub[/dim]",
        border_style="yellow",
        expand=False,
    )
