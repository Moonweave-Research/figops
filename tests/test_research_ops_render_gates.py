import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import orchestrator
from hub_core.mcp import GraphHubMCPServer
from hub_core.raw_integrity import seal_raw_integrity


def _module_config() -> dict:
    return {
        "project": {"name": "Research Ops Module"},
        "visual_style": {"target_format": "nature"},
        "language_policy": {"allow_nonstandard": True, "analysis_lang": "python", "plot_lang": "python"},
        "figures": [{"id": "fig1", "script": "plot.py", "output": "results/fig1.png"}],
    }


def _write_project(project_dir: Path, config: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _write_raw(project_dir: Path, contents: str) -> None:
    raw_path = project_dir / "raw" / "data.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(contents, encoding="utf-8")


class ResearchOpsRenderGateTest(unittest.TestCase):
    def test_mcp_render_blocks_default_raw_integrity_drift(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _module_config()
            config["data_contract"] = {
                "raw_integrity": {
                    "manifest": "raw/.raw_manifest.json",
                    "paths": ["raw/"],
                }
            }
            _write_project(project, config)
            _write_raw(project, "x,y\n1,2\n")
            seal_raw_integrity(project, config)
            _write_raw(project, "x,y\n1,99\n")
            server = GraphHubMCPServer(research_root=root, runtime_root=root / "runtime", write_tools_enabled=True)

            response = server.call_tool(
                "graphhub.render_project_figure",
                {"project_path": "module", "figure_id": "fig1", "dry_run": True},
            )
            result = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("raw_integrity drift" in error for error in result["errors"]))

    def test_mcp_render_allows_explicit_raw_warn_opt_out(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _module_config()
            config["data_contract"] = {
                "raw_integrity": {
                    "manifest": "raw/.raw_manifest.json",
                    "mode": "warn",
                    "paths": ["raw/"],
                }
            }
            _write_project(project, config)
            _write_raw(project, "x,y\n1,2\n")
            seal_raw_integrity(project, config)
            _write_raw(project, "x,y\n1,99\n")
            server = GraphHubMCPServer(research_root=root, runtime_root=root / "runtime", write_tools_enabled=True)

            response = server.call_tool(
                "graphhub.render_project_figure",
                {"project_path": "module", "figure_id": "fig1", "dry_run": True},
            )
            result = response["structuredContent"]

        self.assertFalse(response["isError"])
        self.assertEqual(result["artifact_status"], "validated")

    def test_mcp_render_blocks_missing_declared_canonical_doc_by_default(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _module_config()
            config["canonical_docs"] = ["docs/missing.md"]
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root, runtime_root=root / "runtime", write_tools_enabled=True)

            response = server.call_tool(
                "graphhub.render_project_figure",
                {"project_path": "module", "figure_id": "fig1", "dry_run": True},
            )
            result = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertTrue(any("Missing canonical doc" in error for error in result["errors"]))

    def test_mcp_render_blocks_partial_declared_traceability_by_default(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _module_config()
            config["sample_registry"] = [{"sample_id": "S1"}]
            config["experimental_conditions"] = {"conditions": [{"id": "condition_a"}]}
            config["figures"][0]["claim"] = "Measured response increases."
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root, runtime_root=root / "runtime", write_tools_enabled=True)

            response = server.call_tool(
                "graphhub.render_project_figure",
                {"project_path": "module", "figure_id": "fig1", "dry_run": True},
            )
            result = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertTrue(any("missing samples" in error and "missing conditions" in error for error in result["errors"]))

    def test_cli_render_blocks_missing_declared_canonical_doc_before_execution(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "module"
            config = _module_config()
            config["canonical_docs"] = ["docs/missing.md"]
            _write_project(project, config)
            argv = ["orchestrator.py", "--project", str(project), "--step", "plot"]

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", argv),
                patch("orchestrator.get_hub_path", return_value=str(root)),
                patch("orchestrator.get_research_root", return_value=str(root)),
                patch("orchestrator.run_preflight_check"),
                patch(
                    "orchestrator.validate_environment_locks",
                    side_effect=AssertionError("research-ops gate should run before environment validation"),
                ),
                patch("orchestrator.run_plots", side_effect=AssertionError("render should not execute")),
                patch("orchestrator.logger.error") as log_error,
            ):
                rc = orchestrator.main()

        self.assertEqual(rc, 1)
        self.assertIn("Missing canonical doc", " ".join(str(call) for call in log_error.mock_calls))

    def test_mcp_render_refuses_legacy_project_before_research_ops_enforcement(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "legacy_module"
            config = _module_config()
            config["project"]["status"] = "legacy"
            config["canonical_docs"] = ["docs/missing.md"]
            config["experimental_conditions"] = {
                "conditions": [{"id": "old_run", "parameters": {"voltage_V": "TODO"}}]
            }
            _write_project(project, config)
            server = GraphHubMCPServer(research_root=root, runtime_root=root / "runtime", write_tools_enabled=True)

            response = server.call_tool(
                "graphhub.render_project_figure",
                {"project_path": "legacy_module", "figure_id": "fig1", "dry_run": True},
            )
            result = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertEqual(result["status"], "error")
        combined = " ".join([result["summary"], *result["errors"]]).lower()
        self.assertIn("legacy", combined)
        self.assertIn("rendering is disabled", combined)
        self.assertNotIn("missing canonical doc", combined)
        self.assertNotIn("todo", combined)

    def test_cli_render_refuses_legacy_project_before_research_ops_enforcement(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_render_ops_") as tmpdir:
            root = Path(tmpdir)
            project = root / "legacy_module"
            config = _module_config()
            config["project"]["status"] = "legacy"
            config["canonical_docs"] = ["docs/missing.md"]
            config["experimental_conditions"] = {
                "conditions": [{"id": "old_run", "parameters": {"voltage_V": "TODO"}}]
            }
            _write_project(project, config)
            argv = ["orchestrator.py", "--project", str(project), "--step", "plot"]

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", argv),
                patch("orchestrator.get_hub_path", return_value=str(root)),
                patch("orchestrator.get_research_root", return_value=str(root)),
                patch("orchestrator.run_preflight_check"),
                patch(
                    "orchestrator.validate_environment_locks",
                    side_effect=AssertionError("legacy render should not reach environment validation"),
                ),
                patch("orchestrator.run_plots", side_effect=AssertionError("legacy render should not execute")),
                patch("orchestrator.logger.error") as log_error,
            ):
                rc = orchestrator.main()

        self.assertEqual(rc, 1)
        log_text = " ".join(str(call) for call in log_error.mock_calls).lower()
        self.assertIn("legacy", log_text)
        self.assertIn("rendering is disabled", log_text)
        self.assertNotIn("missing canonical doc", log_text)
        self.assertNotIn("todo", log_text)
