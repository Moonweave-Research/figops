"""Unit tests for _check_statistical_quality() in hub_core.data_contract."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from hub_core.data_contract import _check_statistical_quality
from hub_core.runtime_paths import resolve_diagnostics_dir


class TestCheckStatisticalQuality(unittest.TestCase):
    """Tests for the CV-based statistical quality checker."""

    def setUp(self):
        self._runtime_tmp = tempfile.TemporaryDirectory(prefix="quality_runtime_")
        self._runtime_root = Path(self._runtime_tmp.name)
        self._runtime_env = patch.dict(
            os.environ,
            {"RESEARCH_HUB_RUNTIME_ROOT": str(self._runtime_root)},
            clear=False,
        )
        self._runtime_env.start()

    def tearDown(self):
        self._runtime_env.stop()
        self._runtime_tmp.cleanup()

    # ------------------------------------------------------------------
    # 1. Low CV -> quality_passed=True, no warnings
    # ------------------------------------------------------------------
    def test_quality_passes_low_cv(self):
        """DataFrame whose numeric columns all have CV below threshold."""
        df = pd.DataFrame({
            "voltage": [1.00, 1.01, 0.99, 1.00, 1.01],
            "current": [5.00, 5.01, 4.99, 5.00, 5.02],
        })
        with tempfile.TemporaryDirectory(prefix="quality_low_cv_") as tmpdir:
            result = _check_statistical_quality(df, "data.csv", 0.10, tmpdir)

        self.assertTrue(result["quality_passed"])
        self.assertEqual(result["cv_warnings"], [])
        self.assertIsNone(result["report_path"])

    # ------------------------------------------------------------------
    # 2. High CV -> quality_passed=False, cv_warnings populated
    # ------------------------------------------------------------------
    def test_quality_warns_high_cv(self):
        """One column with high CV triggers a warning."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "stable": [10.0, 10.1, 9.9, 10.0, 10.05],
            "noisy": rng.normal(loc=10.0, scale=5.0, size=5).tolist(),
        })
        with tempfile.TemporaryDirectory(prefix="quality_high_cv_") as tmpdir:
            result = _check_statistical_quality(df, "noisy.csv", 0.05, tmpdir)

        self.assertFalse(result["quality_passed"])
        warned_cols = [w["column"] for w in result["cv_warnings"]]
        self.assertIn("noisy", warned_cols)
        # Each warning must carry a numeric cv value
        for w in result["cv_warnings"]:
            self.assertIn("cv", w)
            self.assertIsInstance(w["cv"], float)

    # ------------------------------------------------------------------
    # 3. Sidecar JSON written when warnings exist
    # ------------------------------------------------------------------
    def test_quality_sidecar_written(self):
        """quality_metrics.json is created under external runtime diagnostics."""
        rng = np.random.default_rng(0)
        df = pd.DataFrame({
            "wild": rng.normal(loc=1.0, scale=5.0, size=20).tolist(),
        })
        with tempfile.TemporaryDirectory(prefix="quality_sidecar_") as tmpdir:
            result = _check_statistical_quality(df, "wild.csv", 0.05, tmpdir)

            sidecar = Path(resolve_diagnostics_dir(tmpdir)) / "data_contract" / "quality_metrics.json"
            self.assertTrue(sidecar.exists(), "quality_metrics.json not created")
            self.assertTrue(sidecar.is_relative_to(self._runtime_root))
            self.assertFalse((Path(tmpdir) / "results" / "diagnostics" / "quality_metrics.json").exists())

            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            for key in ("timestamp", "csv_path", "cv_warnings", "cv_threshold", "quality_passed"):
                self.assertIn(key, payload)
            self.assertFalse(payload["quality_passed"])
            self.assertEqual(payload["csv_path"], "wild.csv")

            # report_path in result should also be set
            self.assertIsNotNone(result["report_path"])

    # ------------------------------------------------------------------
    # 4. Column with mean ~ 0 (division risk) -> skipped gracefully
    # ------------------------------------------------------------------
    def test_quality_zero_mean_column(self):
        """A column with mean effectively zero should be skipped, not crash."""
        df = pd.DataFrame({
            "centered": [-1.0, 1.0, -1.0, 1.0, -1.0, 1.0],
            "offset":   [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        })
        with tempfile.TemporaryDirectory(prefix="quality_zero_") as tmpdir:
            result = _check_statistical_quality(df, "zero.csv", 0.10, tmpdir)

        # Neither column should appear in warnings:
        # "centered" has mean 0 -> skipped; "offset" has std 0 -> CV=0.
        warned_cols = [w["column"] for w in result["cv_warnings"]]
        self.assertNotIn("centered", warned_cols)
        self.assertNotIn("offset", warned_cols)
        self.assertTrue(result["quality_passed"])

    # ------------------------------------------------------------------
    # 5. Single-row DataFrame -> no crash
    # ------------------------------------------------------------------
    def test_quality_single_row(self):
        """A single-row DataFrame should not crash (< 2 values -> skip)."""
        df = pd.DataFrame({"x": [42.0], "y": [100.0]})
        with tempfile.TemporaryDirectory(prefix="quality_single_") as tmpdir:
            result = _check_statistical_quality(df, "single.csv", 0.10, tmpdir)

        self.assertTrue(result["quality_passed"])
        self.assertEqual(result["cv_warnings"], [])

    # ------------------------------------------------------------------
    # 6. All-NaN numeric column -> handled gracefully
    # ------------------------------------------------------------------
    def test_quality_all_nan(self):
        """A column of all NaN should be skipped (dropna -> len < 2)."""
        df = pd.DataFrame({
            "empty": [float("nan")] * 5,
            "good":  [3.0, 3.01, 2.99, 3.0, 3.02],
        })
        with tempfile.TemporaryDirectory(prefix="quality_nan_") as tmpdir:
            result = _check_statistical_quality(df, "nan.csv", 0.10, tmpdir)

        warned_cols = [w["column"] for w in result["cv_warnings"]]
        self.assertNotIn("empty", warned_cols)
        self.assertTrue(result["quality_passed"])


if __name__ == "__main__":
    unittest.main()
