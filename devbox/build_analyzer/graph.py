"""Bazel build graph analysis using networkx.

Parses `bazel query` output into a directed acyclic graph (DAG) and
computes critical paths, bottleneck targets, and parallelism metrics.

Key concepts:
  - Critical path: the longest sequential dependency chain, which sets
    the minimum possible build time regardless of parallelism.
  - Bottleneck node: a target with high combined in-degree + out-degree,
    meaning many targets depend on it AND it depends on many targets.
  - Fan-in: targets that many others depend on (build blockers).
  - Fan-out: targets that depend on many others (late in the DAG).

Phase 2 implementation plan:
  - parse_bazel_query_output(output: str) -> nx.DiGraph
      Parses `bazel query --output=graph //...` proto/text output.
  - find_critical_path(graph: nx.DiGraph) -> list[str]
      Uses DAG longest-path algorithm (nx.dag_longest_path).
  - find_bottleneck_nodes(graph: nx.DiGraph, top_n: int) -> list[tuple[str, int]]
      Returns top_n nodes sorted by in_degree + out_degree descending.
  - compute_build_metrics(graph: nx.DiGraph) -> BuildMetrics
      Returns a dataclass: node_count, edge_count, critical_path_length,
      parallelism_factor, top_bottlenecks.
"""
