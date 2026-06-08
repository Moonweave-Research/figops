"""Unit tests for _read_data_safe in hub_core.data_contract."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from hub_core.config_parser import validate_config
from hub_core.data_contract import _read_data_safe, validate_data_contract, validate_data_contract_preflight


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


class TestSemanticMonotonicContract(unittest.TestCase):
    def test_validate_config_accepts_declared_monotonic_mode(self):
        config = {
            "project": {"name": "Monotonic Demo"},
            "visual_style": {"target_format": "nature"},
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "results/data/summary.csv",
                        "semantic_checks": {"time": {"monotonic": "increasing"}},
                    }
                ]
            },
        }

        self.assertEqual(validate_config(config), [])

    def test_validate_config_rejects_unknown_monotonic_mode(self):
        config = {
            "project": {"name": "Monotonic Demo"},
            "visual_style": {"target_format": "nature"},
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "results/data/summary.csv",
                        "semantic_checks": {"time": {"monotonic": "zigzag"}},
                    }
                ]
            },
        }

        errors = validate_config(config)

        self.assertTrue(any("monotonic" in error and "zigzag" in error for error in errors))

    def test_data_contract_passes_monotonic_increasing_series(self):
        with tempfile.TemporaryDirectory(prefix="dcp_mono_pass_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("time,value\n0,10\n1,20\n2,30\n", encoding="utf-8")
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["time", "value"],
                            "semantic_checks": {"time": {"monotonic": "increasing"}},
                        }
                    ]
                }
            }

            self.assertTrue(validate_data_contract(tmpdir, config))

    def test_data_contract_fails_monotonic_increasing_violation(self):
        with tempfile.TemporaryDirectory(prefix="dcp_mono_fail_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("time,value\n0,10\n2,20\n1,30\n", encoding="utf-8")
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["time", "value"],
                            "semantic_checks": {"time": {"monotonic": "increasing"}},
                        }
                    ]
                }
            }

            self.assertFalse(validate_data_contract(tmpdir, config))


class TestGroupedCalculationChecks(unittest.TestCase):
    def test_validate_config_accepts_grouped_calculation_checks(self):
        config = {
            "project": {"name": "Grouped Demo"},
            "visual_style": {"target_format": "nature"},
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "results/data/summary.csv",
                        "semantic_checks": {
                            "value": {
                                "min_replicates": {"group_by": ["condition"], "min_count": 3},
                                "grouped_cv": {"group_by": ["condition"], "threshold": 0.15},
                            }
                        },
                    }
                ]
            },
        }

        self.assertEqual(validate_config(config), [])

    def test_validate_config_rejects_malformed_grouped_calculation_checks(self):
        config = {
            "project": {"name": "Grouped Demo"},
            "visual_style": {"target_format": "nature"},
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "results/data/summary.csv",
                        "semantic_checks": {
                            "value": {
                                "min_replicates": {"group_by": [], "min_count": 0},
                                "grouped_cv": {
                                    "group_by": ["condition", 123],
                                    "threshold": -0.1,
                                    "warn_only": "yes",
                                },
                            }
                        },
                    }
                ]
            },
        }

        errors = validate_config(config)

        self.assertTrue(any("min_replicates.group_by" in error for error in errors))
        self.assertTrue(any("min_replicates.min_count" in error for error in errors))
        self.assertTrue(any("grouped_cv.group_by" in error for error in errors))
        self.assertTrue(any("grouped_cv.threshold" in error for error in errors))
        self.assertTrue(any("grouped_cv.warn_only" in error for error in errors))

    def test_min_replicates_counts_valid_target_observations_not_raw_rows(self):
        with tempfile.TemporaryDirectory(prefix="dcp_min_reps_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text(
                "condition,value\nA,1.0\nA,\nA,3.0\nB,1.0\nB,2.0\nB,3.0\n",
                encoding="utf-8",
            )
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {"min_replicates": {"group_by": ["condition"], "min_count": 3}}
                            },
                        }
                    ]
                }
            }

            self.assertFalse(validate_data_contract(tmpdir, config))

    def test_grouped_cv_warn_only_writes_aggregate_calculation_sidecar(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_cv_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text(
                "condition,value\nA,10\nA,10\nB,1\nB,100\n",
                encoding="utf-8",
            )
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                            },
                        }
                    ]
                }
            }

            self.assertTrue(validate_data_contract(tmpdir, config))
            sidecar = Path(tmpdir) / "results" / "diagnostics" / "calculation_checks.json"
            payload = json.loads(sidecar.read_text(encoding="utf-8"))

            self.assertFalse(payload["quality_passed"])
            self.assertTrue(payload["manual_review_needed"])
            grouped = next(check for check in payload["checks"] if check["name"] == "grouped_cv")
            self.assertEqual(grouped["status"], "warning")
            self.assertTrue(grouped["manual_review_needed"])
            self.assertEqual(grouped["csv_path"], "results/data/summary.csv")

    def test_grouped_cv_warn_only_false_fails_contract(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_cv_fail_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text(
                "condition,value\nB,1\nB,100\n",
                encoding="utf-8",
            )
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {
                                    "grouped_cv": {
                                        "group_by": ["condition"],
                                        "threshold": 0.15,
                                        "warn_only": False,
                                    }
                                }
                            },
                        }
                    ]
                }
            }

            self.assertFalse(validate_data_contract(tmpdir, config))

    def test_grouped_checks_runtime_malformed_config_returns_false_without_crashing(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_malformed_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("condition,value\nA,1\nA,2\n", encoding="utf-8")
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {
                                    "min_replicates": {"group_by": [], "min_count": 3},
                                    "grouped_cv": {"group_by": [], "threshold": 0.15},
                                }
                            },
                        }
                    ]
                }
            }

            self.assertFalse(validate_data_contract(tmpdir, config))

    def test_grouped_check_sidecar_is_removed_on_early_contract_failure(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_early_failure_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("condition,value\nB,1\nB,100\n", encoding="utf-8")
            warning_config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                            },
                        }
                    ]
                }
            }
            missing_column_config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["missing"],
                        }
                    ]
                }
            }

            self.assertTrue(validate_data_contract(tmpdir, warning_config))
            sidecar = Path(tmpdir) / "results" / "diagnostics" / "calculation_checks.json"
            self.assertTrue(sidecar.exists())
            self.assertFalse(validate_data_contract(tmpdir, missing_column_config))
            self.assertFalse(sidecar.exists())

    def test_grouped_check_sidecar_replaces_stale_warning_when_no_grouped_checks_run(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_stale_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("condition,value\nB,1\nB,100\n", encoding="utf-8")
            warning_config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                            },
                        }
                    ]
                }
            }
            plain_config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                        }
                    ]
                }
            }

            self.assertTrue(validate_data_contract(tmpdir, warning_config))
            sidecar = Path(tmpdir) / "results" / "diagnostics" / "calculation_checks.json"
            self.assertTrue(sidecar.exists())
            self.assertTrue(validate_data_contract(tmpdir, plain_config))
            self.assertFalse(sidecar.exists())

    def test_grouped_check_serializes_scalar_and_null_group_keys(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_null_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("condition,value\nA,1\nA,100\n,1\n,100\n", encoding="utf-8")
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition", "value"],
                            "semantic_checks": {
                                "value": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                            },
                        }
                    ]
                }
            }

            self.assertTrue(validate_data_contract(tmpdir, config))
            sidecar = Path(tmpdir) / "results" / "diagnostics" / "calculation_checks.json"
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            groups = [violation["group"] for violation in payload["checks"][0]["violations"]]

            self.assertIn({"condition": "A"}, groups)
            self.assertIn({"condition": None}, groups)

    def test_semantic_check_missing_target_column_fails_runtime_validation(self):
        with tempfile.TemporaryDirectory(prefix="dcp_grouped_missing_target_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("condition,other\nA,1\nA,2\n", encoding="utf-8")
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["condition"],
                            "semantic_checks": {
                                "value": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                            },
                        }
                    ]
                }
            }

            self.assertFalse(validate_data_contract(tmpdir, config))

    def test_data_contract_enforces_monotonic_modes_at_equal_value_boundary(self):
        cases = (
            ("increasing", "0,10\n1,20\n1,30\n", False),
            ("decreasing", "2,10\n1,20\n1,30\n", False),
            ("nondecreasing", "0,10\n1,20\n1,30\n", True),
            ("nonincreasing", "2,10\n1,20\n1,30\n", True),
        )
        for mode, rows, expected in cases:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="dcp_mono_modes_") as tmpdir:
                data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
                data_path.parent.mkdir(parents=True)
                data_path.write_text(f"time,value\n{rows}", encoding="utf-8")
                config = {
                    "data_contract": {
                        "csv_checks": [
                            {
                                "path": "results/data/summary.csv",
                                "required_columns": ["time", "value"],
                                "semantic_checks": {"time": {"monotonic": mode}},
                            }
                        ]
                    }
                }

                self.assertEqual(validate_data_contract(tmpdir, config), expected)

    def test_data_contract_rejects_runtime_invalid_monotonic_mode(self):
        with tempfile.TemporaryDirectory(prefix="dcp_mono_invalid_") as tmpdir:
            data_path = Path(tmpdir) / "results" / "data" / "summary.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("time,value\n0,10\n1,20\n2,30\n", encoding="utf-8")
            config = {
                "data_contract": {
                    "csv_checks": [
                        {
                            "path": "results/data/summary.csv",
                            "required_columns": ["time", "value"],
                            "semantic_checks": {"time": {"monotonic": ""}},
                        }
                    ]
                }
            }

            self.assertFalse(validate_data_contract(tmpdir, config))


if __name__ == "__main__":
    unittest.main()
