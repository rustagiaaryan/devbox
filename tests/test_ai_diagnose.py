import tempfile
import unittest
from pathlib import Path

from devbox.ai_diagnose.analyzer import BuildFailureAnalyzer
from devbox.ai_diagnose.db import DiagnosisDB


class AnalyzerDryRunTests(unittest.TestCase):
    def test_dry_run_extracts_target_and_type(self) -> None:
        analyzer = BuildFailureAnalyzer(model="claude-opus-4-6")
        log = "ERROR: /repo/app/BUILD:10:11: Compiling failed for //app:cli due to missing header"
        result = analyzer.diagnose_dry_run(log)

        self.assertEqual(result.target, "//app:cli")
        self.assertEqual(result.failure_type, "compilation_error")
        self.assertGreater(len(result.suggested_fixes), 0)


class DiagnosisDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DiagnosisDB(Path(self.tmp.name) / "diagnoses.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_save_list_and_group_patterns(self) -> None:
        analyzer = BuildFailureAnalyzer(model="claude-opus-4-6")

        r1 = analyzer.diagnose_dry_run("ERROR failed target //app:cli; timed out")
        r2 = analyzer.diagnose_dry_run("ERROR failed target //app:cli; timed out")
        r3 = analyzer.diagnose_dry_run("ERROR loading package at //lib:core")

        self.db.save_diagnosis(r1)
        self.db.save_diagnosis(r2)
        self.db.save_diagnosis(r3)

        history = self.db.list_diagnoses(limit=10)
        self.assertEqual(len(history), 3)

        grouped_targets = dict(self.db.group_by_target(limit=10))
        self.assertEqual(grouped_targets.get("//app:cli"), 2)

        grouped_types = dict(self.db.group_by_failure_type())
        self.assertGreaterEqual(grouped_types.get("timeout", 0), 1)


if __name__ == "__main__":
    unittest.main()
