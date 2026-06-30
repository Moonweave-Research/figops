import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hub_core.config_parser as config_parser
import hub_core.config_project_registry as config_project_registry
from hub_core.adapters import SurfurConventions
from hub_core.config_parser import list_projects
from hub_core.project_discovery import ProjectDiscoveryService, get_discoverable_projects
from tests._symlink import symlink_or_skip
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT

VALID_CONFIG = """
project:
  name: "{name}"
visual_style:
  target_format: {target_format}
data_contract:
  csv_checks:
    - path: "results/data/summary.csv"
      required_columns: ["x", "y"]
      dtypes: {{ x: float, y: float }}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    output: results/figures/Fig1.png
"""


class ProjectDiscoveryServiceTest(unittest.TestCase):
    def _write_config(self, project_dir: Path, name: str = "Demo") -> Path:
        project_dir.mkdir(parents=True, exist_ok=True)
        config_path = project_dir / "project_config.yaml"
        config_path.write_text(
            VALID_CONFIG.format(name=name, target_format=INTERNAL_STYLE_TARGET_FORMAT),
            encoding="utf-8",
        )
        return config_path

    def _write_legacy_config(self, project_dir: Path, name: str = "Legacy") -> Path:
        config_dir = project_dir / "scripts"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "project_config.yaml"
        config_path.write_text(
            VALID_CONFIG.format(name=name, target_format=INTERNAL_STYLE_TARGET_FORMAT),
            encoding="utf-8",
        )
        return config_path

    def test_generic_conventions_treat_surfur_paths_as_regular_projects(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_config(root / ".worktrees" / "feature" / "02_Worktree", "Worktree Project")
            self._write_config(root / "[Athena]" / "bridge_jobs" / "job1" / "hub_project", "Bridge Job")

            projects = ProjectDiscoveryService(root).discover(max_depth=5)

            by_path = {project.path: project for project in projects}
            self.assertEqual(by_path[".worktrees/feature/02_Worktree"].classification, "official")
            self.assertEqual(by_path["[Athena]/bridge_jobs/job1/hub_project"].classification, "official")

    def test_surfur_conventions_exclude_ephemeral_defaults(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            real_project = Path(tmpdir) / "external" / "01_Project"
            self._write_config(real_project, "Symlinked Project")
            root.mkdir()
            symlink_or_skip(root / "01_Project", real_project, target_is_directory=True)
            self._write_config(root / ".worktrees" / "feature" / "02_Worktree", "Worktree Project")
            self._write_config(root / "[Athena]" / "bridge_jobs" / "job1" / "hub_project", "Bridge Job")

            projects = ProjectDiscoveryService(root, conventions=SurfurConventions()).discover(max_depth=4)

            paths = {project.path for project in projects}
            self.assertIn("01_Project", paths)
            self.assertNotIn(".worktrees/feature/02_Worktree", paths)
            self.assertNotIn("[Athena]/bridge_jobs/job1/hub_project", paths)

            project = next(item for item in projects if item.path == "01_Project")
            self.assertTrue(project.valid)
            self.assertEqual(project.classification, "official")
            self.assertTrue(project.project_id)
            self.assertEqual(project.target_format, INTERNAL_STYLE_TARGET_FORMAT)

    def test_legacy_list_projects_non_recursive_caps_scan_depth(self):
        calls = []

        def fake_discover(_root, *, max_depth):
            calls.append(max_depth)
            return []

        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            with patch("hub_core.config_parser.discover_projects_with_status", side_effect=fake_discover):
                list_projects(tmpdir, recursive=False, max_depth=4)
                list_projects(tmpdir, recursive=True, max_depth=4)

        self.assertEqual(calls, [1, 4])

    def test_config_parser_keeps_project_registry_compatibility_exports(self):
        self.assertIs(
            config_parser._load_registry_operational_states,
            config_project_registry.load_registry_operational_states,
        )
        self.assertIs(config_parser._normalize_registry_path, config_project_registry.normalize_registry_path)
        self.assertIs(config_parser._resolve_operational_state, config_project_registry.resolve_operational_state)
        states = {
            config_project_registry.normalize_registry_path("Study"): "active",
            config_project_registry.normalize_registry_path(str(Path("Study") / "modules")): "module-active",
        }

        self.assertEqual(
            config_parser._resolve_operational_state(states, str(Path("Study") / "modules" / "A")),
            "module-active",
        )
        self.assertEqual(config_parser._resolve_operational_state(states, str(Path("Study") / "docs")), "active")
        self.assertEqual(config_parser._resolve_operational_state(states, "Other"), "-")

    def test_invalid_configs_are_visible_with_errors(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            invalid_project = root / "02_Invalid"
            invalid_project.mkdir(parents=True)
            (invalid_project / "project_config.yaml").write_text("project: {}\n", encoding="utf-8")

            projects = ProjectDiscoveryService(root).discover(max_depth=3)

            self.assertEqual(len(projects), 1)
            project = projects[0]
            self.assertEqual(project.path, "02_Invalid")
            self.assertFalse(project.valid)
            self.assertEqual(project.classification, "invalid")
            self.assertTrue(project.errors)

    def test_legacy_config_path_is_visible_and_classified(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_legacy_config(root / "03_Legacy", "Legacy Project")

            projects = ProjectDiscoveryService(root).discover(max_depth=3)

            self.assertEqual(len(projects), 1)
            project = projects[0]
            self.assertTrue(project.valid)
            self.assertEqual(project.path, "03_Legacy")
            self.assertEqual(project.config, "scripts/project_config.yaml")
            self.assertEqual(project.classification, "legacy")

    def test_can_include_ephemeral_and_worktree_projects_explicitly(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_config(root / ".worktrees" / "feature" / "02_Worktree", "Worktree Project")
            self._write_config(root / "[Athena]" / "bridge_jobs" / "job1" / "hub_project", "Bridge Job")

            projects = ProjectDiscoveryService(
                root,
                include_worktrees=True,
                include_ephemeral=True,
                conventions=SurfurConventions(),
            ).discover(max_depth=5)

            by_path = {project.path: project for project in projects}
            self.assertEqual(by_path[".worktrees/feature/02_Worktree"].classification, "ephemeral")
            self.assertEqual(by_path["[Athena]/bridge_jobs/job1/hub_project"].classification, "ephemeral")

    def test_quarantine_zone_projects_are_listed_but_not_runnable_by_default(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            quarantine_paths = [
                "_archive/Old_Project",
                "_quarantine/Suspect_Project",
                "_cross_validation/Cross_Check",
                "legacy_old/Legacy_Project",
                "old_legacy/Legacy_Project",
                "planning.bak_260607/Bak_Project",
            ]
            for rel_path in quarantine_paths:
                self._write_config(root / rel_path, rel_path)
            self._write_config(root / "01_Normal", "Normal Project")

            projects = ProjectDiscoveryService(root).discover(max_depth=4)
            runnable = get_discoverable_projects(root, max_depth=4)

            by_path = {project.path: project for project in projects}
            for rel_path in quarantine_paths:
                self.assertEqual(by_path[rel_path].classification, "quarantine")
                self.assertTrue(by_path[rel_path].valid)
            self.assertEqual(by_path["01_Normal"].classification, "official")

            runnable_paths = {project["path"] for project in runnable}
            self.assertNotIn("_archive/Old_Project", runnable_paths)
            self.assertEqual(runnable_paths, {"01_Normal"})

    def test_include_quarantine_opts_quarantine_projects_back_into_runnable_surface(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_config(root / "_archive" / "Old_Project", "Old Project")

            runnable = get_discoverable_projects(root, max_depth=3, include_quarantine=True)

            self.assertEqual([project["path"] for project in runnable], ["_archive/Old_Project"])

    def test_nested_researchos_ephemeral_paths_are_classified_from_workspace_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "workspace"
            self._write_config(
                root / "ResearchOS" / ".worktrees" / "feature" / "02_Worktree",
                "Worktree Project",
            )
            self._write_config(
                root / "ResearchOS" / "[Athena]" / "bridge_jobs" / "job1" / "hub_project",
                "Bridge Job",
            )

            hidden = ProjectDiscoveryService(root, conventions=SurfurConventions()).discover(max_depth=6)
            included = ProjectDiscoveryService(
                root,
                include_worktrees=True,
                include_ephemeral=True,
                conventions=SurfurConventions(),
            ).discover(max_depth=6)

            self.assertEqual(hidden, [])
            by_path = {project.path: project for project in included}
            self.assertEqual(
                by_path["ResearchOS/.worktrees/feature/02_Worktree"].classification,
                "ephemeral",
            )
            self.assertEqual(
                by_path["ResearchOS/[Athena]/bridge_jobs/job1/hub_project"].classification,
                "ephemeral",
            )


if __name__ == "__main__":
    unittest.main()
