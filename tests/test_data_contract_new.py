"""Unit tests for _read_data_safe in hub_core.data_contract."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from hub_core.data_contract import _read_data_safe, validate_data_contract_preflight


class TestReadDataSafe(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1. .csv -> DataFrame via _read_csv_safe path
    # ------------------------------------------------------------------
    def test_csv_returns_dataframe(self):
        with tempfile.TemporaryDirectory(prefix="rds_csv_") as tmpdir:
            csv_file = Path(tmpdir) / "data.csv"
            csv_file.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
            df = _read_data_safe(str(csv_file), pd)

        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ["x", "y"])
        self.assertEqual(len(df), 2)

    def test_tsv_uses_tab_separator(self):
        with tempfile.TemporaryDirectory(prefix="rds_tsv_") as tmpdir:
            tsv_file = Path(tmpdir) / "data.tsv"
            tsv_file.write_text("x\ty\n1\t2\n3\t4\n", encoding="utf-8")
            df = _read_data_safe(str(tsv_file), pd)

        self.assertEqual(list(df.columns), ["x", "y"])
        self.assertEqual(df.iloc[0]["x"], 1)
        self.assertEqual(df.iloc[1]["y"], 4)

    def test_txt_uses_inferred_separator(self):
        with tempfile.TemporaryDirectory(prefix="rds_txt_") as tmpdir:
            txt_file = Path(tmpdir) / "data.txt"
            txt_file.write_text("x\ty\n1\t2\n3\t4\n", encoding="utf-8")
            df = _read_data_safe(str(txt_file), pd)

        self.assertEqual(list(df.columns), ["x", "y"])
        self.assertEqual(df.iloc[0]["x"], 1)
        self.assertEqual(df.iloc[1]["y"], 4)

    # ------------------------------------------------------------------
    # 2. .parquet without pyarrow -> ImportError with helpful message
    # ------------------------------------------------------------------
    def test_parquet_without_pyarrow_raises_import_error(self):
        with tempfile.TemporaryDirectory(prefix="rds_parquet_") as tmpdir:
            parquet_file = Path(tmpdir) / "data.parquet"
            parquet_file.write_bytes(b"")  # content irrelevant; import check fires first

            with patch.dict(sys.modules, {"pyarrow": None}):
                with self.assertRaises(ImportError) as ctx:
                    _read_data_safe(str(parquet_file), pd)

        self.assertIn("pyarrow", str(ctx.exception).lower())

    # ------------------------------------------------------------------
    # 3. Unknown extension .dat -> ValueError
    # ------------------------------------------------------------------
    def test_unknown_extension_raises_value_error(self):
        with tempfile.TemporaryDirectory(prefix="rds_dat_") as tmpdir:
            dat_file = Path(tmpdir) / "data.dat"
            dat_file.write_text("1 2 3\n", encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                _read_data_safe(str(dat_file), pd)

        self.assertIn(".dat", str(ctx.exception))

    def test_preflight_rejects_unsupported_extension(self):
        with tempfile.TemporaryDirectory(prefix="dcp_dat_") as tmpdir:
            config = {
                "data_contract": {
                    "csv_checks": [
                        {"path": "results/data/output.dat"},
                    ]
                }
            }

            result = validate_data_contract_preflight(tmpdir, config)

        self.assertFalse(result)

    def test_preflight_rejects_missing_optional_dependency(self):
        with tempfile.TemporaryDirectory(prefix="dcp_parquet_") as tmpdir:
            config = {
                "data_contract": {
                    "csv_checks": [
                        {"path": "results/data/output.parquet"},
                    ]
                }
            }

            with patch("hub_core.data_contract._module_available", return_value=False):
                result = validate_data_contract_preflight(tmpdir, config)

        self.assertFalse(result)

    def test_preflight_plot_mode_requires_existing_file(self):
        with tempfile.TemporaryDirectory(prefix="dcp_csv_") as tmpdir:
            config = {
                "data_contract": {
                    "csv_checks": [
                        {"path": "results/data/output.csv"},
                    ]
                }
            }

            result = validate_data_contract_preflight(tmpdir, config, require_existing=True)

        self.assertFalse(result)

    # ------------------------------------------------------------------
    # 4. .hdf5 with missing key -> fallback to first available key
    # ------------------------------------------------------------------
    def test_hdf5_missing_key_falls_back_to_first_key(self):
        fallback_df = pd.DataFrame({"a": [1, 2, 3]})

        mock_h5py_file = MagicMock()
        mock_h5py_file.__enter__ = lambda s: s
        mock_h5py_file.__exit__ = MagicMock(return_value=False)
        mock_h5py_file.keys.return_value = iter(["first_key"])

        mock_h5py = MagicMock()
        mock_h5py.File.return_value = mock_h5py_file

        mock_tables = MagicMock()

        read_hdf_calls: list[tuple] = []

        def fake_read_hdf(path, key):
            read_hdf_calls.append((path, key))
            if key == "/data":
                raise KeyError("/data")
            return fallback_df

        with (
            patch.dict(sys.modules, {"h5py": mock_h5py, "tables": mock_tables}),
            patch.object(pd, "read_hdf", side_effect=fake_read_hdf),
        ):
            with tempfile.TemporaryDirectory(prefix="rds_hdf_") as tmpdir:
                hdf_file = Path(tmpdir) / "data.hdf5"
                hdf_file.write_bytes(b"")

                result = _read_data_safe(str(hdf_file), pd, hdf_key="/data")

        self.assertEqual(len(read_hdf_calls), 2)
        self.assertEqual(read_hdf_calls[1][1], "first_key")
        self.assertIs(result, fallback_df)


if __name__ == "__main__":
    unittest.main()
