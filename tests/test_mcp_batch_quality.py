import csv
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.schemas import list_tool_definitions


def _sleeping_batch_discovery_worker(_root, _max_depth, _result_path):
    time.sleep(1)


def _large_batch_discovery_worker(_root, _max_depth, result_path):
    projects = [
        {
            "project_id": f"project-{index}",
            "name": f"Project {index}",
            "path": f"/tmp/research/project-{index}",
            "status": "valid",
        }
        for index in range(100_000)
    ]
    render_helpers._write_worker_result(result_path, {"status": "ok", "projects": projects})


def _oversized_batch_discovery_worker(_root, _max_depth, result_path):
    projects = [
        {
            "project_id": f"project-{index}",
            "name": f"Project {index}",
            "path": f"/tmp/research/project-{index}",
            "status": "valid",
            "metadata": f"{index}-" + ("x" * 1024),
        }
        for index in range(100_000)
    ]
    render_helpers._write_worker_result(result_path, {"status": "ok", "projects": projects})


VALID_CONFIG = """
project:
  name: "{name}"
visual_style:
  target_format: nature_surfur
  font_scale: 1.0
  profile: baseline
data_contract:
  csv_checks:
    - path: "results/data/summary.csv"
      required_columns: ["x", "y"]
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    output: results/figures/Fig1.png
"""

INVALID_CONFIG = """
project: {{}}
visual_style:
  target_format: unknown_style
"""


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["x", "y"])
        writer.writeheader()
        writer.writerows([{"x": 0, "y": 1}, {"x": 1, "y": 2}, {"x": 2, "y": 3}])
    return path


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


class BatchQualityMCPTest(unittest.TestCase):
    def _call(self, server: GraphHubMCPServer, tool_name: str, arguments: dict | None = None) -> dict:
        response = server.call_tool(tool_name, arguments or {})
        self.assertIn("structuredContent", response)
        self.assertEqual(json.loads(response["content"][0]["text"]), response["structuredContent"])
        return response["structuredContent"]

    def _write_project(self, root: Path, rel_path: str, *, config_text: str = VALID_CONFIG) -> Path:
        project = root / rel_path
        project.mkdir(parents=True, exist_ok=True)
        (project / "project_config.yaml").write_text(config_text.format(name=Path(rel_path).name), encoding="utf-8")
        return project

    def _write_legacy_project(self, root: Path, rel_path: str) -> Path:
        project = root / rel_path
        config_dir = project / "scripts"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "project_config.yaml").write_text(VALID_CONFIG.format(name=Path(rel_path).name), encoding="utf-8")
        return project

    def test_tool_definitions_include_batch_check(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}

        self.assertIn("graphhub.batch_check", definitions)
        schema = definitions["graphhub.batch_check"]["inputSchema"]
        self.assertIn("root", schema["properties"])
        self.assertIn("max_projects", schema["properties"])
        self.assertIn("dry_run", schema["properties"])
        self.assertIn("batch_id", schema["properties"])
        self.assertIn("resume_manifest_path", schema["properties"])
        self.assertIn("include_quarantine", schema["properties"])

    def test_render_csv_graph_reports_preflight_passed_artifact_status(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            with patch(
                "hub_core.mcp.tools.render_support.validate_figure_preflight",
                return_value={"passed": True, "checks": [{"name": "format", "passed": True}], "warnings": []},
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "quality-pass"},
                )

            self.assertEqual(result["artifact_status"], "preflight_passed")
            self.assertFalse(result["manual_review_needed"])
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_status"], "preflight_passed")

    def test_collect_artifacts_reports_manual_review_for_preflight_warning(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            with patch(
                "hub_core.mcp.tools.render_support.validate_figure_preflight",
                return_value={"passed": True, "checks": [], "warnings": ["width exceeds journal max"]},
            ):
                rendered = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "quality-review"},
                )
            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "quality-review"})

            self.assertEqual(rendered["artifact_status"], "manual_review_needed")
            self.assertEqual(collected["artifact_status"], "manual_review_needed")
            self.assertTrue(collected["manual_review_needed"])
            self.assertEqual(collected["warnings"], ["width exceeds journal max"])

    def test_collect_artifacts_can_compare_baseline_without_mutating_project(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            rendered = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "quality-baseline"},
            )
            baseline_path = Path(tmpdir) / "baseline" / "graph.png"
            baseline_path.parent.mkdir()
            shutil.copy2(rendered["output_path"], baseline_path)
            input_root = Path(tmpdir) / "input"
            source_snapshot = sorted(path.relative_to(input_root).as_posix() for path in input_root.rglob("*"))

            collected = self._call(
                server,
                "graphhub.collect_artifacts",
                {"job_id": "quality-baseline", "baseline_path": str(baseline_path)},
            )

            self.assertEqual(collected["artifact_status"], "baseline_matched")
            self.assertEqual(collected["baseline_comparison"]["status"], "baseline_matched")
            self.assertTrue(collected["baseline_comparison"]["matched"])
            self.assertEqual(
                sorted(path.relative_to(input_root).as_posix() for path in input_root.rglob("*")),
                source_snapshot,
            )

    def test_batch_check_dry_run_excludes_invalid_legacy_and_ephemeral_projects_by_default(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "01_Valid")
            self._write_project(root, "02_Invalid", config_text=INVALID_CONFIG)
            self._write_legacy_project(root, "03_Legacy")
            self._write_project(root, ".worktrees/feature/04_Worktree")
            self._write_project(root, "[Athena]/bridge_jobs/job-1/05_Bridge")
            self._write_project(root, "_archive/06_Archived")
            before = _snapshot_files(root)
            runtime_root = Path(tmpdir) / "runtime"
            with patch.dict(os.environ, {"GRAPH_HUB_CONVENTIONS_ADAPTER": "surfur"}, clear=False):
                server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
                result = self._call(
                    server,
                    "graphhub.batch_check",
                    {"root": str(root), "max_depth": 8, "dry_run": True},
                )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["is_dry_run"])
            self.assertEqual([item["project_root"] for item in result["checked_projects"]], ["01_Valid"])
            skipped = {item["project_root"]: item["reason"] for item in result["skipped_projects"]}
            self.assertEqual(skipped["02_Invalid"], "invalid_config")
            self.assertEqual(skipped["03_Legacy"], "legacy_project")
            self.assertEqual(skipped[".worktrees/feature/04_Worktree"], "ephemeral_project")
            self.assertEqual(skipped["[Athena]/bridge_jobs/job-1/05_Bridge"], "ephemeral_project")
            self.assertEqual(skipped["_archive/06_Archived"], "quarantine_project")
            self.assertEqual(_snapshot_files(root), before)
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_batch_check_can_include_quarantine_projects_explicitly(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "_archive/06_Archived")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.batch_check",
                {"root": str(root), "max_depth": 4, "dry_run": True, "include_quarantine": True},
            )

            self.assertEqual(
                [item["project_root"] for item in result["checked_projects"]],
                ["_archive/06_Archived"],
            )
            self.assertEqual(result["skipped_projects"], [])

    def test_batch_check_apply_writes_runtime_manifest_not_source_tree(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "01_Valid")
            before = _snapshot_files(root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.batch_check",
                {"root": str(root), "max_depth": 4, "dry_run": False, "batch_id": "batch-demo"},
            )

            manifest_path = Path(result["manifest_path"])
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["is_dry_run"])
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(str(manifest_path.resolve()).startswith(str(runtime_root.resolve())))
            self.assertIn(str(manifest_path), result["created_paths"])
            self.assertEqual(result["log_paths"], [str(manifest_path)])
            self.assertEqual(_snapshot_files(root), before)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["batch_id"], "batch-demo")
            self.assertEqual(manifest["checked_projects"][0]["project_root"], "01_Valid")

    def test_batch_check_resume_uses_prior_manifest(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "01_Valid")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            first = self._call(
                server,
                "graphhub.batch_check",
                {"root": str(root), "dry_run": False, "batch_id": "batch-first"},
            )

            resumed = self._call(
                server,
                "graphhub.batch_check",
                {
                    "root": str(root),
                    "dry_run": False,
                    "batch_id": "batch-resume",
                    "resume_manifest_path": first["manifest_path"],
                },
            )

            self.assertEqual(resumed["resumed_from"], first["manifest_path"])
            self.assertEqual(resumed["checked_projects"], [])
            self.assertEqual(resumed["skipped_projects"][0]["project_root"], "01_Valid")
            self.assertEqual(resumed["skipped_projects"][0]["reason"], "already_checked")

    def test_batch_check_rejects_resume_manifest_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            research_root = Path(tmpdir) / "research"
            runtime_root = Path(tmpdir) / "runtime"
            root = research_root / "ResearchOS"
            self._write_project(root, "01_Valid")
            outside_manifest = Path(tmpdir) / "escape" / "batch_manifest.json"
            outside_manifest.parent.mkdir(parents=True)
            outside_manifest.write_text(json.dumps({"root": str(root), "checked_projects": []}), encoding="utf-8")
            server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

            resumed = self._call(
                server,
                "graphhub.batch_check",
                {
                    "root": str(root),
                    "dry_run": False,
                    "batch_id": "batch-escape",
                    "resume_manifest_path": str(outside_manifest),
                },
            )

            self.assertEqual(resumed["status"], "error")
            self.assertTrue(resumed["manual_review_needed"])
            self.assertEqual(resumed["failure_stage"], "CONTRACT")
            self.assertIn("allowed data root", resumed["errors"][0])
            self.assertEqual(resumed["resumed_from"], "")
            self.assertEqual(resumed["checked_projects"], [])

    def test_batch_check_rejects_resume_manifest_from_different_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root_a = Path(tmpdir) / "ResearchOS_A"
            root_b = Path(tmpdir) / "ResearchOS_B"
            self._write_project(root_a, "01_Valid")
            self._write_project(root_b, "01_Valid")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            first = self._call(
                server,
                "graphhub.batch_check",
                {"root": str(root_a), "dry_run": False, "batch_id": "batch-root-a"},
            )

            resumed = self._call(
                server,
                "graphhub.batch_check",
                {
                    "root": str(root_b),
                    "dry_run": False,
                    "batch_id": "batch-root-b",
                    "resume_manifest_path": first["manifest_path"],
                },
            )

            self.assertEqual(resumed["status"], "error")
            self.assertTrue(resumed["manual_review_needed"])
            self.assertIn("different root", resumed["errors"][0])
            self.assertEqual(resumed["checked_projects"], [])

    def test_batch_check_timeout_returns_partial_manifest(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            for index in range(4):
                self._write_project(root, f"{index:02d}_Valid")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            with patch("hub_core.mcp.render_orchestration.MCP_BATCH_TIMEOUT_SECONDS", 0):
                result = self._call(
                    server,
                    "graphhub.batch_check",
                    {"root": str(root), "dry_run": False, "batch_id": "batch-timeout", "max_projects": 4},
                )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(any("timed out" in warning for warning in result["warnings"]))
            self.assertTrue(Path(result["manifest_path"]).is_file())

    def test_batch_check_timeout_bounds_project_discovery(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "01_Valid")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            started_at = time.monotonic()
            with (
                patch("hub_core.mcp.render_orchestration.MCP_BATCH_TIMEOUT_SECONDS", 0.05),
                patch("hub_core.mcp.render_orchestration._batch_discovery_worker", _sleeping_batch_discovery_worker),
            ):
                result = self._call(
                    server,
                    "graphhub.batch_check",
                    {"root": str(root), "dry_run": False, "batch_id": "batch-discovery-timeout"},
                )
            elapsed = time.monotonic() - started_at

            self.assertLess(elapsed, 0.8)
            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(any("timed out" in warning for warning in result["warnings"]))
            self.assertEqual(result["checked_projects"], [])
            self.assertTrue(Path(result["manifest_path"]).is_file())

    def test_batch_discovery_large_result_returns_without_queue_timeout(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            root.mkdir()

            started_at = time.monotonic()
            with patch(
                "hub_core.mcp.render_orchestration._batch_discovery_worker",
                _large_batch_discovery_worker,
            ):
                projects, timed_out, warnings = GraphHubMCPServer._discover_batch_projects(
                    root,
                    max_depth=1,
                    timeout_seconds=3.0,
                )
            elapsed = time.monotonic() - started_at

            self.assertLess(elapsed, 5.0)
            self.assertFalse(timed_out, warnings)
            self.assertEqual(warnings, [])
            self.assertEqual(len(projects), 100_000)

    def test_batch_discovery_oversized_result_reports_clear_transfer_error(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_batch_quality_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            root.mkdir()

            with patch(
                "hub_core.mcp.render_orchestration._batch_discovery_worker",
                _oversized_batch_discovery_worker,
            ):
                projects, timed_out, warnings = GraphHubMCPServer._discover_batch_projects(
                    root,
                    max_depth=1,
                    timeout_seconds=3.0,
                )

            self.assertFalse(projects, f"expected no projects, got {len(projects)}")
            self.assertTrue(timed_out)
            self.assertTrue(any("result too large" in warning.lower() for warning in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
