"""Click commands for the `devbox ai-diagnose` subcommand group."""

import click

from devbox.utils.console import console, not_implemented_panel


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
    help="Group past diagnoses by failure type to surface recurring issues",
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
    """Diagnose build/test failures using Claude AI.

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
    console.print(not_implemented_panel("ai-diagnose diagnose"))
