import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import orchestrator
from hub_core.config_parser import load_config, validate_config
from hub_core.mcp import GraphHubMCPServer
from hub_core.project_discovery import discover_projects_with_status, get_discoverable_projects


def _write_config(project_dir: Path, lines: list[str]) -> Path:
    config_path = project_dir / "project_config.yaml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config_path


def _minimal_module_config(name: str = "Module Demo") -> list[str]:
    return [
        "project:",
        f"  name: {name}",
        "visual_style:",
        "  target_format: nature",
        "language_policy:",
        "  allow_nonstandard: true",
        "  analysis_lang: python",
        "  plot_lang: python",
    ]


def _minimal_master_config(name: str = "Master Demo") -> list[str]:
    return [
        "project:",
        f"  name: {name}",
        "  role: master",
        "modules:",
        "  - modules/experiment_a",
        "visual_style:",
        "  target_format: nature",
    ]


class ProjectRoleConfigValidationTest(unittest.TestCase):
    def test_config_without_role_defaults_to_module(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_project_role_") as tmpdir:
            project_dir = Path(tmpdir)
            _write_config(project_dir, _minimal_module_config())

            config, loaded_path, config_hash = load_config(str(project_dir))

        self.assertIsNotNone(config)
        self.assertIsNotNone(loaded_path)
        self.assertIsNotNone(config_hash)
        self.assertEqual(config["project"]["role"], "module")
        self.assertEqual(validate_config(config), [])

    def test_invalid_project_role_fails_validation(self):
        config = {
            "project": {"name": "Bad Role", "role": "portfolio"},
            "visual_style": {"target_format": "nature"},
        }

        errors = validate_config(config)

        self.assertTrue(any("project.role" in error and "master" in error and "module" in error for error in errors))

    def test_master_config_with_runnable_surface_fails_validation(self):
        config = {
            "project": {"name": "Bad Master", "role": "master"},
            "modules": ["modules/experiment_a"],
            "pipeline": {"analysis": [{"script": "analysis.py", "lang": "python"}]},
            "figures": [{"id": "fig1", "script": "plot.py", "output": "results/fig1.png"}],
            "visual_style": {"target_format": "nature"},
            "language_policy": {"allow_nonstandard": True, "analysis_lang": "python", "plot_lang": "python"},
        }

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("master", combined)
        self.assertIn("pipeline", combined)
        self.assertIn("figures", combined)


class ProjectRoleDiscoveryTest(unittest.TestCase):
    def test_discovery_surfaces_role_and_excludes_master_from_runnable_projects(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_project_role_") as tmpdir:
            root = Path(tmpdir)
            master = root / "study_master"
            module = root / "study_master" / "modules" / "experiment_a"
            master.mkdir()
            module.mkdir(parents=True)
            _write_config(master, _minimal_master_config("Study Master"))
            _write_config(module, _minimal_module_config("Experiment A"))

            discovered = discover_projects_with_status(root, max_depth=4)
            runnable = get_discoverable_projects(root, max_depth=4)

        by_name = {project["name"]: project for project in discovered}
        self.assertEqual(by_name["Study Master"]["role"], "master")
        self.assertEqual(by_name["Experiment A"]["role"], "module")
        self.assertEqual({project["name"] for project in runnable}, {"Experiment A"})
        self.assertEqual(runnable[0]["role"], "module")

    def test_mcp_list_and_inspect_surface_project_role(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_project_role_") as tmpdir:
            root = Path(tmpdir)
            master = root / "study_master"
            module = root / "study_master" / "modules" / "experiment_a"
            master.mkdir()
            module.mkdir(parents=True)
            _write_config(master, _minimal_master_config("Study Master"))
            _write_config(module, _minimal_module_config("Experiment A"))
            server = GraphHubMCPServer(research_root=root)

            listed = server.call_tool("graphhub.list_projects", {"max_depth": 4})["structuredContent"]["projects"]
            inspected = server.call_tool(
                "graphhub.inspect_project",
                {"project_path": "study_master"},
            )["structuredContent"]

        listed_by_root = {project["project_root"]: project for project in listed}
        self.assertEqual(listed_by_root["study_master"]["role"], "master")
        self.assertEqual(listed_by_root["study_master/modules/experiment_a"]["role"], "module")
        self.assertEqual(inspected["project_metadata"]["role"], "master")


class ProjectRoleExecutionBoundaryTest(unittest.TestCase):
    def test_orchestrator_refuses_master_project_before_execution(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_project_role_") as tmpdir:
            root_dir = Path(tmpdir)
            project_dir = root_dir / "study_master"
            project_dir.mkdir()
            _write_config(project_dir, _minimal_master_config())
            argv = ["orchestrator.py", "--project", str(project_dir), "--step", "analysis"]

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", argv),
                patch("orchestrator.get_hub_path", return_value=str(root_dir)),
                patch("orchestrator.get_research_root", return_value=str(root_dir)),
                patch("orchestrator.run_preflight_check"),
                patch(
                    "orchestrator.validate_environment_locks",
                    side_effect=AssertionError("master project should not reach environment validation"),
                ),
                patch("orchestrator.run_analysis", side_effect=AssertionError("master project should not execute")),
                patch("orchestrator.logger.error") as log_error,
            ):
                rc = orchestrator.main()

        self.assertEqual(rc, 1)
        log_text = " ".join(str(call) for call in log_error.mock_calls)
        self.assertIn("master project root, not an execution module", log_text)

    def test_mcp_render_project_figure_refuses_master_project(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_project_role_") as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "study_master"
            project_dir.mkdir()
            _write_config(project_dir, _minimal_master_config())
            server = GraphHubMCPServer(research_root=root, runtime_root=root / "runtime", write_tools_enabled=True)

            response = server.call_tool(
                "graphhub.render_project_figure",
                {"project_path": "study_master", "figure_id": "fig1", "dry_run": True},
            )
            result = response["structuredContent"]

        self.assertTrue(response["isError"])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "GRAPHHUB_VALIDATION")
        self.assertIn("master project root, not an execution module", " ".join(result["errors"]))
        self.assertIn("modules/experiment_a", " ".join(result["errors"]))


class ProjectRoleRegressionTest(unittest.TestCase):
    def test_module_without_role_keeps_existing_orchestrator_execution_path(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_project_role_") as tmpdir:
            root_dir = Path(tmpdir)
            project_dir = root_dir / "module_project"
            project_dir.mkdir()
            _write_config(project_dir, _minimal_module_config())
            argv = ["orchestrator.py", "--project", str(project_dir), "--step", "analysis"]
            mock_log = MagicMock(return_value=(str(project_dir / "log.jsonl"), {}))

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", argv),
                patch("orchestrator.get_hub_path", return_value=str(root_dir)),
                patch("orchestrator.get_research_root", return_value=str(root_dir)),
                patch("orchestrator.run_preflight_check"),
                patch(
                    "orchestrator.validate_environment_locks",
                    return_value={"ok": True, "strict": False, "python_lock": {}, "r_lock": {}},
                ),
                patch("orchestrator.load_build_state", return_value=({}, str(project_dir / ".build_state.json"))),
                patch("orchestrator.print_provenance"),
                patch("orchestrator.run_analysis", return_value=True) as run_analysis,
                patch("orchestrator.write_execution_log", side_effect=mock_log),
                patch("hub_core.provenance._readable_git_commit", return_value="git-hash"),
            ):
                rc = orchestrator.main()

        self.assertEqual(rc, 0)
        run_analysis.assert_called_once()
