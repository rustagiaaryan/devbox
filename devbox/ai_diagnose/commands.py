"""Click commands for the `devbox ai-diagnose` subcommand group."""

import sys

import click
from rich import box
from rich.panel import Panel
from rich.table import Table

from devbox.ai_diagnose.analyzer import BuildFailureAnalyzer, DiagnosisResult
from devbox.ai_diagnose.db import DiagnosisDB
from devbox.utils.console import console


@click.group(name="ai-diagnose")
def ai_diagnose() -> None:
    """AI-powered diagnostics: pipe build output to Claude for root-cause analysis."""


@ai_diagnose.command(name="diagnose")
@click.argument("input_file", type=click.File("r"), default="-", required=False)
@click.option(
    "--model",
    default="claude-opus-4-6",
    show_default=True,
    help="Anthropic model ID to use for diagnosis",
)
@click.option(
    "--context",
    "-c",
    default=None,
    help="Optional context string appended to the prompt (e.g. 'running on macOS ARM')",
)
@click.option(
    "--save/--no-save",
    default=True,
    show_default=True,
    help="Persist the diagnosis result to local SQLite history",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print a mock diagnosis without calling the Anthropic API (useful for demos)",
)
@click.option(
    "--history",
    is_flag=True,
    default=False,
    help="Show past diagnosis history instead of running a new diagnosis",
)
@click.option(
    "--patterns",
    is_flag=True,
    default=False,
    help="Show recurring issues grouped by failure type and target",
)
def ai_diagnose_diagnose(
    input_file: click.File,
    model: str,
    context: str | None,
    save: bool,
    dry_run: bool,
    history: bool,
    patterns: bool,
) -> None:
    """Diagnose build/test failures using Claude.

    Reads from INPUT_FILE, or from stdin if no file is given.
    Sends the log to Claude, which classifies the failure, identifies
    the root cause, and suggests fixes.

    Examples:

    \b
        # Pipe build output directly
        bazel build //... 2>&1 | devbox ai-diagnose diagnose

    \b
        # Read from a saved log file
        devbox ai-diagnose diagnose build.log

    \b
        # Demo mode — no API call
        devbox ai-diagnose diagnose --dry-run

    \b
        # Review past diagnoses
        devbox ai-diagnose diagnose --history

    \b
        # Surface recurring failure patterns
        devbox ai-diagnose diagnose --patterns
    """
    if history and patterns:
        raise click.ClickException("Use either --history or --patterns, not both together.")

    db = DiagnosisDB()
    try:
        if history:
            _print_history(db)
            return

        if patterns:
            _print_patterns(db)
            return

        input_text = input_file.read()
        if not input_text.strip() and not dry_run:
            if input_file.name == "<stdin>" and sys.stdin.isatty():
                raise click.ClickException(
                    "No input detected. Pipe build output or pass a log file path."
                )
            raise click.ClickException("Input log is empty.")

        analyzer = BuildFailureAnalyzer(model=model)
        with console.status("[bold green]Analyzing failure log...[/bold green]"):
            try:
                if dry_run:
                    result = analyzer.diagnose_dry_run(input_text, context=context)
                else:
                    result = analyzer.diagnose(input_text, context=context)
            except Exception as exc:
                raise click.ClickException(str(exc)) from exc

        _print_result(result, dry_run=dry_run)

        if save:
            diagnosis_id = db.save_diagnosis(result)
            console.print(f"[bold green]✓[/bold green] Saved diagnosis: [cyan]{diagnosis_id}[/cyan]")
    finally:
        db.close()


def _print_result(result: DiagnosisResult, dry_run: bool) -> None:
    title = "Diagnosis (dry run)" if dry_run else "Diagnosis"
    body = (
        f"[bold]Target:[/bold] {result.target or '(unknown)'}\n"
        f"[bold]Failure type:[/bold] {result.failure_type}\n"
        f"[bold]Model:[/bold] {result.model}\n\n"
        f"[bold]Summary:[/bold]\n{result.summary}\n\n"
        f"[bold]Root cause:[/bold]\n{result.root_cause}"
    )
    console.print(
        Panel(
            body,
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
            expand=False,
        )
    )

    fixes = Table(
        title="Suggested Fixes",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold green",
    )
    fixes.add_column("#", justify="right")
    fixes.add_column("Action")
    for idx, fix in enumerate(result.suggested_fixes, start=1):
        fixes.add_row(str(idx), fix)
    console.print(fixes)


def _print_history(db: DiagnosisDB) -> None:
    records = db.list_diagnoses(limit=30)
    if not records:
        console.print("[dim]No diagnosis history found.[/dim]")
        return

    table = Table(
        title="Diagnosis History",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Timestamp", style="dim")
    table.add_column("Target")
    table.add_column("Failure Type")
    table.add_column("Summary")
    table.add_column("Model", style="dim")

    for row in records:
        table.add_row(
            row.timestamp[:19].replace("T", " "),
            row.target or "(unknown)",
            row.failure_type,
            row.summary,
            row.model,
        )
    console.print(table)


def _print_patterns(db: DiagnosisDB) -> None:
    by_type = db.group_by_failure_type()
    by_target = db.group_by_target(limit=10)

    if not by_type and not by_target:
        console.print("[dim]No diagnosis history found.[/dim]")
        return

    type_table = Table(
        title="Failure Patterns by Type",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    type_table.add_column("Failure Type")
    type_table.add_column("Count", justify="right")
    for failure_type, count in by_type:
        type_table.add_row(failure_type, str(count))
    console.print(type_table)

    target_table = Table(
        title="Failure Patterns by Target",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold yellow",
    )
    target_table.add_column("Target")
    target_table.add_column("Count", justify="right")
    for target, count in by_target:
        target_table.add_row(target, str(count))
    console.print(target_table)
