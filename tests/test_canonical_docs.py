import tempfile
import unittest
from pathlib import Path

import yaml

from hub_core.config_parser import validate_config
from hub_core.mcp import GraphHubMCPServer


def _base_config() -> dict:
    return {
        "project": {"name": "Canonical Docs Demo"},
        "visual_style": {"target_format": "nature"},
    }


def _write_project(project_dir: Path, config: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


class CanonicalDocsConfigValidationTest(unittest.TestCase):
    def test_valid_ordered_canonical_docs_pass_validation(self):
        config = _base_config()
        config["canonical_docs"] = [
            "docs/charter.md",
            {"path": "docs/figure_composition.md", "label": "Figure composition"},
        ]

        self.assertEqual(validate_config(config), [])

    def test_absolute_and_traversal_paths_fail_validation(self):
        config = _base_config()
        config["canonical_docs"] = ["/tmp/charter.md", {"path": "../docs/checklist.md"}]

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("canonical_docs[1].path", combined)
        self.assertIn("canonical_docs[2].path", combined)

    def test_duplicate_paths_fail_validation(self):
        config = _base_config()
        config["canonical_docs"] = ["docs/charter.md", {"path": "docs/charter.md", "label": "Duplicate"}]

        errors = validate_config(config)

        self.assertTrue(any("Duplicate canonical_docs path: 'docs/charter.md'" in error for error in errors))

    def test_config_without_canonical_docs_is_unchanged(self):
        self.assertEqual(validate_config(_base_config()), [])


class CanonicalDocsMCPValidationTest(unittest.TestCase):
    def test_missing_declared_canonical_doc_fails_by_default_for_module(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_canonical_docs_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["canonical_docs"] = ["docs/missing.md"]
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "module"})["structuredContent"]

        self.assertFalse(result["valid"])
        self.assertTrue(any("Missing canonical doc" in error for error in result["config_errors"]))

    def test_explicit_false_opt_out_keeps_missing_canonical_doc_advisory(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_canonical_docs_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["canonical_docs"] = ["docs/missing.md"]
            config["data_contract"] = {"require_canonical_docs": False}
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "module"})["structuredContent"]

        self.assertTrue(result["valid"])
        self.assertEqual(result["config_errors"], [])
        self.assertTrue(any("Missing canonical doc" in warning for warning in result["warnings"]))

    def test_master_canonical_docs_are_not_enforced_by_module_default(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_canonical_docs_") as tmpdir:
            root = Path(tmpdir)
            project = root / "master"
            config = _base_config()
            config["project"]["role"] = "master"
            config["modules"] = ["modules/experiment_a"]
            config["canonical_docs"] = ["docs/missing.md"]
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "master"})["structuredContent"]

        self.assertTrue(result["valid"])
        self.assertEqual(result["config_errors"], [])
        self.assertTrue(any("Missing canonical doc" in warning for warning in result["warnings"]))

    def test_missing_canonical_doc_fails_when_required(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_canonical_docs_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _base_config()
            config["canonical_docs"] = ["docs/missing.md"]
            config["data_contract"] = {"require_canonical_docs": True}
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.validate_project", {"project_path": "module"})["structuredContent"]

        self.assertFalse(result["valid"])
        self.assertTrue(any("Missing canonical doc" in error for error in result["config_errors"]))

    def test_inspect_project_surfaces_ordered_registry_with_existence(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_canonical_docs_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            (project / "docs").mkdir(parents=True)
            (project / "docs" / "charter.md").write_text("# Charter\n", encoding="utf-8")
            config = _base_config()
            config["canonical_docs"] = [
                "docs/charter.md",
                {"path": "docs/missing.md", "label": "Missing doc"},
            ]
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool("graphhub.inspect_project", {"project_path": "module"})["structuredContent"]

        registry = result["canonical_docs_registry"]
        self.assertEqual([doc["path"] for doc in registry["docs"]], ["docs/charter.md", "docs/missing.md"])
        self.assertEqual([doc["precedence"] for doc in registry["docs"]], [0, 1])
        self.assertEqual(registry["docs"][1]["label"], "Missing doc")
        self.assertTrue(registry["docs"][0]["exists"])
        self.assertFalse(registry["docs"][1]["exists"])
