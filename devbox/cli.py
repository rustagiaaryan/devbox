"""Top-level CLI entry point for devbox."""

import click
from dotenv import load_dotenv

from devbox.workspace.commands import workspace
from devbox.build_analyzer.commands import build_analyzer
from devbox.ai_diagnose.commands import ai_diagnose


@click.group()
@click.version_option(package_name="devbox")
def cli() -> None:
    """devbox — developer toolbox for workspaces, build analysis, and AI diagnostics.

    A demonstration of Snowflake DevEx concepts: warm-pool workspace provisioning,
    Bazel build graph analysis, and AI-powered failure diagnosis.
    """
    # Load .env if present so subcommands can access ANTHROPIC_API_KEY etc.
    # Silently no-ops if .env does not exist.
    load_dotenv()


cli.add_command(workspace)
cli.add_command(build_analyzer)
cli.add_command(ai_diagnose)
