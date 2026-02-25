"""HTML visualization of Bazel build dependency graphs.

Generates self-contained interactive HTML reports embedding a JavaScript
graph library (vis.js Network). The report highlights:
  - Critical path nodes/edges in red
  - Bottleneck nodes in orange
  - Normal nodes in blue
  - Independent (parallelizable) subgraphs in distinct clusters

The output is a single .html file with no external dependencies,
making it easy to share or open offline.

Phase 2 implementation plan:
  - render_graph_html(
        graph: nx.DiGraph,
        metrics: BuildMetrics,
        output_path: Path,
        open_browser: bool = False,
    ) -> None
  - _build_nodes_json(graph, critical_path, bottlenecks) -> list[dict]
      Maps each node to a vis.js node object with color and label.
  - _build_edges_json(graph, critical_path) -> list[dict]
      Maps each edge to a vis.js edge object; critical path edges
      get a distinct color and increased width.
  - _render_template(nodes, edges, metrics) -> str
      Fills in an HTML template string with embedded vis.js CDN link
      and serialized JSON data. Returns the full HTML document.
"""
