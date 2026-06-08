import csv
import json
import os
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from hub_core.mcp_surface import GraphHubMCPServer, _handle_json_rpc, list_tool_definitions


class _CompletedRenderProcess:
    exitcode = 0

    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True

    def join(self, _timeout=None):
        return None

    def is_alive(self):
        return False


class _DelayedRenderQueue:
    def __init__(self, *args, **kwargs):
        self.blocking_get_timeout = None

    def get_nowait(self):
        raise queue.Empty

    def get(self, timeout=None):
        self.blocking_get_timeout = timeout
        return {"status": "ok"}


def _sleeping_render_worker(_spec_payload, _result_queue):
    time.sleep(1)


def _path_leaking_render_worker(spec_payload, result_queue):
    result_queue.put({"status": "error", "error": f"failed at {spec_payload['output_path']}"})


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["x", "y"])
        writer.writeheader()
        writer.writerows([{"x": 0, "y": 1}, {"x": 1, "y": 2}, {"x": 2, "y": 3}])
    return path


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    snapshot = {}
    for current_root, _dirs, files in os.walk(root):
        for filename in files:
            path = Path(current_root) / filename
            stat = path.stat()
            snapshot[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class RenderCSVGraphMCPTest(unittest.TestCase):
    def _call(self, server: GraphHubMCPServer, tool_name: str, arguments: dict | None = None) -> dict:
        response = server.call_tool(tool_name, arguments or {})
        self.assertIn("structuredContent", response)
        self.assertEqual(json.loads(response["content"][0]["text"]), response["structuredContent"])
        return response["structuredContent"]

    def test_tool_definitions_include_controlled_rendering_tools(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}
        names = set(definitions)

        self.assertIn("graphhub.render_csv_graph", names)
        self.assertIn("graphhub.collect_artifacts", names)
        for tool_name in ("graphhub.render_csv_graph", "graphhub.collect_artifacts"):
            properties = definitions[tool_name]["outputSchema"]["properties"]
            self.assertIn("failure_stage", properties)
            self.assertIn("resolution_hint", properties)
            self.assertIn("manifest_path", properties)
            self.assertIn("status_path", properties)
            self.assertIn("latest_alias", properties)
            self.assertIn("latest_dir", properties)

    def test_default_runtime_root_preview_does_not_create_directory(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"

            with patch("hub_core.mcp_surface.preview_runtime_root", return_value=str(runtime_root)):
                server = GraphHubMCPServer()

            self.assertEqual(server.runtime_root, runtime_root.resolve())
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_activates_shared_runtime_resolver_for_write(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            preview_root = Path(tmpdir) / "preview"
            runtime_root = Path(tmpdir) / "runtime"

            with (
                patch("hub_core.mcp_surface.preview_runtime_root", return_value=str(preview_root)),
                patch("hub_core.mcp_surface.resolve_runtime_root", return_value=str(runtime_root)),
            ):
                server = GraphHubMCPServer()
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "runtime-demo"},
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertFalse(preview_root.exists())

    def test_collect_artifacts_after_restart_uses_shared_runtime_resolver(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            preview_root = Path(tmpdir) / "preview"
            runtime_root = Path(tmpdir) / "runtime"

            with (
                patch("hub_core.mcp_surface.preview_runtime_root", return_value=str(preview_root)),
                patch("hub_core.mcp_surface.resolve_runtime_root", return_value=str(runtime_root)),
                patch("hub_core.mcp_surface.runtime_root_lookup_candidates", return_value=[str(runtime_root)]),
            ):
                render_server = GraphHubMCPServer()
                rendered = self._call(
                    render_server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "restart-demo"},
                )
                collect_server = GraphHubMCPServer()
                collected = self._call(collect_server, "graphhub.collect_artifacts", {"job_id": "restart-demo"})

            self.assertIn(rendered["status"], {"ok", "warning"})
            self.assertIn(collected["status"], {"ok", "warning"})
            self.assertTrue(Path(collected["provenance"]["manifest_path"]).is_file())
            self.assertTrue(str(Path(collected["provenance"]["manifest_path"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertFalse(preview_root.exists())

    def test_render_csv_graph_creates_job_only_under_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_csv(tmp_root / "input" / "data.csv")
            runtime_root = tmp_root / "runtime"
            source_snapshot = _snapshot_tree(tmp_root / "input")

            server = GraphHubMCPServer(runtime_root=runtime_root)
            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "target_format": "nature_surfur",
                    "profile": "baseline",
                    "output_format": "png",
                    "semantic_checks": {"y": {"range": [0, 3], "allow_null": False}},
                    "job_id": "render-demo",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(result["job_id"], "render-demo")
            self.assertTrue(Path(result["output_path"]).is_file())
            self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertTrue(Path(result["config_path"]).is_file())
            self.assertTrue(Path(result["manifest_path"]).is_file())
            self.assertEqual(result["failure_stage"], "")
            self.assertEqual(result["resolution_hint"], "")
            self.assertTrue(Path(result["status_path"]).is_file())
            self.assertTrue(Path(result["latest_dir"]).is_dir())
            self.assertEqual(result["latest_alias"], result["latest_dir"])
            self.assertTrue((Path(result["latest_dir"]) / "manifest.json").is_file())
            self.assertTrue((Path(result["latest_dir"]) / "status.json").is_file())
            self.assertEqual(_snapshot_tree(tmp_root / "input"), source_snapshot)
            self.assertFalse((tmp_root / "input" / "project_config.yaml").exists())
            self.assertTrue(any(path.endswith("project_config.yaml") for path in result["created_paths"]))
            self.assertTrue(any(path.endswith("graph.png") for path in result["created_paths"]))
            self.assertTrue(any(path.endswith("status.json") for path in result["created_paths"]))

            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["job_id"], "render-demo")
            self.assertEqual(manifest["status_path"], result["status_path"])
            self.assertEqual(manifest["latest_dir"], result["latest_dir"])
            self.assertEqual(manifest["latest_alias"], result["latest_alias"])
            self.assertEqual(status["job_id"], "render-demo")
            self.assertEqual(status["status"], result["status"])
            self.assertEqual(status["failure_stage"], "")
            self.assertEqual(manifest["style_summary"]["target_format"], "nature_surfur")
            self.assertEqual(manifest["visual_preflight_status"]["passed"], True)
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(csv_check["required_columns"], ["x", "y"])
            self.assertEqual(csv_check["semantic_checks"], {"y": {"range": [0, 3], "allow_null": False}})

    def test_collect_artifacts_returns_manifest_metadata(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_csv(tmp_root / "input" / "data.csv")
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)
            self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "job_id": "artifact-demo",
                },
            )

            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "artifact-demo"})

            self.assertIn(collected["status"], {"ok", "warning"})
            self.assertEqual(collected["job_id"], "artifact-demo")
            self.assertEqual(collected["provenance"]["job_id"], "artifact-demo")
            self.assertEqual(len(collected["figures"]), 1)
            self.assertTrue(Path(collected["figures"][0]["path"]).is_file())
            self.assertTrue(any(path.endswith("graph.png") for path in collected["created_paths"]))
            self.assertTrue(Path(collected["provenance"]["manifest_path"]).is_file())
            self.assertTrue(Path(collected["provenance"]["status_path"]).is_file())
            self.assertTrue(Path(collected["provenance"]["latest_dir"]).is_dir())
            self.assertEqual(collected["provenance"]["latest_alias"], collected["provenance"]["latest_dir"])
            self.assertEqual(collected["manifest_path"], collected["provenance"]["manifest_path"])
            self.assertEqual(collected["status_path"], collected["provenance"]["status_path"])
            self.assertEqual(collected["latest_dir"], collected["provenance"]["latest_dir"])
            self.assertEqual(collected["latest_alias"], collected["provenance"]["latest_alias"])
            self.assertEqual(collected["visual_preflight_status"]["passed"], True)

    def test_render_csv_graph_rejects_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")
            args = {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "same-job"}
            first = self._call(server, "graphhub.render_csv_graph", args)
            second = self._call(server, "graphhub.render_csv_graph", args)

            self.assertIn(first["status"], {"ok", "warning"})
            self.assertEqual(second["status"], "error")
            self.assertEqual(second["failure_stage"], "EXPORT")
            self.assertIn("overwrite=true", second["resolution_hint"])
            self.assertTrue(second["manual_review_needed"])
            self.assertIn("already exists", second["errors"][0])
            self.assertNotIn(str(Path(tmpdir).resolve()), second["errors"][0])
            self.assertIn("runtime://mcp_jobs/same-job", second["errors"][0])

    def test_render_csv_graph_rejects_unknown_profile(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "profile": "typo-profile"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("profile", result["resolution_hint"])
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("Invalid profile", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_unknown_plot_type_without_writing_job(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "plot_type": "scater"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("plot_type", result["resolution_hint"])
            self.assertIn("plot_type", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_large_csv_before_copying(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "large.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with patch("hub_core.mcp_surface.MCP_RENDER_CSV_MAX_BYTES", 4):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("CSV", result["resolution_hint"])
            self.assertIn("exceeds", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_missing_input_error_does_not_expose_absolute_path(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            missing_path = Path(tmpdir) / "private" / "missing.csv"
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(missing_path), "x_column": "x", "y_column": "y"},
            )

            serialized = json.dumps(result, sort_keys=True)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("data_path", result["resolution_hint"])
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("data_path is not a file", result["errors"][0])
            self.assertNotIn(str(missing_path), serialized)

    def test_render_csv_graph_uses_csv_size_limit_from_environment(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "small.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with patch.dict(os.environ, {"GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES": "4"}, clear=False):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertEqual(result["status"], "error")
            self.assertIn("exceeds", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_ignores_invalid_csv_size_limit_environment(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            with patch.dict(os.environ, {"GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES": "not-an-int"}, clear=False):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertIn(result["status"], {"ok", "warning"})

    def test_render_csv_graph_records_pdf_companion_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "output_format": "pdf",
                    "job_id": "pdf-demo",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            figure_paths = {Path(figure["path"]).name for figure in manifest["figures"]}
            self.assertEqual(figure_paths, {"graph.pdf", "graph.png"})
            self.assertTrue(all(Path(figure["path"]).is_file() for figure in manifest["figures"]))
            self.assertTrue(any(path.endswith("graph.pdf") for path in manifest["created_paths"]))
            self.assertTrue(any(path.endswith("graph.png") for path in manifest["created_paths"]))
            self.assertEqual(len(result["artifact_resources"]), 2)

    def test_render_csv_graph_preflight_warnings_require_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            with patch(
                "hub_core.mcp_surface.validate_figure_preflight",
                return_value={"passed": True, "checks": [], "warnings": ["width exceeds journal max"]},
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "warning-demo"},
                )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertEqual(result["warnings"], ["width exceeds journal max"])

    def test_render_csv_graph_grouped_cv_warning_requires_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "data.csv"
            data_path.parent.mkdir(parents=True)
            with data_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["x", "y", "condition"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"x": 0, "y": 10, "condition": "A"},
                        {"x": 1, "y": 10, "condition": "A"},
                        {"x": 2, "y": 1, "condition": "B"},
                        {"x": 3, "y": 100, "condition": "B"},
                    ]
                )
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with patch(
                "hub_core.mcp_surface.validate_figure_preflight",
                return_value={"passed": True, "checks": [], "warnings": []},
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "semantic_checks": {
                            "y": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                        },
                        "job_id": "grouped-cv-warning",
                    },
                )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(any("grouped_cv" in warning for warning in result["warnings"]))
            self.assertIn("calculation_checks", result)
            self.assertFalse(result["calculation_checks"]["quality_passed"])
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
            for payload in (manifest, status):
                self.assertIn("calculation_checks", payload)
                self.assertFalse(payload["calculation_checks"]["quality_passed"])
                self.assertTrue(payload["calculation_checks"]["manual_review_needed"])
                self.assertEqual(payload["calculation_checks"]["checks"][0]["name"], "grouped_cv")

    def test_render_csv_graph_dry_run_grouped_cv_warning_requires_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "data.csv"
            data_path.parent.mkdir(parents=True)
            with data_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["x", "y", "condition"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"x": 0, "y": 10, "condition": "A"},
                        {"x": 1, "y": 10, "condition": "A"},
                        {"x": 2, "y": 1, "condition": "B"},
                        {"x": 3, "y": 100, "condition": "B"},
                    ]
                )
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "semantic_checks": {
                        "y": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}
                    },
                    "job_id": "grouped-cv-dry-run",
                    "dry_run": True,
                },
            )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(result["is_dry_run"])
            self.assertIn("calculation_checks", result)
            self.assertTrue(any("grouped_cv" in warning for warning in result["warnings"]))
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_prefetches_input_before_reading_or_copying(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            with patch("hub_core.mcp_surface.ensure_local_files") as ensure_local:
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertIn(result["status"], {"ok", "warning"})
            ensure_local.assert_called_once_with([str(data_path)])

    def test_render_csv_graph_timeout_returns_execution_error(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with (
                patch("hub_core.mcp_surface.MCP_RENDER_TIMEOUT_SECONDS", 0.05),
                patch("hub_core.mcp_surface._render_bridge_figure_worker", _sleeping_render_worker),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "timeout-demo"},
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "TIMEOUT")
            self.assertIn("timeout", result["resolution_hint"].lower())
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("timed out", result["errors"][0])
            self.assertTrue(str(Path(result["job_root"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertTrue(Path(result["manifest_path"]).is_file())
            self.assertTrue(Path(result["status_path"]).is_file())
            self.assertTrue(Path(result["latest_dir"]).is_dir())
            self.assertEqual(result["latest_alias"], result["latest_dir"])

    def test_render_csv_graph_execution_error_sanitizes_runtime_path(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with patch("hub_core.mcp_surface._render_bridge_figure_worker", _path_leaking_render_worker):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "path-demo"},
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "PLOT")
            self.assertIn("render", result["resolution_hint"].lower())
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("runtime://mcp_jobs/path-demo/results/figures/graph.png", result["errors"][0])
            self.assertNotIn(str(runtime_root.resolve()), result["errors"][0])
            self.assertTrue(Path(result["manifest_path"]).is_file())
            self.assertTrue(Path(result["status_path"]).is_file())
            self.assertTrue(Path(result["latest_dir"]).is_dir())
            self.assertEqual(result["latest_alias"], result["latest_dir"])
            self.assertTrue((Path(result["latest_dir"]) / "manifest.json").is_file())
            self.assertTrue((Path(result["latest_dir"]) / "status.json").is_file())
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["failure_stage"], "PLOT")
            self.assertEqual(manifest["resolution_hint"], result["resolution_hint"])
            self.assertEqual(manifest["status_path"], result["status_path"])
            self.assertEqual(manifest["latest_dir"], result["latest_dir"])
            self.assertEqual(manifest["latest_alias"], result["latest_alias"])
            self.assertEqual(status["status"], "error")
            self.assertEqual(status["failure_stage"], "PLOT")

            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "path-demo"})
            self.assertEqual(collected["status"], "error")
            self.assertEqual(collected["artifact_status"], "failed")
            self.assertEqual(collected["failure_stage"], "PLOT")
            self.assertEqual(collected["resolution_hint"], result["resolution_hint"])
            self.assertEqual(collected["manifest_path"], result["manifest_path"])
            self.assertEqual(collected["status_path"], result["status_path"])
            self.assertEqual(collected["latest_alias"], result["latest_alias"])

    def test_render_csv_graph_failure_manifest_preserves_requested_baseline_state(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            baseline_path = Path(tmpdir) / "baseline" / "graph.png"
            baseline_path.parent.mkdir()
            baseline_path.write_bytes(b"not-a-real-png")
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with patch("hub_core.mcp_surface._render_bridge_figure_worker", _path_leaking_render_worker):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "job_id": "baseline-failure-demo",
                        "baseline_path": str(baseline_path),
                    },
                )

            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertTrue(result["baseline_comparison"]["checked"])
            self.assertEqual(manifest["baseline_comparison"], result["baseline_comparison"])

            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "baseline-failure-demo"})
            self.assertEqual(collected["baseline_comparison"], result["baseline_comparison"])

    def test_render_worker_uses_blocking_queue_read_after_process_exit(self):
        delayed_queue = _DelayedRenderQueue()

        with (
            patch("hub_core.mcp_surface.multiprocessing.Queue", return_value=delayed_queue),
            patch("hub_core.mcp_surface.multiprocessing.Process", _CompletedRenderProcess),
        ):
            GraphHubMCPServer._run_render_bridge_figure({"csv_path": "input.csv", "output_path": "graph.png"})

        self.assertIsNotNone(delayed_queue.blocking_get_timeout)

    def test_render_csv_graph_data_contract_error_sanitizes_source_path(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "outside" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            with patch(
                "hub_core.mcp_surface._read_data_safe",
                side_effect=OSError(f"cannot read {data_path.resolve()}"),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "contract-path"},
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("data contract", result["resolution_hint"].lower())
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("input://data_path", result["errors"][0])
            self.assertNotIn(str(data_path.resolve()), result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_json_rpc_missing_required_render_argument_returns_protocol_error(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "graphhub.render_csv_graph", "arguments": {"x_column": "x", "y_column": "y"}},
            },
        )

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("data_path", response["error"]["message"])

    def test_json_rpc_schema_invalid_optional_argument_returns_protocol_error(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "graphhub.render_csv_graph",
                    "arguments": {
                        "data_path": "/tmp/input.csv",
                        "x_column": "x",
                        "y_column": "y",
                        "overwrite": "false",
                    },
                },
            },
        )

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("overwrite", response["error"]["message"])
        self.assertNotIn("result", response)

    def test_json_rpc_render_accepts_label_arguments_declared_in_schema(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            response = _handle_json_rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 13,
                    "method": "tools/call",
                    "params": {
                        "name": "graphhub.render_csv_graph",
                        "arguments": {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "y",
                            "title": "Custom title",
                            "x_axis_label": "Custom x",
                            "y_axis_label": "Custom y",
                            "job_id": "label-demo",
                        },
                    },
                },
            )

            self.assertNotIn("error", response)
            self.assertIn(response["result"]["structuredContent"]["status"], {"ok", "warning"})

    def test_render_csv_graph_rejects_semantic_contract_violations_without_writing_job(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "semantic_checks": {"y": {"range": [0, 2]}},
                    "job_id": "semantic-demo",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("semantic_checks", result["resolution_hint"])
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("out of range", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_non_object_semantic_checks(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "semantic_checks": []},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("semantic_checks", result["resolution_hint"])
            self.assertIn("semantic_checks must be an object", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_invalid_column_returns_execution_error(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "missing", "y_column": "y"},
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("missing", result["errors"][0])

    def test_render_csv_graph_preflight_failure_sets_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "output_format": "svg",
                    "job_id": "preflight-demo",
                },
            )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertFalse(result["visual_preflight_status"]["passed"])

            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "preflight-demo"})
            self.assertEqual(collected["status"], "warning")
            self.assertTrue(collected["manual_review_needed"])
            self.assertTrue(collected["warnings"])

    def test_collect_artifacts_missing_job_does_not_create_default_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"

            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)}, clear=False):
                server = GraphHubMCPServer()
                result = self._call(server, "graphhub.collect_artifacts", {"job_id": "missing-job"})

            self.assertEqual(result["status"], "error")
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_dry_run_does_not_create_job_directory(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "dry_run": True},
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["is_dry_run"])
            self.assertFalse((runtime_root / "mcp_jobs").exists())
            self.assertEqual(result["created_paths"], [])


if __name__ == "__main__":
    unittest.main()
