import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hub_core.data_regression import check_golden_regression, freeze_golden_dataset


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


if __name__ == "__main__":
    unittest.main()
