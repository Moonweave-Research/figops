import tempfile
import unittest
from pathlib import Path

from hub_core.project_discovery import ProjectDiscoveryService


VALID_CONFIG = """
project:
  name: "{name}"
visual_style:
  target_format: nature_surfur
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
        config_path.write_text(VALID_CONFIG.format(name=name), encoding="utf-8")
        return config_path

    def _write_legacy_config(self, project_dir: Path, name: str = "Legacy") -> Path:
        config_dir = project_dir / "scripts"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "project_config.yaml"
        config_path.write_text(VALID_CONFIG.format(name=name), encoding="utf-8")
        return config_path

    def test_discovers_symlinked_projects_and_excludes_ephemeral_defaults(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_discovery_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            real_project = Path(tmpdir) / "external" / "01_Project"
            self._write_config(real_project, "Symlinked Project")
            root.mkdir()
            (root / "01_Project").symlink_to(real_project, target_is_directory=True)
            self._write_config(root / ".worktrees" / "feature" / "02_Worktree", "Worktree Project")
            self._write_config(root / "[Athena]" / "bridge_jobs" / "job1" / "hub_project", "Bridge Job")

            projects = ProjectDiscoveryService(root).discover(max_depth=4)

            paths = {project.path for project in projects}
            self.assertIn("01_Project", paths)
            self.assertNotIn(".worktrees/feature/02_Worktree", paths)
            self.assertNotIn("[Athena]/bridge_jobs/job1/hub_project", paths)

            project = next(item for item in projects if item.path == "01_Project")
            self.assertTrue(project.valid)
            self.assertEqual(project.classification, "official")
            self.assertTrue(project.project_id)
            self.assertEqual(project.target_format, "nature_surfur")

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
            ).discover(max_depth=5)

            by_path = {project.path: project for project in projects}
            self.assertEqual(by_path[".worktrees/feature/02_Worktree"].classification, "ephemeral")
            self.assertEqual(by_path["[Athena]/bridge_jobs/job1/hub_project"].classification, "ephemeral")


if __name__ == "__main__":
    unittest.main()
