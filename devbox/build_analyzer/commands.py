"""Click commands for the `devbox build-analyzer` subcommand group."""

from pathlib import Path

import click
from rich.table import Table
from rich import box

from devbox.build_analyzer.graph import (
    compute_build_metrics,
    parse_bazel_query_output,
    run_bazel_query,
)
from devbox.build_analyzer.visualizer import render_graph_html
from devbox.utils.console import console


@click.group(name="build-analyzer")
def build_analyzer() -> None:
    """Analyze Bazel build graphs to find critical paths and bottlenecks."""


@build_analyzer.command(name="analyze")
@click.argument("target", default="//...", required=False)
@click.option(
    "--project-path",
    "-p",
    default=".",
    show_default=True,
    help="Path to Bazel workspace root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
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
    project_path: Path,
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
    with console.status("[bold green]Running bazel query...[/bold green]"):
        try:
            query_output = run_bazel_query(project_path=project_path, target=target, depth=depth)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
        except FileNotFoundError as exc:
            raise click.ClickException("Bazel not found in PATH. Install Bazel and try again.") from exc

    graph = parse_bazel_query_output(query_output)
    metrics = compute_build_metrics(graph)

    summary = Table(
        title="Build Graph Summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    summary.add_column("Metric", style="bold white")
    summary.add_column("Value")
    summary.add_row("Project path", str(project_path.resolve()))
    summary.add_row("Target expression", target)
    summary.add_row("Node count", str(metrics.node_count))
    summary.add_row("Edge count", str(metrics.edge_count))
    summary.add_row("Critical path length", str(metrics.critical_path_length))
    summary.add_row("Parallelism factor", f"{metrics.parallelism_factor}x")
    summary.add_row("Root targets", str(metrics.root_targets))
    summary.add_row("Leaf targets", str(metrics.leaf_targets))
    console.print(summary)

    cp_table = Table(
        title="Critical Path",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold red",
    )
    cp_table.add_column("#", justify="right")
    cp_table.add_column("Target")
    for idx, node in enumerate(metrics.critical_path, start=1):
        cp_table.add_row(str(idx), node)
    console.print(cp_table)

    bottlenecks_table = Table(
        title="Top Bottlenecks",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold yellow",
    )
    bottlenecks_table.add_column("Target")
    bottlenecks_table.add_column("Score", justify="right")
    bottlenecks_table.add_column("In", justify="right")
    bottlenecks_table.add_column("Out", justify="right")
    for node in metrics.top_bottlenecks:
        bottlenecks_table.add_row(
            node.target,
            str(node.score),
            str(node.in_degree),
            str(node.out_degree),
        )
    console.print(bottlenecks_table)

    if visualize:
        with console.status("[bold green]Generating HTML report...[/bold green]"):
            report_path = render_graph_html(
                graph=graph,
                metrics=metrics,
                output_path=Path(output),
                open_browser=open_browser,
            )
        console.print(f"[bold green]✓[/bold green] Report saved to [cyan]{report_path.resolve()}[/cyan]")
