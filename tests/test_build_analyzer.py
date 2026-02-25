import tempfile
import unittest
from pathlib import Path

from devbox.build_analyzer.graph import (
    build_query_expression,
    compute_build_metrics,
    parse_bazel_query_output,
)
from devbox.build_analyzer.visualizer import render_graph_html


SAMPLE_DOT = """
digraph deps {
  node [shape=box];
  "//app:cli";
  "//lib:rpc";
  "//lib:http";
  "//lib:core";
  "//lib:utils";
  "//app:cli" -> "//lib:rpc";
  "//lib:rpc" -> "//lib:http";
  "//lib:rpc" -> "//lib:core";
  "//lib:http" -> "//lib:utils";
  "//lib:core" -> "//lib:utils";
}
"""


class BuildAnalyzerGraphTests(unittest.TestCase):
    def test_build_query_expression(self) -> None:
        self.assertEqual(build_query_expression("//...", 0), "deps(//...)")
        self.assertEqual(build_query_expression("//app:cli", 2), "deps(//app:cli, 2)")

    def test_parse_and_compute_metrics(self) -> None:
        graph = parse_bazel_query_output(SAMPLE_DOT)
        metrics = compute_build_metrics(graph)

        self.assertEqual(graph.number_of_nodes(), 5)
        self.assertEqual(graph.number_of_edges(), 5)
        self.assertGreaterEqual(metrics.critical_path_length, 3)
        self.assertGreater(len(metrics.top_bottlenecks), 0)
        self.assertIn("//lib:rpc", [item.target for item in metrics.top_bottlenecks])


class BuildAnalyzerVisualizerTests(unittest.TestCase):
    def test_render_graph_html(self) -> None:
        graph = parse_bazel_query_output(SAMPLE_DOT)
        metrics = compute_build_metrics(graph)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.html"
            saved = render_graph_html(graph, metrics, output, open_browser=False)
            self.assertEqual(saved, output)
            html = output.read_text(encoding="utf-8")
            self.assertIn("Build Analyzer Report", html)
            self.assertIn("Critical Path", html)
            self.assertIn("//app:cli", html)


if __name__ == "__main__":
    unittest.main()
