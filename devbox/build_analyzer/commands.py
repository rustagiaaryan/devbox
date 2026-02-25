"""Click commands for the `devbox build-analyzer` subcommand group."""

import click

from devbox.utils.console import console, not_implemented_panel


@click.group(name="build-analyzer")
def build_analyzer() -> None:
    """Analyze Bazel build graphs to find critical paths and bottlenecks."""


@build_analyzer.command(name="analyze")
@click.argument("target", default="//...", required=False)
@click.option(
    "--output",
    "-o",
    default="build-report.html",
    show_default=True,
    help="Path for the generated HTML visualization report",
)
@click.option(
    "--depth",
    default=0,
    type=int,
    show_default=True,
    help="Max dependency depth to traverse (0 = unlimited)",
)
@click.option(
    "--visualize",
    is_flag=True,
    default=False,
    help="Generate an interactive HTML dependency graph report",
)
@click.option(
    "--open",
    "open_browser",
    is_flag=True,
    default=False,
    help="Auto-open the HTML report in the default browser after generation",
)
def build_analyzer_analyze(
    target: str,
    output: str,
    depth: int,
    visualize: bool,
    open_browser: bool,
) -> None:
    """Analyze the Bazel dependency graph for TARGET.

    Runs `bazel query` to extract the full build graph, parses it into
    a DAG, computes the critical path (the longest sequential chain that
    determines minimum build time), and identifies bottleneck targets.

    TARGET defaults to //... (all targets in the workspace).

    Examples:

        devbox build-analyzer analyze

        devbox build-analyzer analyze //my/package/...

        devbox build-analyzer analyze --visualize --open
    """
    console.print(not_implemented_panel("build-analyzer analyze"))
