import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from hub_core.data_regression import _build_diff_summary, check_golden_regression, freeze_golden_dataset


class GoldenRegressionTest(unittest.TestCase):
    def test_freeze_and_detect_drift(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            data_dir.mkdir(parents=True)

            csv_path = data_dir / "summary.csv"
            pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}).to_csv(csv_path, index=False)

            config = {"golden_metrics": [{"path": "results/data/summary.csv", "atol": 1e-6}]}
            frozen = freeze_golden_dataset(project_dir, config)
            self.assertTrue(frozen.success)
            self.assertTrue((data_dir / "golden" / "summary.csv").exists())

            matched = check_golden_regression(project_dir, config)
            self.assertTrue(matched.success)
            self.assertEqual(matched.failures, [])

            pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.01]}).to_csv(csv_path, index=False)
            drifted = check_golden_regression(project_dir, config)
            self.assertFalse(drifted.success)
            self.assertIn("Scientific drift detected", drifted.failures[0].reason)
            self.assertIn("column='y'", drifted.failures[0].diff_summary)

    def test_freeze_writes_manifest(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_manifest_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "summary.csv").write_text("a,b\n1,2\n", encoding="utf-8")

            result = freeze_golden_dataset(project_dir, {})
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))

            self.assertEqual(manifest["count"], 1)
            self.assertEqual(manifest["files"][0]["path"], "summary.csv")

    def test_parquet_diff_summary_uses_index_labels_safely(self):
        current_path = Path("/tmp/current.parquet")
        golden_path = Path("/tmp/golden.parquet")

        current = pd.DataFrame({"y": [1.0, 2.0, 9.0]}, index=[10, 20, 30])
        golden = pd.DataFrame({"y": [1.0, 2.0, 3.0]}, index=[10, 20, 30])

        def fake_load_table(path):
            if path == current_path:
                return current
            if path == golden_path:
                return golden
            raise AssertionError(f"Unexpected path: {path}")

        with patch("hub_core.data_regression._load_table", side_effect=fake_load_table):
            summary = _build_diff_summary(current_path, golden_path, "drift", atol=1e-6)

        self.assertIn("row=30", summary)
        self.assertIn("current=", summary)
        self.assertIn("9.0", summary)

    def test_diff_summary_respects_per_spec_atol_for_numeric_columns(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_atol_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            golden_dir = data_dir / "golden"
            data_dir.mkdir(parents=True)
            golden_dir.mkdir(parents=True)

            current_path = data_dir / "summary.csv"
            golden_path = golden_dir / "summary.csv"
            pd.DataFrame({"y": [1.0005]}).to_csv(current_path, index=False)
            pd.DataFrame({"y": [1.0]}).to_csv(golden_path, index=False)

            summary = _build_diff_summary(current_path, golden_path, "drift", atol=0.01)

            self.assertEqual(summary, "drift")

    def test_check_golden_regression_uses_per_spec_atol_for_summary(self):
        # Witnesses the per-spec atol path at the check_golden_regression level by
        # straddling the spec atol (0.01) boundary:
        #   - drift 0.0005 (> DEFAULT_ATOL 1e-6, < spec atol) must be suppressed;
        #   - drift 0.02 (> spec atol) must fail AND surface the drifting column in
        #     the diff summary. The pre-fix code used DEFAULT_ATOL for the summary
        #     regardless of spec; with spec atol > DEFAULT_ATOL the summary still
        #     reports the column, but this asserts the per-spec atol value is what
        #     flows through to the summary rather than the global default.
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_check_atol_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            data_dir.mkdir(parents=True)

            csv_path = data_dir / "summary.csv"
            pd.DataFrame({"y": [1.0]}).to_csv(csv_path, index=False)
            config = {"golden_metrics": [{"path": "results/data/summary.csv", "atol": 0.01}]}
            freeze_golden_dataset(project_dir, config)

            # Within spec atol: suppressed.
            pd.DataFrame({"y": [1.0005]}).to_csv(csv_path, index=False)
            result = check_golden_regression(project_dir, config)
            self.assertTrue(result.success, result.failures)
            self.assertEqual(result.failures, [])

            # Above spec atol: fails and the per-spec-atol summary names column 'y'.
            pd.DataFrame({"y": [1.02]}).to_csv(csv_path, index=False)
            failing = check_golden_regression(project_dir, config)
            self.assertFalse(failing.success)
            self.assertIn("column='y'", failing.failures[0].diff_summary)

    def test_tampered_golden_file_fails_integrity_check(self):
        # Scope: guards the golden_hash.json integrity path, not the atol /
        # index-label fixes in this branch. Coverage for pre-existing behavior.
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_integrity_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            data_dir.mkdir(parents=True)

            csv_path = data_dir / "summary.csv"
            pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}).to_csv(csv_path, index=False)

            config = {"golden_metrics": [{"path": "results/data/summary.csv", "atol": 1e-6}]}
            freeze_golden_dataset(project_dir, config)

            # Tampered golden parses to the SAME values as the current CSV (a plain
            # drift comparison would spuriously pass), but its bytes — and thus its
            # hash — differ from the one recorded at freeze time. This isolates the
            # integrity check from ordinary drift detection.
            golden_file = data_dir / "golden" / "summary.csv"
            frozen_bytes = golden_file.read_bytes()
            golden_csv = pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}).to_csv(index=False)
            # Append an extra blank line: pandas skips it on parse (values stay
            # identical, so drift detection alone would pass), but it always adds
            # bytes regardless of pandas' trailing-newline behavior — guaranteeing
            # a different hash from the frozen file.
            golden_file.write_text(golden_csv + "\n\n", encoding="utf-8")
            self.assertNotEqual(golden_file.read_bytes(), frozen_bytes)

            result = check_golden_regression(project_dir, config)
            self.assertFalse(result.success)
            self.assertIn("integrity check failed", result.failures[0].reason)
            self.assertIn("summary.csv", result.failures[0].reason)

    def test_large_magnitude_value_within_rtol_passes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_rtol_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            data_dir.mkdir(parents=True)

            csv_path = data_dir / "summary.csv"
            pd.DataFrame({"y": [1.0e9]}).to_csv(csv_path, index=False)

            config = {"golden_metrics": [{"path": "results/data/summary.csv", "atol": 1e-6, "rtol": 1e-5}]}
            freeze_golden_dataset(project_dir, config)

            # Drift of 100 on 1e9 is within rtol (1e-5 * 1e9 = 1e4) but far above atol (1e-6).
            pd.DataFrame({"y": [1.0e9 + 100.0]}).to_csv(csv_path, index=False)
            result = check_golden_regression(project_dir, config)
            self.assertTrue(result.success, result.failures)


if __name__ == "__main__":
    unittest.main()
