import contextlib
import csv
import json
import os
import tempfile
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.schemas import list_tool_definitions
from hub_core.mcp.transport import _handle_json_rpc


class _CompletedRenderProcess:
    def __init__(self, *args, **kwargs):
        self.exitcode = 0
        self.started = False
        self._target = kwargs["target"]
        self._args = kwargs["args"]

    def start(self):
        self.started = True
        self._target(*self._args)

    def join(self, _timeout=None):
        return None

    def is_alive(self):
        return False


def _sleeping_render_worker(_spec_payload, _result_path):
    time.sleep(1)


def _path_leaking_render_worker(spec_payload, result_path):
    render_helpers._write_worker_result(
        result_path,
        {"status": "error", "error": f"failed at {spec_payload['output_path']}"},
    )


def _successful_render_worker(_spec_payload, result_path):
    render_helpers._write_worker_result(result_path, {"status": "ok"})


def _successful_batch_discovery_worker(_root, _max_depth, result_path):
    render_helpers._write_worker_result(result_path, {"status": "ok", "projects": []})


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["x", "y"])
        writer.writeheader()
        writer.writerows([{"x": 0, "y": 1}, {"x": 1, "y": 2}, {"x": 2, "y": 3}])
    return path


def _write_grid_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["x", "y", "z"])
        writer.writeheader()
        writer.writerows([{"x": x, "y": y, "z": x + y} for y in (0, 1) for x in (0, 1)])
    return path


def _write_bar_error_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["condition", "value", "sem"])
        writer.writeheader()
        writer.writerows(
            [
                {"condition": "control", "value": 1.2, "sem": 0.1},
                {"condition": "treated", "value": 2.4, "sem": 0.2},
            ]
        )
    return path


def _write_project_render_fixture(root: Path, name: str = "01_Project") -> Path:
    project = root / name
    (project / "hub_scripts").mkdir(parents=True, exist_ok=True)
    (project / "results" / "data").mkdir(parents=True, exist_ok=True)
    (project / "raw").mkdir(parents=True, exist_ok=True)
    (project / "results" / "data" / "summary.csv").write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    (project / "raw" / "large-secret.bin").write_bytes(b"do-not-copy")
    (project / "hub_scripts" / "plot.py").write_text(
        "from pathlib import Path\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "Path('results/figures/Fig1.png').write_bytes(b'png')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        """
project:
  name: Project Render Fixture
visual_style:
  target_format: nature
  profile: baseline
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: ["x", "y"]
      dtypes: {x: float, y: float}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/Fig1.png
""",
        encoding="utf-8",
    )
    return project


def _write_project_save_journal_fixture(root: Path, name: str = "01_Project", break_engine: bool = False) -> Path:
    # Routes the figure through the real save_journal_fig chokepoint so the project
    # subprocess transport (GEOMETRY_DIAGNOSTICS_OUT/_DEADLINE) is exercised end-to-end.
    # When break_engine is set, the diagnostics engine is patched IN THE CHILD to raise
    # (a parent mock.patch cannot reach the spawned subprocess), driving the in-frame
    # degrade-to-passed:None path through a real render.
    project = root / name
    (project / "hub_scripts").mkdir(parents=True, exist_ok=True)
    (project / "results" / "data").mkdir(parents=True, exist_ok=True)
    (project / "raw").mkdir(parents=True, exist_ok=True)
    (project / "results" / "data" / "summary.csv").write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    (project / "raw" / "large-secret.bin").write_bytes(b"do-not-copy")
    break_block = (
        "import hub_core.geometry_diagnostics as _gd\n"
        "def _boom(*_args, **_kwargs):\n"
        "    raise RuntimeError('engine boom')\n"
        "_gd.diagnose_figure_geometry = _boom\n"
        if break_engine
        else ""
    )
    (project / "hub_scripts" / "plot.py").write_text(
        "import os\n"
        "import sys\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "from pathlib import Path\n"
        "hub_path = os.environ['RESEARCH_HUB_PATH']\n"
        "if hub_path not in sys.path:\n"
        "    sys.path.insert(0, hub_path)\n"
        f"{break_block}"
        "from themes.journal_theme import save_journal_fig\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([0, 1, 2], [0, 1, 2])\n"
        "save_journal_fig(fig, 'results/figures/Fig1.png')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        """
project:
  name: Project Render Fixture
visual_style:
  target_format: nature
  profile: baseline
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: ["x", "y"]
      dtypes: {x: float, y: float}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/Fig1.png
""",
        encoding="utf-8",
    )
    return project


def _write_project_legacy_context_fixture(root: Path, name: str = "01_Project") -> Path:
    project = root / name
    (project / "hub_scripts").mkdir(parents=True, exist_ok=True)
    (project / "results" / "data").mkdir(parents=True, exist_ok=True)
    (project / "results" / "data" / "summary.csv").write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    (project / "hub_scripts" / "project_context.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "\n"
        "def get_project_root() -> Path:\n"
        "    return Path(__file__).resolve().parents[1]\n"
        "\n"
        "def setup_hub_path() -> Path:\n"
        "    project_root = get_project_root()\n"
        "    hub_path = project_root.parents[1] / '[Graph_making_hub]'\n"
        "    if str(hub_path) not in sys.path:\n"
        "        sys.path.insert(0, str(hub_path))\n"
        "    return hub_path\n",
        encoding="utf-8",
    )
    (project / "hub_scripts" / "plot.py").write_text(
        "from pathlib import Path\n"
        "from project_context import setup_hub_path\n"
        "\n"
        "setup_hub_path()\n"
        "from themes.style_profiles import DEFAULT_PROFILE\n"
        "\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "Path('results/figures/Fig1.png').write_bytes(DEFAULT_PROFILE.encode('utf-8'))\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        """
project:
  name: Legacy Project Context Fixture
visual_style:
  target_format: nature
  profile: baseline
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: ["x", "y"]
      dtypes: {x: float, y: float}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/Fig1.png
""",
        encoding="utf-8",
    )
    return project


def _copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        destination = target / rel
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    snapshot = {}
    for current_root, _dirs, files in os.walk(root):
        for filename in files:
            path = Path(current_root) / filename
            stat = path.stat()
            snapshot[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


@contextlib.contextmanager
def _without_runtime_root_env():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RESEARCH_HUB_RUNTIME_ROOT", None)
        os.environ.pop("RESEARCH_HUB_RUNTIME_HOME", None)
        yield


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
        self.assertIn("graphhub.render_project_figure", names)
        self.assertIn("graphhub.collect_artifacts", names)
        for tool_name in ("graphhub.render_csv_graph", "graphhub.render_project_figure", "graphhub.collect_artifacts"):
            properties = definitions[tool_name]["outputSchema"]["properties"]
            self.assertIn("failure_stage", properties)
            self.assertIn("resolution_hint", properties)
            self.assertIn("manifest_path", properties)
            self.assertIn("status_path", properties)
            self.assertIn("latest_alias", properties)
            self.assertIn("latest_dir", properties)
            self.assertIn("layout_report", properties)
        project_input = definitions["graphhub.render_project_figure"]["inputSchema"]["properties"]
        project_output = definitions["graphhub.render_project_figure"]["outputSchema"]["properties"]
        self.assertIn("project_id", project_input)
        self.assertIn("project_path", project_input)
        self.assertIn("figure_id", project_input)
        self.assertIn("figure_output", project_input)
        self.assertIn("selected_figure", project_output)
        self.assertIn("snapshot_project_path", project_output)
        self.assertIn("provenance", project_output)

    def test_default_runtime_root_preview_does_not_create_directory(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"

            with (
                _without_runtime_root_env(),
                patch("hub_core.mcp.security.preview_runtime_root", return_value=str(runtime_root)),
            ):
                server = GraphHubMCPServer(research_root=Path(tmpdir))

            self.assertEqual(server.runtime_root, runtime_root.resolve())
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_activates_shared_runtime_resolver_for_write(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            preview_root = Path(tmpdir) / "preview"
            runtime_root = Path(tmpdir) / "runtime"

            with (
                _without_runtime_root_env(),
                patch("hub_core.mcp.security.preview_runtime_root", return_value=str(preview_root)),
                patch("hub_core.mcp.security.resolve_runtime_root", return_value=str(runtime_root)),
            ):
                server = GraphHubMCPServer(research_root=Path(tmpdir))
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "runtime-demo"},
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertFalse(preview_root.exists())

    def test_render_csv_graph_redirects_gdrive_prefetch_stdout_away_from_mcp_stdout(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            stdout = StringIO()
            stderr = StringIO()

            def noisy_prefetch(_paths):
                print("prefetch stdout would corrupt MCP framing")

            with (
                patch.dict(os.environ, {"GRAPH_HUB_PREFETCH_ADAPTER": "gdrive"}, clear=False),
                _without_runtime_root_env(),
                patch("hub_core.mcp.security.resolve_runtime_root", return_value=str(runtime_root)),
                patch("hub_core.adapters.prefetch.ensure_local_files", side_effect=noisy_prefetch),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                server = GraphHubMCPServer(research_root=Path(tmpdir))
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "quiet-prefetch"},
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("prefetch stdout would corrupt MCP framing", stderr.getvalue())

    def test_collect_artifacts_after_restart_uses_shared_runtime_resolver(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            preview_root = Path(tmpdir) / "preview"
            runtime_root = Path(tmpdir) / "runtime"

            with (
                _without_runtime_root_env(),
                patch("hub_core.mcp.security.preview_runtime_root", return_value=str(preview_root)),
                patch("hub_core.mcp.security.resolve_runtime_root", return_value=str(runtime_root)),
                patch(
                    "hub_core.mcp.tools.batch_tools.runtime_root_lookup_candidates",
                    return_value=[str(runtime_root)],
                ),
            ):
                render_server = GraphHubMCPServer(research_root=Path(tmpdir))
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
            self.assertTrue(
                str(Path(collected["provenance"]["manifest_path"]).resolve()).startswith(str(runtime_root.resolve()))
            )
            self.assertFalse(preview_root.exists())

    def test_render_csv_graph_creates_job_only_under_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_csv(tmp_root / "input" / "data.csv")
            runtime_root = tmp_root / "runtime"
            source_snapshot = _snapshot_tree(tmp_root / "input")

            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
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
            provenance = manifest["provenance"]
            self.assertEqual(provenance["job_id"], "render-demo")
            self.assertEqual(provenance["renderer_surface"], "graphhub.render_csv_graph")
            self.assertEqual(provenance["renderer"], "plotting.bridge_renderer.render_bridge_figure")
            self.assertEqual(provenance["source_data_sha256"], provenance["copied_data_sha256"])
            self.assertEqual(len(provenance["config_sha256"]), 64)
            self.assertEqual(len(provenance["environment_sha256"]), 64)
            self.assertIn("hub_git_commit", provenance)
            self.assertTrue(provenance["lock_status"]["python_lock"]["exists"])
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(csv_check["required_columns"], ["x", "y"])
            self.assertEqual(csv_check["semantic_checks"], {"y": {"range": [0, 3], "allow_null": False}})

    def test_render_csv_graph_rejects_data_path_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            external_data = _write_csv(Path(tmpdir) / "outside" / "data.csv")
            runtime_root = research_root / "runtime"
            server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(external_data), "x_column": "x", "y_column": "y", "job_id": "outside-data"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("data_path must stay under", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_data_path_under_runtime_parent_only(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            runtime_root = Path(tmpdir) / "runtime"
            sibling_data = _write_csv(Path(tmpdir) / "runtime-sibling" / "data.csv")
            server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(sibling_data), "x_column": "x", "y_column": "y", "job_id": "runtime-parent"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("data_path must stay under", result["errors"][0])

    def test_collect_artifacts_returns_manifest_metadata(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_csv(tmp_root / "input" / "data.csv")
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
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
            self.assertEqual(collected["provenance"]["renderer_surface"], "graphhub.render_csv_graph")
            self.assertEqual(len(collected["provenance"]["source_data_sha256"]), 64)
            self.assertEqual(len(collected["provenance"]["config_sha256"]), 64)
            self.assertEqual(len(collected["provenance"]["environment_sha256"]), 64)

    def test_render_project_figure_dry_run_does_not_create_runtime_job(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "project-dry", "dry_run": True},
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["is_dry_run"])
            self.assertEqual(result["artifact_status"], "validated")
            self.assertEqual(result["failure_stage"], "")
            self.assertEqual(_snapshot_tree(project), before)
            self.assertFalse((runtime_root / "mcp_project_jobs").exists())

    def test_render_project_figure_dry_run_uses_same_runtime_paths_as_real_render(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "env-runtime"
            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)}):
                dry_server = GraphHubMCPServer(research_root=root)
                dry_result = self._call(
                    dry_server,
                    "graphhub.render_project_figure",
                    {"project_path": str(project), "figure_id": "Fig1", "job_id": "path-parity", "dry_run": True},
                )
                render_server = GraphHubMCPServer(research_root=root)
                render_result = self._call(
                    render_server,
                    "graphhub.render_project_figure",
                    {"project_path": str(project), "figure_id": "Fig1", "job_id": "path-parity-real"},
                )

            expected_dry_root = runtime_root / "mcp_project_jobs" / "path-parity"
            expected_render_root = runtime_root / "mcp_project_jobs" / "path-parity-real"
            self.assertEqual(Path(dry_result["job_root"]).resolve(), expected_dry_root.resolve())
            self.assertEqual(
                Path(dry_result["snapshot_project_path"]).resolve(),
                (expected_dry_root / "project").resolve(),
            )
            self.assertEqual(Path(render_result["job_root"]).resolve(), expected_render_root.resolve())
            self.assertEqual(
                Path(render_result["snapshot_project_path"]).resolve(),
                (expected_render_root / "project").resolve(),
            )

    def test_render_project_figure_runs_selected_figure_in_runtime_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "project-render"},
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(result["job_id"], "project-render")
            self.assertEqual(result["selected_figure"]["id"], "Fig1")
            self.assertTrue(Path(result["output_path"]).is_file())
            self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertEqual(_snapshot_tree(project), before)
            snapshot_project = Path(result["snapshot_project_path"])
            self.assertTrue((snapshot_project / "project_config.yaml").is_file())
            self.assertTrue((snapshot_project / "hub_scripts" / "plot.py").is_file())
            self.assertTrue((snapshot_project / "results" / "data" / "summary.csv").is_file())
            self.assertFalse((snapshot_project / "raw" / "large-secret.bin").exists())
            self.assertTrue(Path(result["manifest_path"]).is_file())
            self.assertTrue(Path(result["status_path"]).is_file())
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["provenance"]["renderer_surface"], "graphhub.render_project_figure")
            self.assertEqual(manifest["selected_figure"]["output"], "results/figures/Fig1.png")
            self.assertEqual(manifest["source_project_path"], "01_Project")
            self.assertEqual(manifest["provenance"]["source_project_path"], "01_Project")
            self.assertEqual(len(manifest["provenance"]["config_sha256"]), 64)
            self.assertEqual(len(manifest["provenance"]["environment_sha256"]), 64)

    def test_render_project_figure_injects_hub_pythonpath_for_legacy_project_context(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_legacy_context_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "legacy-context-render"},
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(result["failure_stage"], "")
            self.assertTrue(Path(result["output_path"]).is_file())
            self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))

    def test_render_project_figure_runs_public_safe_synthetic_fixture(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "synthetic_project"
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_synthetic_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = root / "synthetic_project"
            _copy_tree(fixture, project)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {
                    "project_path": str(project),
                    "figure_id": "FigSynthetic_Response",
                    "job_id": "synthetic-project-render",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(result["selected_figure"]["id"], "FigSynthetic_Response")
            self.assertTrue(Path(result["output_path"]).is_file())
            self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))
            self.assertEqual(_snapshot_tree(project), before)
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["style_summary"]["target_format"], "nature")
            self.assertEqual(manifest["style_summary"]["profile"], "baseline")

    def test_render_project_figure_runs_public_safe_multipanel_fixture(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "multipanel_project"
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_multipanel_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = root / "multipanel_project"
            _copy_tree(fixture, project)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {
                    "project_path": str(project),
                    "figure_id": "FigSynthetic_Multipanel",
                    "job_id": "multipanel-project-render",
                },
            )

            output = Path(result["output_path"])
            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(result["selected_figure"]["id"], "FigSynthetic_Multipanel")
            self.assertTrue(output.is_file())
            self.assertTrue(str(output.resolve()).startswith(str(runtime_root.resolve())))
            self.assertEqual(_snapshot_tree(project), before)
            svg = output.read_text(encoding="utf-8")
            self.assertIn("(a)", svg)
            self.assertIn("(b)", svg)
            self.assertIn("(c)", svg)
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["style_summary"]["target_format"], "nature")
            self.assertEqual(manifest["selected_figure"]["output"], "results/figures/FigSynthetic_Multipanel.svg")

    def test_collect_artifacts_returns_project_render_metadata(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
            self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "project-artifacts"},
            )

            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "project-artifacts"})

            self.assertIn(collected["status"], {"ok", "warning"})
            self.assertEqual(collected["job_id"], "project-artifacts")
            self.assertEqual(collected["provenance"]["renderer_surface"], "graphhub.render_project_figure")
            self.assertEqual(collected["provenance"]["source_project_path"], "01_Project")
            self.assertEqual(len(collected["figures"]), 1)
            self.assertTrue(Path(collected["figures"][0]["path"]).is_file())
            self.assertIn("figure_metadata", collected)

    def test_render_project_figure_requires_unambiguous_selector_without_writing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"].append(
                {"id": "Fig2", "script": "hub_scripts/plot.py", "output": "results/figures/Fig2.png"}
            )
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "job_id": "ambiguous-project"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("figure_id", result["resolution_hint"])
            self.assertFalse((runtime_root / "mcp_project_jobs").exists())

    def test_render_project_figure_rejects_output_path_escape_without_writing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            outside_output = Path(tmpdir) / "outside.png"
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"][0]["output"] = str(outside_output)
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            absolute_result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "absolute-output"},
            )
            config["figures"][0]["output"] = "../outside.png"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            parent_result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "parent-output"},
            )

            self.assertEqual(absolute_result["status"], "error")
            self.assertEqual(parent_result["status"], "error")
            self.assertEqual(absolute_result["failure_stage"], "CONTRACT")
            self.assertEqual(parent_result["failure_stage"], "CONTRACT")
            self.assertFalse(outside_output.exists())
            self.assertFalse((runtime_root / "mcp_project_jobs").exists())

    def test_render_project_figure_rejects_project_path_outside_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            external_root = Path(tmpdir) / "external"
            project = _write_project_render_fixture(external_root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "external-project"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("project_path must stay under", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_project_jobs").exists())

    def test_render_project_figure_missing_input_is_export_failure(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "results" / "data" / "summary.csv").unlink()
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "missing-input"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "EXPORT")
            self.assertIn("declared inputs", result["resolution_hint"])
            self.assertTrue(Path(result["manifest_path"]).is_file())

    def test_render_project_figure_refuses_symlinked_snapshot_inputs(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            target = Path(tmpdir) / "secret.csv"
            target.write_text("x,y\n9,9\n", encoding="utf-8")
            data_path = project / "results" / "data" / "summary.csv"
            data_path.unlink()
            try:
                data_path.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "symlink-input"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "EXPORT")
            self.assertIn("symlink", result["errors"][0])

    def test_render_project_figure_script_failure_error_does_not_leak_absolute_paths(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "from pathlib import Path\nraise RuntimeError(f'failed at {Path.cwd() / \"private-output.png\"}')\n",
                encoding="utf-8",
            )
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "script-fails"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "PLOT")
            self.assertNotIn(str(tmpdir), result["errors"][0])
            self.assertIn("runtime://", result["errors"][0])

    def test_render_project_figure_export_failure_surfaces_swallowed_traceback_tail(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "import traceback\n"
                "try:\n"
                "    raise KeyError('Unknown layout_type duo')\n"
                "except Exception:\n"
                "    traceback.print_exc()\n",
                encoding="utf-8",
            )
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "swallowed-traceback"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "EXPORT")
            self.assertIn("Selected figure output was not created", result["errors"][0])
            self.assertTrue(any("KeyError" in line for line in result["script_output"]))
            self.assertTrue(any("Unknown layout_type duo" in line for line in result["script_output"]))
            self.assertEqual(result["layout_report"]["render_errors"][0]["stage"], "EXPORT")
            self.assertTrue(
                any(
                    "Unknown layout_type duo" in line
                    for line in result["layout_report"]["render_errors"][0]["script_output_tail"]
                )
            )
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertTrue(any("KeyError" in line for line in manifest["script_output"]))
            self.assertEqual(manifest["layout_report"]["render_errors"][0]["stage"], "EXPORT")
            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "swallowed-traceback"})
            self.assertEqual(collected["status"], "error")
            self.assertTrue(any("Unknown layout_type duo" in line for line in collected["script_output"]))
            self.assertEqual(collected["layout_report"]["render_errors"][0]["stage"], "EXPORT")

    def test_render_csv_graph_rejects_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")
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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

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

    def test_render_csv_graph_renders_heatmap_end_to_end(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_grid_csv(tmp_root / "input" / "grid.csv")
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "z_column": "z",
                    "plot_type": "heatmap",
                    "job_id": "render-heatmap",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(result["job_id"], "render-heatmap")
            self.assertTrue(Path(result["output_path"]).is_file())
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(csv_check["required_columns"], ["x", "y", "z"])

    def test_render_csv_graph_forwards_heatmap_value_annotations(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_grid_csv(tmp_root / "input" / "grid.csv")
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                Path(spec_payload["output_path"]).write_bytes(b"png")

            with (
                patch.object(GraphHubMCPServer, "_run_render_bridge_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "z_column": "z",
                        "plot_type": "heatmap",
                        "annotate_values": True,
                        "job_id": "render-heatmap-annotated",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertIs(captured["annotate_values"], True)

    def test_render_csv_graph_forwards_facet_grid_shape_controls(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "facet.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,phase\n0,1,A\n1,2,A\n0,3,B\n1,4,B\n0,5,C\n1,6,C\n0,7,D\n1,8,D\n",
                encoding="utf-8",
            )
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                Path(spec_payload["output_path"]).write_bytes(b"png")

            with (
                patch.object(GraphHubMCPServer, "_run_render_bridge_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "facet_column": "phase",
                        "plot_type": "facet",
                        "facet_ncols": 4,
                        "facet_nrows": 1,
                        "job_id": "render-facet-grid",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["facet_ncols"], 4)
            self.assertEqual(captured["facet_nrows"], 1)

    def test_render_csv_graph_rejects_heatmap_without_z_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_grid_csv(Path(tmpdir) / "input" / "grid.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "plot_type": "heatmap"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("z_column", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_forwards_single_series_bar_error_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_bar_error_csv(tmp_root / "input" / "bar.csv")
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                Path(spec_payload["output_path"]).write_bytes(b"png")

            with (
                patch.object(GraphHubMCPServer, "_run_render_bridge_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "condition",
                        "y_column": "value",
                        "plot_type": "bar",
                        "bar_error_column": "sem",
                        "job_id": "render-bar-yerr",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["yerr_column"], "sem")
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(
                csv_check["semantic_checks"],
                {"value": {"error_bar_source": {"column": "sem", "source": "sem"}}},
            )

    def test_render_csv_graph_rejects_missing_bar_error_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "bar",
                    "bar_error_column": "sem",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("error_bar_source" in error and "sem" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_invalid_statistical_overlay_args(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "significance_markers": [{"x1": 0, "y": 3, "label": "p<0.05"}],
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("significance_markers[0]", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_invalid_bar_aggregate(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "bar",
                    "aggregate": "mode",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("aggregate", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_category_order_for_unsupported_plot_type(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "category_order": [0, 1, 2],
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("category_order", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_large_csv_before_copying(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "large.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with patch("hub_core.mcp.render_orchestration.MCP_RENDER_CSV_MAX_BYTES", 4):
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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            with patch(
                "hub_core.mcp.tools.render_support.validate_figure_preflight",
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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with patch(
                "hub_core.mcp.tools.render_support.validate_figure_preflight",
                return_value={"passed": True, "checks": [], "warnings": []},
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "semantic_checks": {"y": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}},
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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "semantic_checks": {"y": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}},
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

    def test_render_csv_graph_dry_run_axis_unit_skip_requires_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with patch("hub_core.data_contract._PINT_AVAILABLE", False):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "semantic_checks": {"y": {"axis_unit": {"data_unit": "mA", "display_unit": "A"}}},
                        "job_id": "axis-unit-dry-run",
                        "dry_run": True,
                    },
                )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            self.assertTrue(result["is_dry_run"])
            self.assertTrue(any("axis_unit" in warning for warning in result["warnings"]))
            self.assertIn("calculation_checks", result)
            self.assertTrue(result["calculation_checks"]["quality_passed"])
            self.assertTrue(result["calculation_checks"]["manual_review_needed"])
            self.assertEqual(result["calculation_checks"]["checks"][0]["status"], "skipped")
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_contract_failure_includes_calculation_checks(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "data.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("x,y\n0,1\n1,9\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "semantic_checks": {"y": {"linear_fit": {"x_column": "x", "slope": 2.0, "intercept": 1.0}}},
                    "job_id": "linear-fit-failure",
                    "dry_run": True,
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("calculation_checks", result)
            self.assertFalse(result["calculation_checks"]["quality_passed"])
            self.assertEqual(result["calculation_checks"]["checks"][0]["name"], "linear_fit")
            self.assertEqual(result["calculation_checks"]["checks"][0]["status"], "failed")
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_axis_unit_skip_reaches_manifest_and_status(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with (
                patch("hub_core.data_contract._PINT_AVAILABLE", False),
                patch(
                    "hub_core.mcp.tools.render_support.validate_figure_preflight",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "semantic_checks": {"y": {"axis_unit": {"data_unit": "mA", "display_unit": "A"}}},
                        "job_id": "axis-unit-render",
                    },
                )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(any("axis_unit" in warning for warning in result["warnings"]))
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
            for payload in (manifest, status):
                self.assertIn("calculation_checks", payload)
                self.assertTrue(payload["calculation_checks"]["quality_passed"])
                self.assertTrue(payload["calculation_checks"]["manual_review_needed"])
                self.assertEqual(payload["calculation_checks"]["checks"][0]["name"], "axis_unit")
                self.assertEqual(payload["calculation_checks"]["checks"][0]["status"], "skipped")

    def test_render_csv_graph_default_prefetcher_is_noop(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("hub_core.adapters.prefetch.ensure_local_files", side_effect=AssertionError("gdrive ran")),
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertIn(result["status"], {"ok", "warning"})

    def test_render_csv_graph_uses_gdrive_prefetcher_when_opted_in(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            with (
                patch.dict(os.environ, {"GRAPH_HUB_PREFETCH_ADAPTER": "gdrive"}, clear=False),
                patch("hub_core.adapters.prefetch.ensure_local_files") as ensure_local,
            ):
                result = self._call(
                    server,
                    "graphhub.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertIn(result["status"], {"ok", "warning"})
            ensure_local.assert_called_once_with([str(data_path.resolve())])

    def test_render_csv_graph_timeout_returns_execution_error(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with (
                patch("hub_core.mcp.render_orchestration.MCP_RENDER_TIMEOUT_SECONDS", 0.05),
                patch("hub_core.mcp.render_orchestration._render_bridge_figure_worker", _sleeping_render_worker),
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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with patch("hub_core.mcp.render_orchestration._render_bridge_figure_worker", _path_leaking_render_worker):
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

    def test_render_csv_graph_allows_internal_symlinked_data_path_component(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_symlink_data_") as tmpdir:
            root = Path(tmpdir) / "root"
            real_dir = root / "real"
            link_dir = root / "link"
            data_path = _write_csv(real_dir / "data.csv")
            try:
                link_dir.symlink_to(real_dir, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(link_dir / data_path.name), "x_column": "x", "y_column": "y"},
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertFalse(any("symlinked path components" in error for error in result["errors"]))

    def test_render_csv_graph_failure_manifest_preserves_requested_baseline_state(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            baseline_path = Path(tmpdir) / "baseline" / "graph.png"
            baseline_path.parent.mkdir()
            baseline_path.write_bytes(b"not-a-real-png")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with patch("hub_core.mcp.render_orchestration._render_bridge_figure_worker", _path_leaking_render_worker):
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

    def test_render_worker_reads_file_result_after_process_exit(self):
        with (
            patch("hub_core.mcp.render_orchestration._render_bridge_figure_worker", _successful_render_worker),
            patch("hub_core.mcp.render_orchestration.multiprocessing.Process", _CompletedRenderProcess),
        ):
            GraphHubMCPServer._run_render_bridge_figure({"csv_path": "input.csv", "output_path": "graph.png"})

    def test_batch_discovery_reads_file_result_after_process_exit(self):
        with (
            patch("hub_core.mcp.render_orchestration._batch_discovery_worker", _successful_batch_discovery_worker),
            patch("hub_core.mcp.render_orchestration.multiprocessing.Process", _CompletedRenderProcess),
        ):
            projects, timed_out, warnings = GraphHubMCPServer._discover_batch_projects(
                Path("/tmp"),
                max_depth=1,
                timeout_seconds=1.0,
            )

        self.assertEqual(projects, [])
        self.assertFalse(timed_out)
        self.assertEqual(warnings, [])

    def test_baseline_comparison_does_not_expose_baseline_hash(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            artifact_path = Path(tmpdir) / "output.png"
            baseline_path = Path(tmpdir) / "baseline.png"
            artifact_path.write_bytes(b"same")
            baseline_path.write_bytes(b"same")
            server = GraphHubMCPServer(research_root=Path(tmpdir))

            result = server._baseline_comparison(artifact_path, str(baseline_path))

            self.assertTrue(result["checked"])
            self.assertTrue(result["matched"])
            self.assertIn("artifact_sha256", result)
            self.assertNotIn("baseline_sha256", result)

    def test_baseline_comparison_rejects_path_outside_allowed_roots_without_hashing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            artifact_path = research_root / "output.png"
            artifact_path.write_bytes(b"artifact")
            baseline_path = Path(tmpdir) / "outside" / "baseline.png"
            baseline_path.parent.mkdir()
            baseline_path.write_bytes(b"baseline")
            server = GraphHubMCPServer(research_root=research_root)

            result = server._baseline_comparison(artifact_path, str(baseline_path))

            self.assertTrue(result["checked"])
            self.assertFalse(result["matched"])
            self.assertEqual(result["status"], "manual_review_needed")
            self.assertIn("baseline_path must stay under", result["warnings"][0])
            self.assertEqual(result["baseline_path"], "")
            self.assertNotIn("baseline_sha256", result)

    def test_baseline_comparison_rejects_path_under_runtime_parent_only(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            research_root.mkdir()
            runtime_root = Path(tmpdir) / "runtime"
            artifact_path = runtime_root / "output.png"
            artifact_path.parent.mkdir()
            artifact_path.write_bytes(b"artifact")
            baseline_path = Path(tmpdir) / "runtime-sibling" / "baseline.png"
            baseline_path.parent.mkdir()
            baseline_path.write_bytes(b"baseline")
            server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

            result = server._baseline_comparison(artifact_path, str(baseline_path))

            self.assertEqual(result["status"], "manual_review_needed")
            self.assertIn("baseline_path must stay under", result["warnings"][0])
            self.assertNotIn("baseline_sha256", result)

    def test_render_csv_graph_data_contract_error_sanitizes_source_path(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "outside" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            with patch(
                "hub_core.mcp.tools.render_support._read_data_safe",
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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "missing", "y_column": "y"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("data contract", result["resolution_hint"].lower())
            self.assertIn("missing", result["errors"][0])

    def test_render_csv_graph_preflight_failure_sets_manual_review(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

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
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "dry_run": True},
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["is_dry_run"])
            self.assertFalse((runtime_root / "mcp_jobs").exists())
            self.assertEqual(result["created_paths"], [])

    def test_listed_project_id_resolves_in_render_regardless_of_scan_root(self):
        # Issue #16: list_projects emits a project_id that render rejects because
        # the id scheme depends on the discovery root. A project_id from list must
        # round-trip through render's resolution even when the two surfaces scan
        # from different roots, and render must report back the same id.
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            research_root = Path(tmpdir)
            project = _write_project_render_fixture(
                research_root / "ResearchOS" / "02_Surfur_Polymer", name="260504_sulfur_rh25"
            )
            server = GraphHubMCPServer(research_root=research_root)

            # User lists from a narrow root (the project's parent), as in the repro.
            listed = self._call(server, "graphhub.list_projects", {"root": str(project.parent)})
            project_id = listed["projects"][0]["project_id"]

            # Render receives only the project_id, so it scans from research_root —
            # a different root than list used.
            resolved_path = server._resolve_project_path({"project_id": project_id})
            self.assertEqual(resolved_path.resolve(), project.resolve())

            # The id render reports back must equal the id list emitted.
            self.assertEqual(server._stable_project_id_for_path(project), project_id)


def _write_dense_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["x", "y"])
        writer.writeheader()
        writer.writerows([{"x": i, "y": i * i} for i in range(12)])
    return path


class GeometryDiagnosticsIntegrationTest(unittest.TestCase):
    def _call(self, server: GraphHubMCPServer, tool_name: str, arguments: dict | None = None) -> dict:
        response = server.call_tool(tool_name, arguments or {})
        return response["structuredContent"]

    def _render_csv(self, tmpdir, **overrides):
        data_path = _write_dense_csv(Path(tmpdir) / "input" / "data.csv")
        runtime_root = Path(tmpdir) / "runtime"
        server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
        arguments = {
            "data_path": str(data_path),
            "x_column": "x",
            "y_column": "y",
            "plot_type": "scatter",
            "job_id": "geom-csv",
        }
        arguments.update(overrides)
        return server, self._call(server, "graphhub.render_csv_graph", arguments)

    def test_csv_attaches_key_and_manifest(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir)
            self.assertIn(result["status"], {"ok", "warning"})
            diag = result["geometry_diagnostics"]
            self.assertEqual(diag["schema_version"], "geometry_diagnostics/1")
            self.assertTrue(diag["checks"])
            self.assertEqual(result["layout_report"]["schema_version"], "layout_report/1")
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertIn("geometry_diagnostics", manifest)
            self.assertEqual(manifest["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/1")
            self.assertEqual(manifest["layout_report"]["schema_version"], "layout_report/1")
            status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
            self.assertEqual(status["layout_report"]["schema_version"], "layout_report/1")

    def test_project_attaches_key_and_sidecar_outside_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project"},
            )
            self.assertIn(result["status"], {"ok", "warning"})
            self.assertIn("geometry_diagnostics", result)
            self.assertIn("layout_report", result)
            self.assertEqual(result["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/1")
            self.assertEqual(result["layout_report"]["schema_version"], "layout_report/1")
            snapshot = Path(result["snapshot_project_path"])
            self.assertFalse((snapshot / "geometry_diagnostics.json").exists())

    def test_project_save_journal_populates_sidecar(self):
        # Routes through the real save_journal_fig chokepoint (not the write_bytes bypass),
        # so the project env-dict transport is exercised: deleting
        # those two env keys would drop the populated sidecar and fail this test.
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project-real"},
            )
            self.assertIn(result["status"], {"ok", "warning"})
            diag = result["geometry_diagnostics"]
            self.assertIsNotNone(diag["passed"])
            self.assertTrue(len(diag["checks"]) > 0)
            self.assertEqual(diag["schema_version"], "geometry_diagnostics/1")
            job_root = Path(result["snapshot_project_path"]).parent
            self.assertTrue((job_root / "geometry_diagnostics.json").is_file())
            snapshot = Path(result["snapshot_project_path"])
            self.assertFalse((snapshot / "geometry_diagnostics.json").exists())

    def test_project_render_warns_when_declared_canonical_format_mismatches_rendered_figure(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_canonical_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"][0]["layout_type"] = "solo"
            config["figures"][0]["canonical"] = {
                "layout_type": "triplet",
                "width_px": 1,
                "height_px": 1,
                "dimension_tolerance_px": 0,
            }
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "canonical-mismatch"},
            )

            self.assertEqual(result["status"], "warning")
            self.assertTrue(result["manual_review_needed"])
            metadata = result["figure_metadata"]
            self.assertEqual(metadata["layout_type"], "solo")
            self.assertGreater(metadata["width_px"], 1)
            self.assertGreater(metadata["height_px"], 1)
            self.assertFalse(metadata["canonical_check"]["passed"])
            self.assertIn("canonical", metadata["canonical_check"]["warnings"][0])
            self.assertTrue(any("canonical" in warning for warning in result["warnings"]))
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["figure_metadata"], metadata)
            status_payload = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
            self.assertEqual(status_payload["figure_metadata"], metadata)
            collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "canonical-mismatch"})
            self.assertEqual(collected["figure_metadata"], metadata)
            self.assertTrue(any("canonical" in warning for warning in collected["warnings"]))

    def test_project_render_warns_when_declared_canonical_config_is_malformed(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_canonical_bad_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"][0]["canonical"] = {
                "width_px": "wide",
                "height_px": None,
                "dimension_tolerance_px": "loose",
                "widht_px": 300,
            }
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "canonical-config-warning"},
            )

            self.assertEqual(result["status"], "warning")
            warnings = result["figure_metadata"]["canonical_check"]["warnings"]
            self.assertTrue(any("width_px must be an integer" in warning for warning in warnings))
            self.assertTrue(any("dimension_tolerance_px must be an integer" in warning for warning in warnings))
            self.assertTrue(any("unknown key 'widht_px'" in warning for warning in warnings))
            self.assertTrue(any("canonical config warning" in warning for warning in result["warnings"]))

    def test_project_render_extracts_svg_dimensions_for_canonical_check(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_svg_meta_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "from pathlib import Path\n"
                "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
                "Path('results/figures/Fig1.svg').write_text("
                "'<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 320 180\"></svg>', encoding='utf-8')\n",
                encoding="utf-8",
            )
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"][0]["output"] = "results/figures/Fig1.svg"
            config["figures"][0]["canonical"] = {"width_px": 320, "height_px": 180, "dimension_tolerance_px": 0}
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "svg-metadata"},
            )

            metadata = result["figure_metadata"]
            self.assertEqual(metadata["width_px"], 320)
            self.assertEqual(metadata["height_px"], 180)
            self.assertTrue(metadata["canonical_check"]["passed"])

    def test_project_render_warns_when_rendered_figure_deviates_from_existing_family_sibling(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_family_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "from pathlib import Path\n"
                "from PIL import Image\n"
                "Path('results/figures/fig_cvs_fits').mkdir(parents=True, exist_ok=True)\n"
                "Image.new('RGB', (120, 60), 'white').save('results/figures/fig_cvs_fits/FigPI_CvS_Fits.png')\n"
                "Image.new('RGB', (40, 40), 'white').save('results/figures/fig_cvs_fits/FigPTFE_CvS_Fits.png')\n",
                encoding="utf-8",
            )
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"] = [
                {
                    "id": "FigPI_CvS_Fits",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/fig_cvs_fits/FigPI_CvS_Fits.png",
                },
                {
                    "id": "FigPTFE_CvS_Fits",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/fig_cvs_fits/FigPTFE_CvS_Fits.png",
                },
            ]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "FigPTFE_CvS_Fits", "job_id": "family-mismatch"},
            )

            self.assertEqual(result["status"], "warning")
            metadata = result["figure_metadata"]
            self.assertEqual(metadata["width_px"], 40)
            self.assertEqual(metadata["height_px"], 40)
            self.assertFalse(metadata["family_check"]["passed"])
            self.assertEqual(metadata["family_check"]["family"], "CvS_Fits")
            self.assertTrue(any("sibling" in warning for warning in metadata["family_check"]["warnings"]))
            self.assertTrue(any("sibling" in warning for warning in result["warnings"]))

    def test_project_render_family_check_uses_snapshot_artifacts_not_source_tree(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_family_snapshot_") as tmpdir:
            from PIL import Image

            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            source_figure_dir = project / "results" / "figures" / "fig_cvs_fits"
            source_figure_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (500, 40), "white").save(source_figure_dir / "FigPI_CvS_Fits.png")
            (project / "hub_scripts" / "plot.py").write_text(
                "from pathlib import Path\n"
                "from PIL import Image\n"
                "Path('results/figures/fig_cvs_fits').mkdir(parents=True, exist_ok=True)\n"
                "Image.new('RGB', (40, 40), 'white').save('results/figures/fig_cvs_fits/FigPI_CvS_Fits.png')\n"
                "Image.new('RGB', (40, 40), 'white').save('results/figures/fig_cvs_fits/FigPTFE_CvS_Fits.png')\n",
                encoding="utf-8",
            )
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"] = [
                {
                    "id": "FigPI_CvS_Fits",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/fig_cvs_fits/FigPI_CvS_Fits.png",
                },
                {
                    "id": "FigPTFE_CvS_Fits",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/fig_cvs_fits/FigPTFE_CvS_Fits.png",
                },
            ]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "FigPTFE_CvS_Fits", "job_id": "family-snapshot"},
            )

            metadata = result["figure_metadata"]
            self.assertTrue(metadata["family_check"]["passed"])
            self.assertEqual(metadata["family_check"]["siblings"][0]["width_px"], 40)
            self.assertFalse(any("sibling" in warning for warning in result["warnings"]))

    def test_project_render_family_check_does_not_group_unrelated_two_part_ids(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_family_false_positive_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "from pathlib import Path\n"
                "from PIL import Image\n"
                "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
                "Image.new('RGB', (120, 60), 'white').save('results/figures/Setup_A.png')\n"
                "Image.new('RGB', (40, 40), 'white').save('results/figures/Result_A.png')\n",
                encoding="utf-8",
            )
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["figures"] = [
                {
                    "id": "Setup_A",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/Setup_A.png",
                },
                {
                    "id": "Result_A",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/Result_A.png",
                },
            ]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Result_A", "job_id": "family-false-positive"},
            )

            self.assertTrue(result["figure_metadata"]["family_check"]["passed"])
            self.assertEqual(result["figure_metadata"]["family_check"]["siblings"], [])

    def test_project_render_surfaces_artist_overlaps_in_visual_preflight_status(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "import os\n"
                "import sys\n"
                "import matplotlib\n"
                "matplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "from pathlib import Path\n"
                "hub_path = os.environ['RESEARCH_HUB_PATH']\n"
                "if hub_path not in sys.path:\n"
                "    sys.path.insert(0, hub_path)\n"
                "from themes.journal_theme import save_journal_fig\n"
                "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
                "fig, ax = plt.subplots()\n"
                "ax.scatter([0.5], [0.5], s=300)\n"
                "ax.text(0.5, 0.5, 'S70', ha='center', va='center')\n"
                "save_journal_fig(fig, 'results/figures/Fig1.png')\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project-overlap"},
            )

            self.assertEqual(result["status"], "warning")
            overlaps = result["visual_preflight_status"]["overlaps"]
            self.assertTrue(any("S70" in item["a"] or "S70" in item["b"] for item in overlaps))
            self.assertTrue(any("marker:" in item["a"] or "marker:" in item["b"] for item in overlaps))
            layout_overlaps = result["layout_report"]["overlaps"]
            self.assertTrue(any(item["kind"] == "text-marker" for item in layout_overlaps))
            self.assertTrue(any("S70" in item["a"] or "S70" in item["b"] for item in layout_overlaps))

    def test_project_engine_error_degrades_real_render(self):
        # Drives the diagnostics-engine failure through a real project render: the engine is
        # patched to raise IN THE CHILD subprocess (a parent mock.patch cannot reach it). The
        # in-frame helper degrades to passed:None and the already-saved figure survives — the
        # worker's broad except never sees the error.
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root, break_engine=True)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
            result = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project-boom"},
            )
            self.assertNotEqual(result["status"], "error")
            self.assertIsNone(result["geometry_diagnostics"]["passed"])
            self.assertTrue(Path(result["output_path"]).is_file())

    def test_manifest_round_trips_native_types(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir)
            text = Path(result["manifest_path"]).read_text(encoding="utf-8")
            reloaded = json.loads(text)  # numpy/tuple leak would have failed the manifest write
            self.assertEqual(reloaded["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/1")

    def test_reproducibility_hashes_unbroken(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir)
            provenance = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))["provenance"]
            self.assertEqual(len(provenance["config_sha256"]), 64)
            self.assertEqual(len(provenance["environment_sha256"]), 64)

    def test_dry_run_stub(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir, dry_run=True)
            diag = result["geometry_diagnostics"]
            self.assertIsNone(diag["passed"])
            self.assertEqual(diag["checks"], [])
            self.assertEqual(diag["warnings"], ["dry_run"])

    def test_contract_stage_error_carries_stub(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            data_path = _write_dense_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            missing_column = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "does_not_exist"},
            )
            self.assertEqual(missing_column["status"], "error")
            self.assertEqual(missing_column["failure_stage"], "CONTRACT")
            self.assertIn("geometry_diagnostics", missing_column)
            self.assertIsNone(missing_column["geometry_diagnostics"]["passed"])

            file_missing = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": "", "x_column": "x", "y_column": "y"},
            )
            self.assertEqual(file_missing["status"], "error")
            self.assertIn("geometry_diagnostics", file_missing)
            self.assertIsNone(file_missing["geometry_diagnostics"]["passed"])

    def test_warn_only_never_errors(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir)
            self.assertNotEqual(result["status"], "error")
            self.assertEqual(result["errors"], [])
            self.assertTrue(Path(result["output_path"]).is_file())

    def test_geometry_finding_is_sole_status_driver(self):
        # Isolate geometry as the status driver: clean preflight + a warning-eligible
        # geometry finding must flip status to warning and surface the detail string,
        # while passed:True leaves status ok. This exercises the `passed is False` flip
        # and _geometry_warnings surfacing that a real render (preflight-masked) cannot.
        clean_preflight = {"passed": True, "checks": [], "warnings": []}
        finding = {
            "schema_version": "geometry_diagnostics/1",
            "passed": False,
            "checks": [
                {
                    "name": "tick_label_overlaps",
                    "passed": False,
                    "detail": "x: 3 overlapping pairs; y: 0 overlapping pairs (axis 0)",
                    "data": {"axis_index": 0},
                }
            ],
            "warnings": [],
        }
        clean = {"schema_version": "geometry_diagnostics/1", "passed": True, "checks": [], "warnings": []}
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            with (
                patch.object(GraphHubMCPServer, "_safe_preflight", return_value=clean_preflight),
                patch("hub_core.mcp.render_orchestration._read_geometry_sidecar", return_value=finding),
            ):
                _, result = self._render_csv(tmpdir, job_id="geom-flip")
            self.assertEqual(result["status"], "warning")
            self.assertEqual(result["errors"], [])
            self.assertTrue(result["manual_review_needed"])
            self.assertIn("x: 3 overlapping pairs; y: 0 overlapping pairs (axis 0)", result["warnings"])

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            with (
                patch.object(GraphHubMCPServer, "_safe_preflight", return_value=clean_preflight),
                patch("hub_core.mcp.render_orchestration._read_geometry_sidecar", return_value=clean),
            ):
                _, result = self._render_csv(tmpdir, job_id="geom-ok")
            self.assertEqual(result["status"], "ok")

    def test_engine_error_safety_in_frame(self):
        # The helper try/except lives in the same frame that holds the figure, so a
        # diagnostics-engine error degrades to passed:None and never propagates to the
        # worker's broad except (which would hard-fail an already-saved figure).
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        from themes.journal_theme import _safe_geometry_diagnostics_inline

        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 2])
        fig.canvas.draw()
        prior = os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE")
        os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + 3600)
        try:
            with patch(
                "hub_core.geometry_diagnostics.diagnose_figure_geometry",
                side_effect=RuntimeError("boom"),
            ):
                result = _safe_geometry_diagnostics_inline(fig)
            self.assertIsNone(result["passed"])
            self.assertEqual(result["checks"], [])
            self.assertEqual(result["warnings"], ["boom"])
        finally:
            if prior is None:
                os.environ.pop("GEOMETRY_DIAGNOSTICS_DEADLINE", None)
            else:
                os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = prior
            plt.close("all")

    def test_tri_state_discriminator(self):
        # An agent-style `passed is False` branch must distinguish a real finding from
        # "not measured" (None) and a clean pass (True), never conflating None and False.
        def is_finding(diag):
            return diag.get("passed") is False

        self.assertTrue(is_finding({"passed": False}))
        self.assertFalse(is_finding({"passed": True}))
        self.assertFalse(is_finding({"passed": None}))

    def test_no_sidecar_marker(self):
        # A render whose save_journal_fig never wrote a sidecar (env var stripped) must
        # carry the distinct no_sidecar stub, not a silent null.
        from hub_core.mcp.render_orchestration import _read_geometry_sidecar

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            diag = _read_geometry_sidecar(Path(tmpdir))
            self.assertIsNone(diag["passed"])
            self.assertEqual(diag["data"]["reason"], "no_sidecar")
            self.assertTrue(any("geometry_diagnostics_unavailable" in warning for warning in diag["warnings"]))

    def test_env_var_no_leak(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir_a:
            prior_out = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
            prior_deadline = os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE")
            server_a, result_a = self._render_csv(tmpdir_a)
            self.assertEqual(os.environ.get("GEOMETRY_DIAGNOSTICS_OUT"), prior_out)
            self.assertEqual(os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE"), prior_deadline)
            job_root_a = Path(result_a["job_root"])
            with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir_b:
                _, result_b = self._render_csv(tmpdir_b)
                job_root_b = Path(result_b["job_root"])
                self.assertNotEqual(job_root_a, job_root_b)
                self.assertTrue((job_root_b / "geometry_diagnostics.json").exists())
                self.assertFalse(str(job_root_b).startswith(str(job_root_a)))

    def test_schema_validity_per_tool_scoped(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}
        for tool_name in ("graphhub.render_csv_graph", "graphhub.render_project_figure"):
            properties = definitions[tool_name]["outputSchema"]["properties"]
            self.assertIn("geometry_diagnostics", properties)
            self.assertIn("layout_report", properties)
            if tool_name == "graphhub.render_project_figure":
                self.assertIn("figure_metadata", properties)
            geom_schema = properties["geometry_diagnostics"]
            self.assertEqual(set(geom_schema["required"]), {"schema_version", "passed", "checks", "warnings"})
            metric_enum = geom_schema["properties"]["checks"]["items"]["properties"]["name"]["enum"]
            self.assertIn("tick_label_overlaps", metric_enum)
            self.assertIn("text_axis_edge_proximity", metric_enum)
            report_schema = properties["layout_report"]
            self.assertIn("overlaps", report_schema["required"])
            self.assertIn("render_errors", report_schema["required"])
        # per-tool scoping: not declared on non-render tools
        for tool_name in ("graphhub.health", "graphhub.list_projects"):
            self.assertNotIn("geometry_diagnostics", definitions[tool_name]["outputSchema"]["properties"])
        # CSV extras declares the previously-undeclared calculation_checks too (strict-validator gap)
        self.assertIn(
            "calculation_checks",
            definitions["graphhub.render_csv_graph"]["outputSchema"]["properties"],
        )
        # additive non-breakage: real responses validate only because the key is declared.
        # Exercises every response shape against its tool's outputSchema so a stray top-level
        # key would be caught by additionalProperties:False, not just by manual tracing.
        csv_schema = definitions["graphhub.render_csv_graph"]["outputSchema"]
        project_schema = definitions["graphhub.render_project_figure"]["outputSchema"]
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, csv_success = self._render_csv(tmpdir)
            self._assert_validates(csv_success, csv_schema)
            self.assertIn("geometry_diagnostics", csv_success)
            self.assertIn("layout_report", csv_success)
            # remove the declaration -> additionalProperties:False rejects the response
            stripped = json.loads(json.dumps(csv_schema))
            stripped["properties"].pop("geometry_diagnostics")
            with self.assertRaises(AssertionError):
                self._assert_validates(csv_success, stripped)
            stripped = json.loads(json.dumps(csv_schema))
            stripped["properties"].pop("layout_report")
            with self.assertRaises(AssertionError):
                self._assert_validates(csv_success, stripped)

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, csv_dry_run = self._render_csv(tmpdir, dry_run=True)
            self._assert_validates(csv_dry_run, csv_schema)
            self.assertIn("geometry_diagnostics", csv_dry_run)
            self.assertIn("layout_report", csv_dry_run)
            self.assertIn("dry_run", csv_dry_run["layout_report"]["warnings"])

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            data_path = _write_dense_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")
            csv_error = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "does_not_exist"},
            )
            self.assertEqual(csv_error["status"], "error")
            self._assert_validates(csv_error, csv_schema)
            self.assertIn("geometry_diagnostics", csv_error)
            self.assertIn("layout_report", csv_error)

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_save_journal_fixture(root)
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            project_success = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-schema-real"},
            )
            self._assert_validates(project_success, project_schema)
            self.assertIn("geometry_diagnostics", project_success)
            self.assertIn("layout_report", project_success)

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            project_no_sidecar = self._call(
                server,
                "graphhub.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-schema-stub"},
            )
            self._assert_validates(project_no_sidecar, project_schema)
            self.assertIsNone(project_no_sidecar["geometry_diagnostics"]["passed"])
            self.assertIsNone(project_no_sidecar["layout_report"]["passed"])

    def _assert_validates(self, instance: dict, schema: dict) -> None:
        # Hand-rolled non-vacuous check (jsonschema is not a test dependency):
        # required keys present + additionalProperties:False respected for the top object.
        for key in schema.get("required", []):
            self.assertIn(key, instance, f"missing required key: {key}")
        if schema.get("additionalProperties") is False:
            declared = set(schema.get("properties", {}))
            extra = set(instance) - declared
            self.assertEqual(extra, set(), f"undeclared keys present: {sorted(extra)}")


if __name__ == "__main__":
    unittest.main()
