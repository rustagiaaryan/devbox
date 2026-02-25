"""Self-contained HTML report for build graph visualization."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path

import networkx as nx

from devbox.build_analyzer.graph import BuildMetrics


def _compute_levels(graph: nx.DiGraph) -> dict[str, int]:
    """Assign a horizontal layer to each node."""
    if graph.number_of_nodes() == 0:
        return {}
    if not nx.is_directed_acyclic_graph(graph):
        return {node: idx for idx, node in enumerate(graph.nodes)}

    levels: dict[str, int] = {}
    for node in nx.topological_sort(graph):
        parents = list(graph.predecessors(node))
        if not parents:
            levels[node] = 0
        else:
            levels[node] = 1 + max(levels[parent] for parent in parents)
    return levels


def _build_nodes_data(
    graph: nx.DiGraph,
    critical_path: list[str],
    bottlenecks: set[str],
) -> list[dict]:
    """Build node payload with static x/y coordinates and styles."""
    levels = _compute_levels(graph)
    if not levels:
        return []

    by_level: dict[int, list[str]] = {}
    for node, level in levels.items():
        by_level.setdefault(level, []).append(node)

    level_width = 280
    row_height = 100
    nodes: list[dict] = []
    for level in sorted(by_level.keys()):
        lane = sorted(by_level[level])
        for idx, node in enumerate(lane):
            x = 120 + level * level_width
            y = 100 + idx * row_height
            color = "#3b82f6"
            border = "#1e3a8a"
            if node in bottlenecks:
                color = "#f59e0b"
                border = "#92400e"
            if node in critical_path:
                color = "#ef4444"
                border = "#7f1d1d"
            nodes.append(
                {
                    "id": node,
                    "label": node,
                    "x": x,
                    "y": y,
                    "color": color,
                    "border": border,
                }
            )
    return nodes


def _build_edges_data(graph: nx.DiGraph, critical_path: list[str]) -> list[dict]:
    """Build edge payload and style critical-path edges."""
    critical_edges = {
        (critical_path[idx], critical_path[idx + 1])
        for idx in range(max(0, len(critical_path) - 1))
    }
    edges: list[dict] = []
    for source, target in graph.edges():
        is_critical = (source, target) in critical_edges
        edges.append(
            {
                "source": source,
                "target": target,
                "color": "#ef4444" if is_critical else "#94a3b8",
                "width": 3 if is_critical else 1.4,
            }
        )
    return edges


def _render_template(nodes: list[dict], edges: list[dict], metrics: BuildMetrics) -> str:
    """Render standalone HTML with inline CSS/JS."""
    metrics_json = {
        "node_count": metrics.node_count,
        "edge_count": metrics.edge_count,
        "critical_path_length": metrics.critical_path_length,
        "parallelism_factor": metrics.parallelism_factor,
        "root_targets": metrics.root_targets,
        "leaf_targets": metrics.leaf_targets,
        "critical_path": metrics.critical_path,
        "bottlenecks": [
            {
                "target": node.target,
                "score": node.score,
                "in_degree": node.in_degree,
                "out_degree": node.out_degree,
            }
            for node in metrics.top_bottlenecks
        ],
    }

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>devbox Build Graph Report</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --ink: #0f172a;
      --line: #cbd5e1;
      --accent: #0ea5e9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top right, #e2e8f0, var(--bg));
      color: var(--ink);
      font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 14px;
      min-height: 100vh;
      padding: 14px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
    }}
    .title {{
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: 0.2px;
    }}
    .stat {{
      display: flex;
      justify-content: space-between;
      margin: 6px 0;
      font-size: 14px;
    }}
    .stat strong {{
      color: var(--accent);
    }}
    .list {{
      margin: 8px 0 0;
      padding-left: 16px;
      font-size: 13px;
      line-height: 1.4;
    }}
    .graph-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      position: relative;
      min-height: 72vh;
    }}
    .legend {{
      position: absolute;
      right: 10px;
      top: 10px;
      background: rgba(255, 255, 255, 0.94);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 12px;
    }}
    .chip {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-right: 6px;
      vertical-align: middle;
    }}
    #graph {{
      width: 100%;
      height: 100%;
      min-height: 72vh;
      background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
      cursor: grab;
    }}
    #graph.dragging {{ cursor: grabbing; }}
    .node-label {{
      font-size: 12px;
      fill: #0f172a;
      pointer-events: none;
    }}
    @media (max-width: 980px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .graph-wrap {{
        min-height: 60vh;
      }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="panel">
      <h1 class="title">Build Analyzer Report</h1>
      <div class="stat"><span>Targets</span><strong id="targets"></strong></div>
      <div class="stat"><span>Edges</span><strong id="edges"></strong></div>
      <div class="stat"><span>Critical Path</span><strong id="critical-len"></strong></div>
      <div class="stat"><span>Parallelism</span><strong id="parallelism"></strong></div>
      <div class="stat"><span>Root Targets</span><strong id="roots"></strong></div>
      <div class="stat"><span>Leaf Targets</span><strong id="leaves"></strong></div>
      <h3 class="title" style="font-size:15px;margin-top:18px;">Critical Path</h3>
      <ol class="list" id="critical-path"></ol>
      <h3 class="title" style="font-size:15px;margin-top:18px;">Top Bottlenecks</h3>
      <ol class="list" id="bottlenecks"></ol>
    </aside>
    <main class="graph-wrap">
      <div class="legend">
        <div><span class="chip" style="background:#ef4444;"></span>Critical path</div>
        <div><span class="chip" style="background:#f59e0b;"></span>Bottleneck</div>
        <div><span class="chip" style="background:#3b82f6;"></span>Other target</div>
      </div>
      <svg id="graph">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto">
            <polygon points="0 0, 8 3.5, 0 7" fill="#94a3b8"></polygon>
          </marker>
        </defs>
        <g id="viewport"></g>
      </svg>
    </main>
  </div>
  <script>
    const nodes = {json.dumps(nodes)};
    const edges = {json.dumps(edges)};
    const metrics = {json.dumps(metrics_json)};

    document.getElementById("targets").textContent = metrics.node_count;
    document.getElementById("edges").textContent = metrics.edge_count;
    document.getElementById("critical-len").textContent = metrics.critical_path_length;
    document.getElementById("parallelism").textContent = `${{metrics.parallelism_factor}}x`;
    document.getElementById("roots").textContent = metrics.root_targets;
    document.getElementById("leaves").textContent = metrics.leaf_targets;

    const criticalList = document.getElementById("critical-path");
    metrics.critical_path.forEach((target) => {{
      const li = document.createElement("li");
      li.textContent = target;
      criticalList.appendChild(li);
    }});

    const bottleneckList = document.getElementById("bottlenecks");
    metrics.bottlenecks.forEach((item) => {{
      const li = document.createElement("li");
      li.textContent = `${{item.target}} (score=${{item.score}}, in=${{item.in_degree}}, out=${{item.out_degree}})`;
      bottleneckList.appendChild(li);
    }});

    const svg = document.getElementById("graph");
    const viewport = document.getElementById("viewport");
    const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));

    const maxX = Math.max(140, ...nodes.map((n) => n.x)) + 340;
    const maxY = Math.max(160, ...nodes.map((n) => n.y)) + 220;
    svg.setAttribute("viewBox", `0 0 ${{maxX}} ${{maxY}}`);

    edges.forEach((edge) => {{
      const source = nodeById[edge.source];
      const target = nodeById[edge.target];
      if (!source || !target) return;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", source.x + 92);
      line.setAttribute("y1", source.y + 12);
      line.setAttribute("x2", target.x - 6);
      line.setAttribute("y2", target.y + 12);
      line.setAttribute("stroke", edge.color);
      line.setAttribute("stroke-width", edge.width);
      line.setAttribute("marker-end", "url(#arrow)");
      line.setAttribute("opacity", "0.85");
      viewport.appendChild(line);
    }});

    nodes.forEach((node) => {{
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", node.x);
      rect.setAttribute("y", node.y);
      rect.setAttribute("rx", "10");
      rect.setAttribute("width", "170");
      rect.setAttribute("height", "24");
      rect.setAttribute("fill", node.color);
      rect.setAttribute("stroke", node.border);
      rect.setAttribute("stroke-width", "1.4");
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", node.x + 8);
      label.setAttribute("y", node.y + 16);
      label.setAttribute("class", "node-label");
      label.textContent = node.label;
      group.appendChild(rect);
      group.appendChild(label);
      viewport.appendChild(group);
    }});

    let scale = 1;
    let panX = 0;
    let panY = 0;
    let dragging = false;
    let dragStart = null;

    const applyTransform = () => {{
      viewport.setAttribute("transform", `translate(${{panX}}, ${{panY}}) scale(${{scale}})`);
    }};

    svg.addEventListener("wheel", (event) => {{
      event.preventDefault();
      const delta = event.deltaY < 0 ? 1.08 : 0.92;
      scale = Math.min(3, Math.max(0.35, scale * delta));
      applyTransform();
    }});

    svg.addEventListener("mousedown", (event) => {{
      dragging = true;
      dragStart = {{ x: event.clientX, y: event.clientY }};
      svg.classList.add("dragging");
    }});

    window.addEventListener("mousemove", (event) => {{
      if (!dragging || !dragStart) return;
      panX += (event.clientX - dragStart.x);
      panY += (event.clientY - dragStart.y);
      dragStart = {{ x: event.clientX, y: event.clientY }};
      applyTransform();
    }});

    window.addEventListener("mouseup", () => {{
      dragging = false;
      dragStart = null;
      svg.classList.remove("dragging");
    }});
  </script>
</body>
</html>"""


def render_graph_html(
    graph: nx.DiGraph,
    metrics: BuildMetrics,
    output_path: Path,
    open_browser: bool = False,
) -> Path:
    """Write an interactive HTML report and optionally open it."""
    critical_set = set(metrics.critical_path)
    bottlenecks = {node.target for node in metrics.top_bottlenecks}
    nodes = _build_nodes_data(graph, metrics.critical_path, bottlenecks)
    edges = _build_edges_data(graph, metrics.critical_path)
    html = _render_template(nodes, edges, metrics)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(output_path.resolve().as_uri())
    return output_path
