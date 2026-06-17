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
        self.assertIn("current=np.float64(9.0)", summary)

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
        with tempfile.TemporaryDirectory(prefix="graph_hub_golden_check_atol_") as tmpdir:
            project_dir = Path(tmpdir) / "project"
            data_dir = project_dir / "results" / "data"
            data_dir.mkdir(parents=True)

            csv_path = data_dir / "summary.csv"
            pd.DataFrame({"y": [1.0]}).to_csv(csv_path, index=False)
            config = {"golden_metrics": [{"path": "results/data/summary.csv", "atol": 0.01}]}
            freeze_golden_dataset(project_dir, config)

            pd.DataFrame({"y": [1.02]}).to_csv(csv_path, index=False)
            result = check_golden_regression(project_dir, config)

            self.assertFalse(result.success)
            self.assertIn("column='y'", result.failures[0].diff_summary)


if __name__ == "__main__":
    unittest.main()
