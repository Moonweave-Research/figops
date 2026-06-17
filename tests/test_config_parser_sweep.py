"""Unit tests for parse_sweep_config(), _validate_sweep(), and targeted config validation."""

import unittest

from hub_core.config_parser import _validate_sweep, parse_sweep_config, validate_config


class TestParseSweepConfigValues(unittest.TestCase):

    def test_values_mode_produces_correct_run_count(self):
        sweep = {"enabled": True, "parameter": "lr", "values": [0.01, 0.001, 0.0001]}
        result = parse_sweep_config(sweep)
        self.assertEqual(len(result["runs"]), 3)

    def test_values_mode_each_run_contains_parameter_key(self):
        sweep = {"enabled": True, "parameter": "lr", "values": [0.01, 0.001, 0.0001]}
        result = parse_sweep_config(sweep)
        for run in result["runs"]:
            self.assertIn("lr", run)

    def test_values_mode_values_are_stringified(self):
        sweep = {"enabled": True, "parameter": "lr", "values": [0.01, 0.001, 0.0001]}
        result = parse_sweep_config(sweep)
        expected = [{"lr": "0.01"}, {"lr": "0.001"}, {"lr": "0.0001"}]
        self.assertEqual(result["runs"], expected)

    def test_values_mode_string_values_preserved(self):
        sweep = {"enabled": True, "parameter": "mode", "values": ["fast", "slow", "medium"]}
        result = parse_sweep_config(sweep)
        self.assertEqual(result["runs"], [{"mode": "fast"}, {"mode": "slow"}, {"mode": "medium"}])


class TestParseSweepConfigGrid(unittest.TestCase):

    def test_grid_mode_cartesian_product_count(self):
        sweep = {
            "enabled": True,
            "grid": {
                "lr": [0.1, 0.01, 0.001],
                "batch_size": [16, 32, 64],
            },
        }
        result = parse_sweep_config(sweep)
        self.assertEqual(len(result["runs"]), 9)

    def test_grid_mode_two_params_three_values_each(self):
        sweep = {
            "enabled": True,
            "grid": {
                "alpha": ["a1", "a2", "a3"],
                "beta": ["b1", "b2"],
            },
        }
        result = parse_sweep_config(sweep)
        self.assertEqual(len(result["runs"]), 6)

    def test_grid_mode_runs_contain_all_param_keys(self):
        sweep = {
            "enabled": True,
            "grid": {
                "alpha": ["a1", "a2", "a3"],
                "beta": ["b1", "b2", "b3"],
            },
        }
        result = parse_sweep_config(sweep)
        for run in result["runs"]:
            self.assertIn("alpha", run)
            self.assertIn("beta", run)

    def test_grid_mode_values_are_stringified(self):
        sweep = {
            "enabled": True,
            "grid": {
                "x": [1, 2],
                "y": [10, 20],
            },
        }
        result = parse_sweep_config(sweep)
        for run in result["runs"]:
            for val in run.values():
                self.assertIsInstance(val, str)


class TestValidateSweepMutualExclusion(unittest.TestCase):

    def test_values_and_grid_together_returns_error(self):
        sweep = {
            "enabled": True,
            "parameter": "lr",
            "values": [0.1, 0.01],
            "grid": {"lr": [0.1, 0.01]},
        }
        errors = _validate_sweep(sweep)
        self.assertTrue(
            any("values" in e and "grid" in e for e in errors),
            f"Expected mutual exclusion error, got: {errors}",
        )

    def test_values_and_grid_error_message_content(self):
        sweep = {
            "enabled": True,
            "parameter": "lr",
            "values": [0.1],
            "grid": {"lr": [0.1]},
        }
        errors = _validate_sweep(sweep)
        combined = " ".join(errors)
        self.assertIn("values", combined)
        self.assertIn("grid", combined)


class TestValidateSweepMissingParameter(unittest.TestCase):

    def test_values_without_parameter_returns_error(self):
        sweep = {"enabled": True, "values": [0.1, 0.01, 0.001]}
        errors = _validate_sweep(sweep)
        self.assertTrue(
            any("parameter" in e for e in errors),
            f"Expected parameter error, got: {errors}",
        )

    def test_values_with_empty_parameter_returns_error(self):
        sweep = {"enabled": True, "parameter": "   ", "values": [0.1]}
        errors = _validate_sweep(sweep)
        self.assertTrue(
            any("parameter" in e for e in errors),
            f"Expected parameter error for empty string, got: {errors}",
        )


class TestDataContractConfigValidation(unittest.TestCase):
    def test_reversed_range_bounds_are_rejected(self):
        config = {
            "project": {"name": "Bad Range"},
            "visual_style": {"target_format": "nature"},
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "results/data/summary.csv",
                        "semantic_checks": {"temperature": {"range": [5, 1]}},
                    }
                ]
            },
        }

        errors = validate_config(config)

        self.assertTrue(any("range" in error and "<=" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
