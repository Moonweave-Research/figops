import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import yaml

from hub_core.config_parser import validate_config
from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.schemas import list_tool_definitions
from tests._symlink import symlink_or_skip
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT
from themes.style_profiles import INTERNAL_RESISTANCE_PROFILE


def _snapshot_files(root: Path) -> dict[str, tuple[int, int]]:
    snapshot = {}
    if not root.exists():
        return snapshot
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [dirname for dirname in dirs if dirname != "__pycache__"]
        for filename in files:
            path = Path(current_root) / filename
            stat = path.stat()
            snapshot[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _legacy_style_config() -> str:
    return f"""
project: {{name: LegacyGraph}}
visual_style:
  target_format: {INTERNAL_STYLE_TARGET_FORMAT}
  font_scale: 1.2
  profile: {INTERNAL_RESISTANCE_PROFILE}
presets:
  custom_svg:
    target_format: science
    output_format: svg
figures:
  - id: FigLegacy
    output: figure.png
    preset: custom_svg
"""


class ProjectNormalizationMCPTest(unittest.TestCase):
    def _call(self, server: GraphHubMCPServer, tool_name: str, arguments: dict | None = None) -> dict:
        response = server.call_tool(tool_name, arguments or {})
        self.assertIn("structuredContent", response)
        self.assertEqual(json.loads(response["content"][0]["text"]), response["structuredContent"])
        return response["structuredContent"]

    def test_tool_definitions_include_project_normalization_tools(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}

        self.assertIn("figops.scaffold_project", definitions)
        self.assertIn("figops.normalize_project_structure", definitions)
        self.assertIn("project_root", definitions["figops.scaffold_project"]["inputSchema"]["required"])
        self.assertIn("project_name", definitions["figops.scaffold_project"]["inputSchema"]["required"])
        self.assertIn("project_path", definitions["figops.normalize_project_structure"]["inputSchema"]["required"])

    def test_normalize_uses_dry_run_flag_matching_other_write_tools(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}
        normalize_props = definitions["figops.normalize_project_structure"]["inputSchema"]["properties"]

        self.assertIn("dry_run", normalize_props)
        self.assertNotIn("plan_only", normalize_props)
        self.assertTrue(normalize_props["dry_run"]["default"])
        self.assertIn("default", normalize_props["dry_run"]["description"].lower())

    def test_scaffold_project_dry_run_is_side_effect_free(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "New_Project"
            before = _snapshot_files(Path(tmpdir))

            with unittest.mock.patch.dict(os.environ, {"GRAPH_HUB_CONVENTIONS_ADAPTER": ""}, clear=False):
                server = GraphHubMCPServer(research_root=Path(tmpdir))
                result = self._call(
                    server,
                    "figops.scaffold_project",
                    {
                        "project_name": "New Project",
                        "project_root": str(project_root),
                        "target_format": INTERNAL_STYLE_TARGET_FORMAT,
                        "dry_run": True,
                    },
                )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["is_dry_run"])
            self.assertEqual(_snapshot_files(Path(tmpdir)), before)
            self.assertIn("project_config.yaml", result["planned_paths"])
            self.assertIn("hub_scripts/analyze.R", result["planned_paths"])
            reasons = {entry["reason"] for entry in result["manifest"]["entries"]}
            self.assertIn("scaffold directory", reasons)
            self.assertIn("scaffold file", reasons)
            self.assertNotIn("ResearchOS scaffold directory", reasons)
            self.assertNotIn("ResearchOS scaffold file", reasons)
            for required_dir in (
                "raw",
                "work",
                "hub_scripts",
                "results/data",
                "results/figures",
                "results/final",
                "docs",
                "archive",
            ):
                self.assertIn(required_dir, result["planned_paths"])
            self.assertEqual(result["style_summary"]["target_format"], INTERNAL_STYLE_TARGET_FORMAT)
            self.assertEqual(result["manifest"]["operation"], "scaffold_project")

    def test_scaffold_project_surfur_conventions_preserve_researchos_reasons(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "New_Project"

            with unittest.mock.patch.dict(os.environ, {"GRAPH_HUB_CONVENTIONS_ADAPTER": "surfur"}, clear=False):
                server = GraphHubMCPServer(research_root=Path(tmpdir))
                result = self._call(
                    server,
                    "figops.scaffold_project",
                    {
                        "project_name": "New Project",
                        "project_root": str(project_root),
                        "dry_run": True,
                    },
                )

            reasons = {entry["reason"] for entry in result["manifest"]["entries"]}
            self.assertIn("ResearchOS scaffold directory", reasons)
            self.assertIn("ResearchOS scaffold file", reasons)

    def test_scaffold_project_rejects_project_root_outside_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            external_root = Path(tmpdir) / "outside" / "New_Project"
            server = GraphHubMCPServer(research_root=research_root)

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Blocked Project", "project_root": str(external_root), "dry_run": False},
            )

            self.assertEqual(result["status"], "error")
            self.assertIn("project_root must stay under", result["errors"][0])
            self.assertFalse(external_root.exists())

    def test_scaffold_project_apply_writes_template_and_valid_config(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Applied_Project"
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {
                    "project_name": "Applied Project",
                    "project_root": str(project_root),
                    "target_format": "science",
                    "dry_run": False,
                },
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["is_dry_run"])
            self.assertTrue((project_root / "project_config.yaml").is_file())
            for required_dir in (
                "raw",
                "work",
                "results/data",
                "results/figures",
                "results/final",
                "docs",
                "archive",
            ):
                self.assertTrue((project_root / required_dir).is_dir())
            self.assertTrue((project_root / "hub_scripts" / "analyze.R").is_file())
            self.assertTrue((project_root / "hub_scripts" / "project_context.py").is_file())
            self.assertTrue((project_root / "hub_scripts" / "plot.py").is_file())
            self.assertIn(
                "theme_font_tokens",
                (project_root / "hub_scripts" / "project_context.py").read_text(encoding="utf-8"),
            )
            config = yaml.safe_load((project_root / "project_config.yaml").read_text(encoding="utf-8"))
            self.assertEqual(config["project"]["name"], "Applied Project")
            self.assertEqual(config["visual_style"]["target_format"], "science")
            self.assertEqual(validate_config(config), [])
            self.assertTrue(any(path.endswith("project_config.yaml") for path in result["created_paths"]))
            self.assertEqual(result["manifest"]["operation"], "scaffold_project")
            self.assertTrue(all(entry["status"] == "created" for entry in result["manifest"]["entries"]))

    def test_scaffold_project_refuses_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Existing_Project"
            project_root.mkdir(parents=True)
            (project_root / "project_config.yaml").write_text("project: {name: existing}\n", encoding="utf-8")
            before = _snapshot_files(project_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {
                    "project_name": "Existing Project",
                    "project_root": str(project_root),
                    "dry_run": False,
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("already exists", result["errors"][0])
            self.assertEqual(_snapshot_files(project_root), before)

    def test_scaffold_project_refuses_existing_manifest_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Existing_Project"
            project_root.mkdir(parents=True)
            manifest_path = project_root / ".figops_scaffold_manifest.json"
            manifest_path.write_text('{"existing": true}\n', encoding="utf-8")
            before = _snapshot_files(project_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Existing Project", "project_root": str(project_root), "dry_run": False},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn(".figops_scaffold_manifest.json", result["errors"][0])
            self.assertEqual(_snapshot_files(project_root), before)

    def test_scaffold_project_refuses_directory_blocker_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Blocked_Project"
            project_root.mkdir(parents=True)
            (project_root / "hub_scripts").write_text("not a directory\n", encoding="utf-8")
            before = _snapshot_files(project_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Blocked Project", "project_root": str(project_root), "dry_run": False},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("hub_scripts", result["errors"][0])
            self.assertEqual(_snapshot_files(project_root), before)

    def test_scaffold_project_refuses_directory_parent_blocker_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Blocked_Project"
            project_root.mkdir(parents=True)
            (project_root / "results").write_text("not a directory\n", encoding="utf-8")
            before = _snapshot_files(project_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Blocked Project", "project_root": str(project_root), "dry_run": False},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("results", result["errors"][0])
            self.assertFalse((project_root / "data").is_dir())
            self.assertFalse((project_root / "hub_scripts").exists())
            self.assertEqual(_snapshot_files(project_root), before)

    def test_scaffold_project_refuses_file_destination_directory_even_with_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Blocked_Project"
            (project_root / "project_config.yaml").mkdir(parents=True)
            (project_root / "project_config.yaml" / "sentinel").write_text("keep\n", encoding="utf-8")
            before = _snapshot_files(project_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {
                    "project_name": "Blocked Project",
                    "project_root": str(project_root),
                    "dry_run": False,
                    "overwrite": True,
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("project_config.yaml", result["errors"][0])
            self.assertFalse((project_root / "raw").exists())
            self.assertEqual(_snapshot_files(project_root), before)

    def test_scaffold_project_refuses_symlinked_scaffold_directory(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project_root = Path(tmpdir) / "ResearchOS" / "Blocked_Project"
            target_dir = Path(tmpdir) / "outside_raw"
            target_dir.mkdir(parents=True)
            project_root.mkdir(parents=True)
            symlink_or_skip(project_root / "raw", target_dir, target_is_directory=True)
            before = _snapshot_files(project_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Blocked Project", "project_root": str(project_root), "dry_run": False},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("raw", result["errors"][0])
            self.assertFalse((project_root / "project_config.yaml").exists())
            self.assertEqual(_snapshot_files(project_root), before)

    def test_scaffold_project_allows_internal_symlinked_project_root_boundary(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            actual_root = Path(tmpdir) / "Actual_Project"
            actual_root.mkdir()
            symlink_root = Path(tmpdir) / "Project_Link"
            symlink_or_skip(symlink_root, actual_root, target_is_directory=True)
            before_actual = _snapshot_files(actual_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Blocked Project", "project_root": str(symlink_root), "dry_run": False},
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["manual_review_needed"])
            self.assertEqual(result["errors"], [])
            self.assertTrue((actual_root / "project_config.yaml").exists())
            self.assertNotEqual(_snapshot_files(actual_root), before_actual)

    def test_scaffold_project_allows_project_root_under_internal_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            actual_parent = Path(tmpdir) / "Actual_Projects"
            actual_parent.mkdir()
            symlink_parent = Path(tmpdir) / "Projects_Link"
            symlink_or_skip(symlink_parent, actual_parent, target_is_directory=True)
            before_actual = _snapshot_files(actual_parent)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.scaffold_project",
                {
                    "project_name": "Blocked Project",
                    "project_root": str(symlink_parent / "Blocked_Project"),
                    "dry_run": False,
                },
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["manual_review_needed"])
            self.assertEqual(result["errors"], [])
            self.assertTrue((actual_parent / "Blocked_Project" / "project_config.yaml").exists())
            self.assertNotEqual(_snapshot_files(actual_parent), before_actual)

    def test_scaffold_project_allows_symlink_alias_back_to_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            alias = research_root / "Alias"
            symlink_or_skip(alias, research_root, target_is_directory=True)
            server = GraphHubMCPServer(research_root=research_root)

            result = self._call(
                server,
                "figops.scaffold_project",
                {"project_name": "Blocked Project", "project_root": str(alias / "Blocked_Project"), "dry_run": False},
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["errors"], [])
            self.assertTrue((research_root / "Blocked_Project" / "project_config.yaml").exists())

    def test_normalize_project_structure_plan_is_side_effect_free_and_preserves_style(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "summary.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (project / "figure.png").write_bytes(b"fake")
            (project / "notes.md").write_text("# Notes\n", encoding="utf-8")
            (project / "project_config.yaml").write_text(_legacy_style_config(), encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": True, "include_raw": True, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["is_dry_run"])
            self.assertEqual(_snapshot_files(project), before)
            destinations = {entry["destination"] for entry in result["manifest"]["entries"]}
            self.assertIn("hub_scripts/plot.py", destinations)
            self.assertIn("hub_scripts/project_context.py", destinations)
            self.assertIn("raw/summary.csv", destinations)
            self.assertIn("results/figures/figure.png", destinations)
            self.assertIn("docs/notes.md", destinations)
            self.assertEqual(result["style_summary"]["target_format"], INTERNAL_STYLE_TARGET_FORMAT)
            self.assertIn("custom_svg", result["style_summary"]["presets"])
            self.assertFalse(result["style_summary"]["style_update_applied"])

    def test_normalize_project_structure_rejects_project_path_outside_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            project = Path(tmpdir) / "outside" / "LegacyGraph"
            project.mkdir(parents=True)
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=research_root)

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False},
            )

            self.assertEqual(result["status"], "error")
            self.assertIn("project_path must stay under", result["errors"][0])
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_apply_copies_files_and_writes_manifest(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "summary.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "include_raw": True, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["is_dry_run"])
            self.assertTrue((project / "hub_scripts" / "plot.py").is_file())
            self.assertTrue((project / "raw" / "summary.csv").is_file())
            self.assertTrue((project / ".figops_normalization_manifest.json").is_file())
            manifest = json.loads((project / ".figops_normalization_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["operation"], "normalize_project_structure")
            self.assertTrue(any(entry["destination"] == "hub_scripts/plot.py" for entry in manifest["entries"]))
            self.assertTrue(
                any(path.endswith(".figops_normalization_manifest.json") for path in result["created_paths"])
            )

    def test_normalize_project_structure_preserves_legacy_scripts_config(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            scripts = project / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "project_config.yaml").write_text(_legacy_style_config(), encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            planned = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": True, "move_policy": "copy"},
            )
            applied = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(planned["style_summary"]["target_format"], INTERNAL_STYLE_TARGET_FORMAT)
            self.assertIn("custom_svg", planned["style_summary"]["presets"])
            self.assertEqual(applied["status"], "warning")
            config = yaml.safe_load((project / "project_config.yaml").read_text(encoding="utf-8"))
            self.assertEqual(config["visual_style"]["target_format"], INTERNAL_STYLE_TARGET_FORMAT)
            self.assertEqual(config["visual_style"]["profile"], INTERNAL_RESISTANCE_PROFILE)
            self.assertIn("custom_svg", config["presets"])
            self.assertEqual(config["figures"][0]["preset"], "custom_svg")

    def test_normalize_project_structure_includes_nested_legacy_files(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "scripts").mkdir(parents=True)
            (project / "data").mkdir()
            (project / "docs").mkdir()
            (project / "scripts" / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "data" / "summary.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (project / "docs" / "notes.md").write_text("# Notes\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": True, "include_raw": True, "move_policy": "copy"},
            )

            destinations = {entry["destination"] for entry in result["manifest"]["entries"]}
            self.assertIn("hub_scripts/plot.py", destinations)
            self.assertIn("raw/summary.csv", destinations)
            self.assertIn("docs/notes.md", destinations)

    def test_normalize_project_structure_preserves_nested_relative_subpaths(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "scripts" / "prep").mkdir(parents=True)
            (project / "scripts" / "final").mkdir(parents=True)
            (project / "data" / "a").mkdir(parents=True)
            (project / "data" / "b").mkdir(parents=True)
            (project / "scripts" / "prep" / "plot.py").write_text("print('prep')\n", encoding="utf-8")
            (project / "scripts" / "final" / "plot.py").write_text("print('final')\n", encoding="utf-8")
            (project / "data" / "a" / "results.csv").write_text("x\n1\n", encoding="utf-8")
            (project / "data" / "b" / "results.csv").write_text("x\n2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": True, "include_raw": True, "move_policy": "copy"},
            )

            destinations = {entry["destination"] for entry in result["manifest"]["entries"]}
            self.assertIn("hub_scripts/prep/plot.py", destinations)
            self.assertIn("hub_scripts/final/plot.py", destinations)
            self.assertIn("raw/a/results.csv", destinations)
            self.assertIn("raw/b/results.csv", destinations)

    def test_normalize_project_structure_preserves_existing_result_tables(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "results" / "data").mkdir(parents=True)
            (project / "results" / "data" / "summary.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            planned = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": True, "include_raw": False, "move_policy": "copy"},
            )

            entries = {entry["source"]: entry for entry in planned["manifest"]["entries"]}
            self.assertIn("results/data/summary.csv", entries)
            self.assertEqual(entries["results/data/summary.csv"]["destination"], "results/data/summary.csv")
            self.assertEqual(entries["results/data/summary.csv"]["operation"], "copy")

    def test_normalize_project_structure_refuses_intra_manifest_destination_collision(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "scripts").mkdir(parents=True)
            (project / "plot.py").write_text("print('root')\n", encoding="utf-8")
            (project / "scripts" / "plot.py").write_text("print('scripts')\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("hub_scripts/plot.py", result["errors"][0])
            self.assertFalse((project / "hub_scripts" / "plot.py").exists())
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_collision_even_with_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "scripts").mkdir(parents=True)
            (project / "plot.py").write_text("print('root')\n", encoding="utf-8")
            (project / "scripts" / "plot.py").write_text("print('scripts')\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "move", "overwrite": True},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("hub_scripts/plot.py", result["errors"][0])
            self.assertTrue((project / "plot.py").is_file())
            self.assertTrue((project / "scripts" / "plot.py").is_file())
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_mixed_normalized_collision_with_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "hub_scripts").mkdir(parents=True)
            (project / "plot.py").write_text("print('legacy')\n", encoding="utf-8")
            (project / "hub_scripts" / "plot.py").write_text("print('normalized')\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy", "overwrite": True},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("hub_scripts/plot.py", result["errors"][0])
            self.assertEqual((project / "hub_scripts" / "plot.py").read_text(encoding="utf-8"), "print('normalized')\n")
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_keeps_raw_source_when_move_policy_selected(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            raw_source = project / "summary.csv"
            raw_source.write_text("x,y\n1,2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            planned = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": True, "include_raw": True, "move_policy": "move"},
            )
            applied = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "include_raw": True, "move_policy": "move"},
            )

            raw_entry = next(
                entry for entry in planned["manifest"]["entries"] if entry["destination"] == "raw/summary.csv"
            )
            self.assertEqual(raw_entry["operation"], "copy")
            self.assertIn(applied["status"], {"ok", "warning"})
            self.assertTrue(raw_source.is_file())
            self.assertEqual(raw_source.read_text(encoding="utf-8"), "x,y\n1,2\n")
            self.assertEqual((project / "raw" / "summary.csv").read_text(encoding="utf-8"), "x,y\n1,2\n")

    def test_normalize_project_structure_symlink_overwrite_replaces_existing_target(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "hub_scripts").mkdir(parents=True)
            (project / "plot.py").write_text("print('new')\n", encoding="utf-8")
            symlink_or_skip(project / "hub_scripts" / "plot.py", project / "missing_plot.py")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "symlink", "overwrite": True},
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertTrue((project / "hub_scripts" / "plot.py").is_symlink())
            self.assertEqual((project / "hub_scripts" / "plot.py").resolve(), (project / "plot.py").resolve())

    def test_normalize_project_structure_copy_overwrite_replaces_symlink_not_target(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "hub_scripts").mkdir(parents=True)
            (project / "plot.py").write_text("print('new')\n", encoding="utf-8")
            symlink_or_skip(project / "hub_scripts" / "plot.py", project / "missing_target.py")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy", "overwrite": True},
            )

            destination = project / "hub_scripts" / "plot.py"
            self.assertIn(result["status"], {"ok", "warning"})
            self.assertFalse(destination.is_symlink())
            self.assertEqual(destination.read_text(encoding="utf-8"), "print('new')\n")

    def test_normalize_project_structure_apply_warns_when_config_remains_invalid(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "project_config.yaml").write_text(
                """
project: {}
visual_style:
  target_format: not_a_style
""",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(result["validation"]["checked"])
            self.assertFalse(result["validation"]["valid"])
            self.assertTrue(result["validation"]["errors"])

    def test_normalize_project_structure_warns_for_non_mapping_config(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "project_config.yaml").write_text("- item\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(result["validation"]["checked"])
            self.assertFalse(result["validation"]["valid"])
            self.assertIn("Config root must be a YAML mapping/object.", result["validation"]["errors"])

    def test_normalize_project_structure_refuses_existing_destination_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            (project / "hub_scripts").mkdir(parents=True)
            (project / "plot.py").write_text("print('new')\n", encoding="utf-8")
            (project / "hub_scripts" / "plot.py").write_text("print('existing')\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("already exists", result["errors"][0])
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_existing_manifest_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            manifest_path = project / ".figops_normalization_manifest.json"
            manifest_path.write_text('{"existing": true}\n', encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn(".figops_normalization_manifest.json", result["errors"][0])
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_manifest_directory_even_with_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            manifest_path = project / ".figops_normalization_manifest.json"
            manifest_path.mkdir()
            (manifest_path / "sentinel").write_text("keep\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy", "overwrite": True},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn(".figops_normalization_manifest.json", result["errors"][0])
            self.assertFalse((project / "hub_scripts" / "plot.py").exists())
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_parent_file_blocker_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "a.py").write_text("print('a')\n", encoding="utf-8")
            (project / "docs").write_text("not a directory\n", encoding="utf-8")
            (project / "notes.md").write_text("# Notes\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("docs", result["errors"][0])
            self.assertFalse((project / "hub_scripts" / "a.py").exists())
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_file_destination_directory_even_with_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "a.py").write_text("print('a')\n", encoding="utf-8")
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "hub_scripts" / "plot.py").mkdir(parents=True)
            (project / "hub_scripts" / "plot.py" / "sentinel").write_text("keep\n", encoding="utf-8")
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy", "overwrite": True},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("hub_scripts/plot.py", result["errors"][0])
            self.assertFalse((project / "hub_scripts" / "a.py").exists())
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_refuses_destination_parent_symlink(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            project = Path(tmpdir) / "LegacyGraph"
            project.mkdir()
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            (project / "alternate_scripts").mkdir()
            symlink_or_skip(project / "hub_scripts", project / "alternate_scripts", target_is_directory=True)
            before = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "copy", "overwrite": True},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("hub_scripts", result["errors"][0])
            self.assertFalse((project / "alternate_scripts" / "plot.py").exists())
            self.assertEqual(_snapshot_files(project), before)

    def test_normalize_project_structure_allows_internal_symlinked_project_root_boundary(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            actual_root = Path(tmpdir) / "LegacyGraph"
            actual_root.mkdir()
            (actual_root / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            symlink_root = Path(tmpdir) / "LegacyGraph_Link"
            symlink_or_skip(symlink_root, actual_root, target_is_directory=True)
            before_actual = _snapshot_files(actual_root)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(symlink_root), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["manual_review_needed"])
            self.assertEqual(result["errors"], [])
            self.assertTrue((actual_root / "hub_scripts" / "plot.py").exists())
            self.assertNotEqual(_snapshot_files(actual_root), before_actual)

    def test_normalize_project_structure_allows_project_root_under_internal_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            actual_parent = Path(tmpdir) / "Actual_Projects"
            project = actual_parent / "LegacyGraph"
            project.mkdir(parents=True)
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            symlink_parent = Path(tmpdir) / "Projects_Link"
            symlink_or_skip(symlink_parent, actual_parent, target_is_directory=True)
            before_project = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(symlink_parent / "LegacyGraph"), "dry_run": False, "move_policy": "copy"},
            )

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["manual_review_needed"])
            self.assertEqual(result["errors"], [])
            self.assertTrue((project / "hub_scripts" / "plot.py").exists())
            self.assertNotEqual(_snapshot_files(project), before_project)

    def test_normalize_project_structure_allows_symlink_alias_back_to_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            project = research_root / "LegacyGraph"
            project.mkdir(parents=True)
            (project / "plot.py").write_text("print('plot')\n", encoding="utf-8")
            alias = research_root / "Alias"
            symlink_or_skip(alias, research_root, target_is_directory=True)
            before_project = _snapshot_files(project)
            server = GraphHubMCPServer(research_root=research_root)

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(alias / "LegacyGraph"), "dry_run": False},
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["errors"], [])
            self.assertTrue((project / "hub_scripts" / "plot.py").exists())
            self.assertNotEqual(_snapshot_files(project), before_project)

    def test_normalize_project_structure_rejects_symlink_source_escaping_project(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_norm_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            project = research_root / "LegacyGraph"
            project.mkdir(parents=True)
            external = Path(tmpdir) / "outside.py"
            external.write_text("print('outside')\n", encoding="utf-8")
            symlink_or_skip(project / "plot.py", external)
            server = GraphHubMCPServer(research_root=research_root)

            result = self._call(
                server,
                "figops.normalize_project_structure",
                {"project_path": str(project), "dry_run": False, "move_policy": "symlink"},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("symlink source must stay inside the project root", result["errors"][0])
            self.assertFalse((project / "hub_scripts" / "plot.py").exists())


if __name__ == "__main__":
    unittest.main()
