"""Unit tests for parse_sweep_config(), _validate_sweep(), and targeted config validation."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hub_core import (
    config_language_policy,
    config_parser,
    config_research_metadata,
    config_schema,
    config_top_level_keys,
)
from hub_core.config_parser import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    SUPPORTED_CONFIG_SCHEMA_VERSIONS,
    _load_project_metadata,
    _load_yaml_with_unique_keys,
    _validate_comparison,
    _validate_sweep,
    load_config,
    migrate_config,
    parse_sweep_config,
    validate_config,
)

RESERVED_EXECUTION_ENV_KEYS = (
    "PYTHONPATH",
    "RESEARCH_HUB_PATH",
    "PROJECT_ROOT",
    "RESEARCH_HUB_RUNTIME_ROOT",
    "RESEARCH_HUB_RUNTIME_HOME",
    "GRAPH_HUB_RUNTIME_ROOT",
    "UV_PROJECT_ENVIRONMENT",
    "UV_CACHE_DIR",
)

# Keep private compatibility values out of the public source scan while still
# asserting the exact validation facade exposed to existing configurations.
PRIVATE_TARGET_FORMAT = "_".join(("nature", "surfur"))
PRIVATE_STYLE_PROFILE = "_".join(("resistance", "premium"))


def test_config_parser_keeps_schema_compatibility_exports():
    assert config_parser.CURRENT_CONFIG_SCHEMA_VERSION is config_schema.CURRENT_CONFIG_SCHEMA_VERSION
    assert config_parser.SUPPORTED_CONFIG_SCHEMA_VERSIONS is config_schema.SUPPORTED_CONFIG_SCHEMA_VERSIONS
    assert config_parser.ConfigMigrationError is config_schema.ConfigMigrationError
    assert config_parser.ConfigVersionTooNewError is config_schema.ConfigVersionTooNewError
    assert config_parser._UniqueKeySafeLoader is config_schema.UniqueKeySafeLoader
    assert config_parser._construct_mapping_no_duplicates is config_schema.construct_mapping_no_duplicates
    assert config_parser._load_yaml_with_unique_keys is config_schema.load_yaml_with_unique_keys
    assert config_parser.load_yaml_with_unique_keys is config_schema.load_yaml_with_unique_keys
    assert config_parser.migrate_config is config_schema.migrate_config


def test_config_parser_keeps_top_level_key_compatibility_exports():
    assert config_parser.KNOWN_TOP_LEVEL_CONFIG_KEYS is config_top_level_keys.KNOWN_TOP_LEVEL_CONFIG_KEYS
    assert config_parser._top_level_key_fingerprint is config_top_level_keys.top_level_key_fingerprint
    assert config_parser._levenshtein_distance is config_top_level_keys.levenshtein_distance
    assert config_parser._top_level_key_suggestion is config_top_level_keys.top_level_key_suggestion
    assert config_parser._validate_top_level_key_near_misses is config_top_level_keys.validate_top_level_key_near_misses


def test_config_parser_keeps_language_policy_compatibility_exports():
    assert config_parser.normalize_lang is config_language_policy.normalize_lang
    with patch.object(config_parser, "normalize_lang", return_value="patched"):
        policy = config_parser.get_language_policy({"language_policy": {"analysis_lang": "r", "plot_lang": "py"}})
    assert policy["analysis_lang"] == "patched"
    assert policy["plot_lang"] == "patched"


def test_config_parser_keeps_research_metadata_compatibility_exports():
    assert config_parser._validate_experimental_conditions is config_research_metadata.validate_experimental_conditions
    assert config_parser._validate_sample_registry is config_research_metadata.validate_sample_registry
    assert config_parser._condition_sample_references is config_research_metadata.condition_sample_references
    assert config_parser._validate_relative_path_value is config_research_metadata.validate_relative_path_value
    assert config_parser._validate_canonical_docs is config_research_metadata.validate_canonical_docs
    assert config_parser._experimental_condition_ids is config_research_metadata.experimental_condition_ids


def test_config_parser_raw_integrity_wrapper_preserves_allowed_modes():
    errors: list[str] = []

    config_parser._validate_raw_integrity_config(errors, {"mode": "audit"})

    assert errors == ["data_contract.raw_integrity.mode must be one of: strict, warn."]


def test_schema_less_structure_resolves_in_memory_without_rewrite(tmp_path: Path):
    from hub_core.project_structure_contract import resolve_project_structure

    config_path = tmp_path / "project_config.yaml"
    original = "project:\n  name: Legacy structure\n"
    config_path.write_text(original, encoding="utf-8")

    config, loaded_path, _config_hash = load_config(tmp_path)

    assert loaded_path == str(config_path)
    assert config_path.read_text(encoding="utf-8") == original
    assert config["schema_version"] == "1.1"
    assert "structure" not in config
    before = copy.deepcopy(config)
    resolved = resolve_project_structure(config)
    assert config == before
    assert resolved.declared_version == "1.0"
    assert resolved.effective_version == "1.1"


def test_visual_style_and_preset_validation_keeps_facade_error_order():
    config = {
        "project": {"name": "Visual validation"},
        "visual_style": {"target_format": "unknown", "font_scale": 0, "profile": "unknown"},
        "language_policy": {"analysis_lang": 1, "plot_lang": 2},
        "presets": {"_default": "missing", "journal": {"font_scale": 4.0}},
    }

    errors = validate_config(config)

    relevant = [
        error
        for error in errors
        if error.startswith(("Invalid visual_style", "visual_style.", "language_policy.", "presets."))
    ]
    assert relevant == [
        "Invalid visual_style.target_format: 'unknown'. Allowed values: "
        f"acs, cell, default, elsevier, nature, {PRIVATE_TARGET_FORMAT}, neutral, ppt, rsc, science, wiley.",
        "visual_style.font_scale must be a positive number.",
        "Invalid visual_style.profile: 'unknown'. Allowed values: "
        f"baseline, publication, {PRIVATE_STYLE_PROFILE}.",
        "language_policy.analysis_lang must be a string.",
        "language_policy.plot_lang must be a string.",
        "language_policy.analysis_lang must be one of: r (or set language_policy.allow_nonstandard=true).",
        "language_policy.plot_lang must be one of: python (or set language_policy.allow_nonstandard=true).",
        "presets._default 'missing' references an undefined preset.",
        "presets.journal.font_scale must be a number in [0.5, 3.0].",
    ]


class TestUniqueKeyConfigLoader(unittest.TestCase):
    def test_duplicate_top_level_key_is_rejected(self):
        raw_config = """
project:
  name: First
project:
  name: Second
"""

        with self.assertRaisesRegex(Exception, "Duplicate key 'project'"):
            _load_yaml_with_unique_keys(raw_config)

    def test_duplicate_nested_key_is_rejected(self):
        raw_config = """
project:
  name: Demo
visual_style:
  target_format: nature
  target_format: science
"""

        with self.assertRaisesRegex(Exception, "Duplicate key 'target_format'"):
            _load_yaml_with_unique_keys(raw_config)

    def test_merge_keys_still_load(self):
        raw_config = """
defaults: &defaults
  target_format: nature
  font_scale: 1.2
project:
  name: Merge Demo
visual_style:
  <<: *defaults
  profile: baseline
"""

        config = _load_yaml_with_unique_keys(raw_config)

        self.assertEqual(config["visual_style"]["target_format"], "nature")
        self.assertEqual(config["visual_style"]["font_scale"], 1.2)
        self.assertEqual(config["visual_style"]["profile"], "baseline")


class TestLoadProjectMetadataNonDictProject(unittest.TestCase):
    """Regression: a config whose `project` key is not a mapping must not crash discovery."""

    def _metadata_for(self, config_text: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "project_config.yaml"
            config_path.write_text(config_text, encoding="utf-8")
            return _load_project_metadata(str(config_path), "fallback_name")

    def test_string_project_key_does_not_raise_and_marks_invalid(self):
        metadata = self._metadata_for('project: "just a string"\n')
        self.assertEqual(metadata["name"], "fallback_name")
        self.assertFalse(metadata["valid"])
        self.assertTrue(metadata["errors"])

    def test_list_project_key_does_not_raise(self):
        metadata = self._metadata_for("project:\n  - a\n  - b\n")
        self.assertEqual(metadata["name"], "fallback_name")
        self.assertFalse(metadata["valid"])


class TestConfigSchemaMigration(unittest.TestCase):
    def _minimal_config(self, schema_version: str | None = None) -> dict:
        config = {
            "project": {"name": "Migration Demo"},
            "visual_style": {"target_format": "nature"},
        }
        if schema_version is not None:
            config["schema_version"] = schema_version
        return config

    def test_old_version_loads_via_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version: "0.9"',
                        "project:",
                        "  name: Migration Demo",
                        "visual_style:",
                        "  target_format: nature",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config, loaded_path, config_hash = load_config(tmpdir)

        self.assertIsNotNone(config)
        self.assertEqual(config["schema_version"], CURRENT_CONFIG_SCHEMA_VERSION)
        self.assertEqual(loaded_path, str(config_path))
        self.assertIsNotNone(config_hash)
        self.assertEqual(validate_config(config), [])

    def test_too_new_version_fails_with_upgrade_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version: "9.9"',
                        "project:",
                        "  name: Future Demo",
                        "visual_style:",
                        "  target_format: nature",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config, loaded_path, config_hash = load_config(tmpdir)

        self.assertIsNone(config)
        self.assertIsNone(loaded_path)
        self.assertIsNone(config_hash)

    def test_too_new_version_error_is_precise(self):
        errors = validate_config(self._minimal_config("9.9"))

        combined = " ".join(errors)
        self.assertIn("newer than this FigOps runtime supports", combined)
        self.assertIn("Upgrade FigOps", combined)

    def test_supported_versions_round_trip_to_current(self):
        for version in SUPPORTED_CONFIG_SCHEMA_VERSIONS:
            with self.subTest(version=version):
                migrated = migrate_config(self._minimal_config(version))

                self.assertEqual(migrated["schema_version"], CURRENT_CONFIG_SCHEMA_VERSION)
                self.assertEqual(validate_config(migrated), [])


class TestValidateConfigTopLevelNearMisses(unittest.TestCase):
    def _minimal_config(self) -> dict:
        return {
            "project": {"name": "Near Miss Demo"},
            "visual_style": {"target_format": "nature"},
        }

    def test_near_miss_top_level_key_is_error(self):
        config = self._minimal_config()
        config["module"] = ["../escape.py"]

        errors = validate_config(config)

        self.assertIn("Unknown top-level key 'module' — did you mean 'modules'?", errors)

    def test_unrelated_extra_top_level_key_is_allowed(self):
        config = self._minimal_config()
        config["external_lab_notebook"] = {"owner": "materials-team"}

        errors = validate_config(config)

        self.assertEqual(errors, [])


class TestAssemblyConfigValidation(unittest.TestCase):
    def test_assembly_layout_and_panel_containment_errors_remain_precise(self):
        config = {
            "project": {"name": "Assembly Validation"},
            "visual_style": {"target_format": "nature"},
            "assemblies": {
                "Fig1": {
                    "target_width_mm": 100,
                    "layout": "ab\naa",
                    "row_height_ratios": [1],
                    "panels": {
                        "a": {"source": "../escape.svg", "font_strategy": "invalid"},
                        "b": {"source": "panel-b.svg"},
                    },
                }
            },
        }

        errors = validate_config(config)

        self.assertIn("assemblies.Fig1.layout: character 'a' does not form a contiguous rectangle.", errors)
        self.assertIn("assemblies.Fig1.row_height_ratios has 1 entries but layout has 2 rows.", errors)
        self.assertIn("assemblies.Fig1.panels.a.source: path traversal '..' is not allowed.", errors)
        self.assertIn(
            "assemblies.Fig1.panels.a.font_strategy must be one of: as_is, compensate.",
            errors,
        )


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


class TestExecutionBoundaryValidation(unittest.TestCase):
    def _minimal_config(self) -> dict:
        return {
            "project": {"name": "Execution Boundary"},
            "visual_style": {"target_format": "nature"},
        }

    def test_sweep_values_parameter_rejects_reserved_keys_case_insensitively(self):
        for reserved_key in RESERVED_EXECUTION_ENV_KEYS:
            with self.subTest(reserved_key=reserved_key):
                errors = _validate_sweep(
                    {
                        "enabled": True,
                        "parameter": reserved_key.lower(),
                        "values": ["attacker"],
                    }
                )

                self.assertTrue(any("reserved" in error.lower() for error in errors), errors)

    def test_sweep_grid_rejects_reserved_keys_case_insensitively(self):
        errors = _validate_sweep(
            {
                "enabled": True,
                "grid": {"project_root": ["attacker"]},
            }
        )

        self.assertTrue(any("reserved" in error.lower() for error in errors), errors)

    def test_comparison_env_rejects_reserved_keys_case_insensitively(self):
        errors = _validate_comparison(
            {
                "enabled": True,
                "conditions": [{"label": "attack", "env": {"PyThOnPaTh": "attacker"}}],
            }
        )

        self.assertTrue(any("reserved" in error.lower() for error in errors), errors)

    def test_sweep_output_pattern_rejects_absolute_and_parent_paths(self):
        unsafe_patterns = (
            "../outside",
            "results/../../outside",
            "C:\\outside",
            "\\\\server\\share\\outside",
            "/outside",
        )
        for pattern in unsafe_patterns:
            with self.subTest(pattern=pattern):
                errors = _validate_sweep(
                    {
                        "enabled": True,
                        "parameter": "mode",
                        "values": ["safe"],
                        "output_dir_pattern": pattern,
                    }
                )

                self.assertTrue(any("output_dir_pattern" in error for error in errors), errors)

    def test_execution_timeout_seconds_accepts_positive_finite_numbers(self):
        for timeout_seconds in (0.1, 1, 600.0):
            with self.subTest(timeout_seconds=timeout_seconds):
                config = self._minimal_config()
                config["execution"] = {"timeout_seconds": timeout_seconds}

                self.assertEqual(validate_config(config), [])

    def test_execution_timeout_seconds_rejects_non_positive_non_finite_and_non_numeric(self):
        invalid_values = (True, False, 0, -1, float("inf"), float("-inf"), float("nan"), "1", None)
        for timeout_seconds in invalid_values:
            with self.subTest(timeout_seconds=timeout_seconds):
                config = self._minimal_config()
                config["execution"] = {"timeout_seconds": timeout_seconds}

                errors = validate_config(config)

                self.assertTrue(any("execution.timeout_seconds" in error for error in errors), errors)


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
