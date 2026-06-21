import tempfile
import unittest
from pathlib import Path

from hub_core.config_parser import load_config, validate_config
from hub_core.mcp import GraphHubMCPServer


def _minimal_config() -> dict:
    return {
        "project": {"name": "Experiment Conditions Demo"},
        "visual_style": {"target_format": "nature"},
    }


def _valid_experimental_conditions() -> dict:
    return {
        "common": {
            "instrument": "Hioki IM3523 LCR meter",
            "electrode": "Aluminum foil, 12 mm diameter",
            "voltage_Vrms": 2.0,
            "temperature_C": 25,
            "atmosphere": "ambient",
        },
        "conditions": [
            {
                "id": "lcr_al_foil_fab260406",
                "description": "S85 - Al foil electrode",
                "parameters": {
                    "samples": ["S85"],
                    "batch": "fab260406",
                },
            }
        ],
        "equipment": [
            {
                "name": "Hioki IM3523 LCR meter",
                "role": "impedance analyzer",
            }
        ],
    }


class ExperimentalConditionsValidationTest(unittest.TestCase):
    def test_valid_experimental_conditions_pass_validation(self):
        config = _minimal_config()
        config["experimental_conditions"] = _valid_experimental_conditions()

        self.assertEqual(validate_config(config), [])

    def test_condition_missing_id_fails_validation(self):
        config = _minimal_config()
        config["experimental_conditions"] = {"conditions": [{"description": "missing id"}]}

        errors = validate_config(config)

        self.assertTrue(any("experimental_conditions.conditions[1].id" in error for error in errors))

    def test_duplicate_condition_id_fails_validation(self):
        config = _minimal_config()
        config["experimental_conditions"] = {
            "conditions": [
                {"id": "lcr_al_foil_fab260406"},
                {"id": "lcr_al_foil_fab260406"},
            ]
        }

        errors = validate_config(config)

        self.assertTrue(any("Duplicate experimental_conditions.conditions id" in error for error in errors))

    def test_conditions_must_be_list(self):
        config = _minimal_config()
        config["experimental_conditions"] = {"conditions": {"id": "not-a-list"}}

        errors = validate_config(config)

        self.assertTrue(any("experimental_conditions.conditions must be a list" in error for error in errors))

    def test_parameters_samples_must_be_list(self):
        config = _minimal_config()
        config["experimental_conditions"] = {
            "conditions": [
                {
                    "id": "lcr_al_foil_fab260406",
                    "parameters": {"samples": "S85"},
                }
            ]
        }

        errors = validate_config(config)

        self.assertTrue(
            any("experimental_conditions.conditions[1].parameters.samples must be a list" in error for error in errors)
        )

    def test_parameters_batch_must_be_string(self):
        config = _minimal_config()
        config["experimental_conditions"] = {
            "conditions": [
                {
                    "id": "lcr_al_foil_fab260406",
                    "parameters": {"batch": 260406},
                }
            ]
        }

        errors = validate_config(config)

        self.assertTrue(
            any("experimental_conditions.conditions[1].parameters.batch must be a string" in error for error in errors)
        )

    def test_config_without_experimental_conditions_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_exp_conditions_") as tmpdir:
            project_dir = Path(tmpdir)
            config_path = project_dir / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        "  name: No Conditions Demo",
                        "visual_style:",
                        "  target_format: nature",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config, loaded_path, config_hash = load_config(str(project_dir))

        self.assertIsNotNone(config)
        self.assertEqual(config["project"]["role"], "module")
        self.assertEqual(loaded_path, str(config_path))
        self.assertIsNotNone(config_hash)
        self.assertNotIn("experimental_conditions", config)
        self.assertEqual(validate_config(config), [])


class ExperimentalConditionsMCPInspectTest(unittest.TestCase):
    def test_inspect_project_surfaces_experimental_conditions_summary(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_exp_conditions_") as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "module"
            project_dir.mkdir()
            config_path = project_dir / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        "  name: Condition Summary Demo",
                        "experimental_conditions:",
                        "  conditions:",
                        "    - id: lcr_al_foil_fab260406",
                        "      description: S85 - Al foil electrode",
                        "    - id: lcr_au_probe_fab260407",
                        "visual_style:",
                        "  target_format: nature",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool(
                "graphhub.inspect_project",
                {"project_path": "module"},
            )["structuredContent"]

        summary = result["experimental_conditions_summary"]
        self.assertEqual(summary["condition_count"], 2)
        self.assertEqual(summary["condition_ids"], ["lcr_al_foil_fab260406", "lcr_au_probe_fab260407"])
