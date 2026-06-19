import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hub_core.logging import configure_logging
from hub_core.utils import scan_csv_export_anomalies


class TestInputExportAnomalies(unittest.TestCase):
    def test_detects_duplicate_and_blank_headers(self):
        with tempfile.TemporaryDirectory(prefix="input_anomaly_") as tmpdir:
            root = Path(tmpdir)
            csv_path = root / "bad.csv"
            csv_path.write_text(
                "Time(sec),ThetaTotal(deg),,ThetaTotal(deg)\n0,1,,2\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                configure_logging("INFO")
                warnings = scan_csv_export_anomalies(str(root), ["bad.csv"])

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["path"], "bad.csv")
        self.assertEqual(warnings[0]["blank_headers"], 1)
        self.assertEqual(warnings[0]["duplicate_headers"], ["ThetaTotal(deg)"])
        self.assertEqual("", stdout.getvalue())
        self.assertIn("[Input Export Anomaly]", stderr.getvalue())

    def test_ignores_clean_csv_and_non_csv_inputs(self):
        with tempfile.TemporaryDirectory(prefix="input_clean_") as tmpdir:
            root = Path(tmpdir)
            (root / "good.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            (root / "note.txt").write_text("hello\n", encoding="utf-8")

            warnings = scan_csv_export_anomalies(str(root), ["good.csv", "note.txt"])

        self.assertEqual(warnings, [])
