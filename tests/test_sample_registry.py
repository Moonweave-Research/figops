import tempfile
import unittest
from pathlib import Path

from hub_core.config_parser import load_config, validate_config
from hub_core.mcp import GraphHubMCPServer


def _minimal_config() -> dict:
    return {
        "project": {"name": "Sample Registry Demo"},
        "visual_style": {"target_format": "nature"},
    }


def _valid_sample_registry() -> list[dict]:
    return [
        {
            "sample_id": "S60",
            "composition": "60 wt%",
            "material": "ionoelastomer",
            "batch": "fab260406",
            "fabrication_date": "260406",
            "status": "active",
            "notes": "canonical sample identity",
            "raw_paths": ["raw/S60", "measurements/lcr/S60.csv"],
        },
        {
            "sample_id": "S75",
            "composition": 75,
            "material": "ionoelastomer",
            "batch": "fab260406",
        },
        {
            "sample_id": "S85",
            "composition": "85 wt%",
            "material": "ionoelastomer",
            "batch": "fab260406",
        },
    ]


class SampleRegistryValidationTest(unittest.TestCase):
    def test_valid_sample_registry_passes_validation(self):
        config = _minimal_config()
        config["sample_registry"] = _valid_sample_registry()
        config["experimental_conditions"] = {
            "conditions": [
                {
                    "id": "lcr_al_foil_fab260406",
                    "parameters": {"samples": ["S60", "S75", "S85"]},
                }
            ]
        }

        self.assertEqual(validate_config(config), [])

    def test_duplicate_sample_id_fails_validation(self):
        config = _minimal_config()
        config["sample_registry"] = [
            {"sample_id": "S85"},
            {"sample_id": "S85"},
        ]

        errors = validate_config(config)

        self.assertTrue(any("Duplicate sample_registry sample_id: 'S85'" in error for error in errors))

    def test_condition_sample_reference_must_exist_in_registry(self):
        config = _minimal_config()
        config["sample_registry"] = [{"sample_id": "S85"}]
        config["experimental_conditions"] = {
            "conditions": [
                {
                    "id": "lcr_al_foil_fab260406",
                    "parameters": {"samples": ["S85", "S999"]},
                }
            ]
        }

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("Unknown sample_id(s)", combined)
        self.assertIn("S999", combined)

    def test_raw_paths_must_be_relative_without_traversal(self):
        config = _minimal_config()
        config["sample_registry"] = [
            {"sample_id": "S60", "raw_paths": ["raw/S60", "/tmp/S60.csv", "../outside/S60.csv"]}
        ]

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("sample_registry[1].raw_paths", combined)
        self.assertIn("absolute path", combined)
        self.assertIn("path traversal", combined)

    def test_config_without_sample_registry_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_sample_registry_") as tmpdir:
            project_dir = Path(tmpdir)
            config_path = project_dir / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        "  name: No Registry Demo",
                        "experimental_conditions:",
                        "  conditions:",
                        "    - id: lcr_al_foil_fab260406",
                        "      parameters:",
                        "        samples: [S999]",
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
        self.assertNotIn("sample_registry", config)
        self.assertEqual(validate_config(config), [])


class SampleRegistryMCPInspectTest(unittest.TestCase):
    def test_inspect_project_surfaces_sample_registry_summary(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_sample_registry_") as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "module"
            project_dir.mkdir()
            config_path = project_dir / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        "  name: Sample Summary Demo",
                        "sample_registry:",
                        "  - sample_id: S60",
                        "    composition: 60 wt%",
                        "  - sample_id: S85",
                        "    composition: 85 wt%",
                        "experimental_conditions:",
                        "  conditions:",
                        "    - id: lcr_al_foil_fab260406",
                        "      parameters:",
                        "        samples: [S60, S85]",
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

        summary = result["sample_registry_summary"]
        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["sample_ids"], ["S60", "S85"])
