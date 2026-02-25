"""Bazel build graph analysis primitives."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import networkx as nx


EDGE_PATTERN = re.compile(r'^\s*"([^"]+)"\s*->\s*"([^"]+)"')
NODE_PATTERN = re.compile(r'^\s*"([^"]+)"(?:\s*\[.*\])?\s*;?\s*$')


@dataclass
class BottleneckNode:
    """A target with high centrality in the dependency graph."""

    target: str
    score: int
    in_degree: int
    out_degree: int


@dataclass
class BuildMetrics:
    """Computed summary of a Bazel dependency graph."""

    node_count: int
    edge_count: int
    critical_path: list[str]
    critical_path_length: int
    top_bottlenecks: list[BottleneckNode]
    parallelism_factor: float
    root_targets: int
    leaf_targets: int


def build_query_expression(target: str, depth: int) -> str:
    """Build a bazel query expression for `deps(...)` traversal."""
    if depth > 0:
        return f"deps({target}, {depth})"
    return f"deps({target})"


def run_bazel_query(project_path: Path, target: str = "//...", depth: int = 0) -> str:
    """Execute `bazel query --output=graph` and return DOT output."""
    query = build_query_expression(target, depth)
    cmd = ["bazel", "query", query, "--output", "graph"]
    proc = subprocess.run(
        cmd,
        cwd=str(project_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or "bazel query failed"
        raise RuntimeError(stderr)
    return proc.stdout


def parse_bazel_query_output(output: str) -> nx.DiGraph:
    """Parse Bazel DOT graph output from `--output graph` into a DiGraph."""
    graph = nx.DiGraph()
    for line in output.splitlines():
        edge_match = EDGE_PATTERN.match(line)
        if edge_match:
            source, target = edge_match.groups()
            graph.add_edge(source, target)
            continue

        node_match = NODE_PATTERN.match(line)
        if not node_match:
            continue
        node = node_match.group(1)
        if node in {"node", "edge"}:
            continue
        graph.add_node(node)
    return graph


def find_critical_path(graph: nx.DiGraph) -> list[str]:
    """Return the longest dependency chain in the DAG."""
    if graph.number_of_nodes() == 0:
        return []
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Dependency graph contains a cycle; expected a DAG.")
    return nx.dag_longest_path(graph)


def find_bottleneck_nodes(graph: nx.DiGraph, top_n: int = 5) -> list[BottleneckNode]:
    """Return targets with highest combined in-degree and out-degree."""
    scored: list[BottleneckNode] = []
    for node in graph.nodes:
        in_degree = graph.in_degree(node)
        out_degree = graph.out_degree(node)
        score = in_degree + out_degree
        scored.append(
            BottleneckNode(
                target=node,
                score=score,
                in_degree=in_degree,
                out_degree=out_degree,
            )
        )
    scored.sort(key=lambda item: (item.score, item.in_degree, item.out_degree), reverse=True)
    return scored[:top_n]


def compute_build_metrics(graph: nx.DiGraph, bottleneck_count: int = 5) -> BuildMetrics:
    """Compute critical path and high-level graph metrics."""
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    critical_path = find_critical_path(graph)
    critical_path_length = len(critical_path)
    top_bottlenecks = find_bottleneck_nodes(graph, top_n=bottleneck_count)
    parallelism_factor = round(
        (node_count / max(critical_path_length, 1)) if node_count else 0.0,
        2,
    )
    root_targets = sum(1 for n in graph.nodes if graph.in_degree(n) == 0)
    leaf_targets = sum(1 for n in graph.nodes if graph.out_degree(n) == 0)
    return BuildMetrics(
        node_count=node_count,
        edge_count=edge_count,
        critical_path=critical_path,
        critical_path_length=critical_path_length,
        top_bottlenecks=top_bottlenecks,
        parallelism_factor=parallelism_factor,
        root_targets=root_targets,
        leaf_targets=leaf_targets,
    )
