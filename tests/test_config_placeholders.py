import tempfile
import unittest
from pathlib import Path

import yaml

from hub_core.config_parser import validate_config
from hub_core.mcp import GraphHubMCPServer


def _base_config() -> dict:
    return {
        "project": {"name": "Placeholder Demo"},
        "visual_style": {"target_format": "nature"},
    }


def _write_project(project_dir: Path, config: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


class ConfigPlaceholderMCPTest(unittest.TestCase):
    def test_placeholder_strings_warn_without_failing_by_default(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_placeholders_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["experimental_conditions"] = {
                "common": {
                    "voltage_V": "TODO",
                    "operator": "FIXME: fill operator",
                    "sample_note": "<fill>",
                }
            }
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "module"})["structuredContent"]

        self.assertTrue(result["valid"])
        self.assertEqual(result["config_errors"], [])
        report = result["placeholder_report"]
        self.assertEqual(
            {item["path"] for item in report["placeholders"]},
            {
                "experimental_conditions.common.voltage_V",
                "experimental_conditions.common.operator",
                "experimental_conditions.common.sample_note",
            },
        )
        self.assertTrue(any("Config placeholder" in warning for warning in result["warnings"]))

    def test_forbid_todo_placeholders_escalates_to_validation_error(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_placeholders_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["data_contract"] = {"forbid_todo_placeholders": True}
            config["experimental_conditions"] = {"common": {"voltage_V": "TODO"}}
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "module"})["structuredContent"]

        self.assertFalse(result["valid"])
        self.assertTrue(
            any("experimental_conditions.common.voltage_V" in error for error in result["config_errors"])
        )

    def test_prose_with_incidental_words_is_not_flagged(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_placeholders_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["experimental_conditions"] = {
                "common": {
                    "note": "methodology to be determined later",
                    "description": "The TODOmeter label is a literal instrument nickname",
                }
            }
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "module"})["structuredContent"]

        self.assertTrue(result["valid"])
        self.assertEqual(result["placeholder_report"]["placeholders"], [])
        self.assertFalse(any("Config placeholder" in warning for warning in result["warnings"]))

    def test_config_without_placeholders_is_unchanged(self):
        config = _base_config()
        config["experimental_conditions"] = {"common": {"voltage_V": "2.0"}}

        self.assertEqual(validate_config(config), [])

    def test_inspect_project_surfaces_placeholder_report(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_placeholders_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["experimental_conditions"] = {"common": {"voltage_V": "TODO"}}
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.inspect_project", {"project_path": "module"})["structuredContent"]

        report = result["placeholder_report"]
        self.assertTrue(report["detected"])
        self.assertEqual(report["placeholders"][0]["path"], "experimental_conditions.common.voltage_V")
