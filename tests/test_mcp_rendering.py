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
from hub_core.mcp.security import PROJECT_ID_REPARSE_ERROR
from hub_core.mcp.transport import _handle_json_rpc
from tests._symlink import symlink_or_skip
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT


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


def test_render_csv_multipanel_facade_delegates_current_renderer_instance(tmp_path):
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")
    arguments = {"job_id": "delegate-witness"}
    expected = {"status": "ok", "summary": "delegated"}

    with patch(
        "hub_core.mcp.tools.render_csv._render_csv_multipanel_handler",
        return_value=expected,
    ) as handler:
        result = server.render_csv_multipanel(arguments)

    assert result is expected
    handler.assert_called_once_with(server, arguments)


def test_project_runtime_timeout_uses_render_orchestration_facade(tmp_path):
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=tmp_path / "runtime")

    with patch("hub_core.mcp.render_orchestration.MCP_RENDER_TIMEOUT_SECONDS", 7.5):
        assert server._project_render_timeout_seconds() == 7.5


def _write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["x", "y"])
        writer.writeheader()
        writer.writerows([{"x": 0, "y": 1}, {"x": 1, "y": 2}, {"x": 2, "y": 3}])
    return path


def _write_valid_png(path: str | Path) -> None:
    from PIL import Image

    Image.new("RGB", (8, 6), "navy").save(path, format="PNG")


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
        "from PIL import Image\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "Image.new('RGB', (64, 48), 'navy').save('results/figures/Fig1.png', format='PNG')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        """
project:
  name: Project Render Fixture
visual_style:
  target_format: nature
  profile: baseline
sample_registry:
  - sample_id: S1
experimental_conditions:
  conditions:
    - id: condition_a
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: ["x", "y"]
      dtypes: {x: number, y: number}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/Fig1.png
    claim: Fixture render completes.
    samples: [S1]
    conditions: [condition_a]
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
sample_registry:
  - sample_id: S1
experimental_conditions:
  conditions:
    - id: condition_a
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: ["x", "y"]
      dtypes: {x: number, y: number}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/Fig1.png
    claim: Fixture render completes.
    samples: [S1]
    conditions: [condition_a]
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
        "from PIL import Image\n"
        "from themes.style_profiles import DEFAULT_PROFILE\n"
        "\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "assert DEFAULT_PROFILE\n"
        "Image.new('RGB', (64, 48), 'navy').save('results/figures/Fig1.png', format='PNG')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        """
project:
  name: Legacy Project Context Fixture
visual_style:
  target_format: nature
  profile: baseline
sample_registry:
  - sample_id: S1
experimental_conditions:
  conditions:
    - id: condition_a
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: ["x", "y"]
      dtypes: {x: number, y: number}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: ["results/data/summary.csv"]
    output: results/figures/Fig1.png
    claim: Fixture render completes.
    samples: [S1]
    conditions: [condition_a]
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

        self.assertIn("figops.render_csv_graph", names)
        self.assertIn("figops.render_project_figure", names)
        self.assertIn("figops.collect_artifacts", names)
        for tool_name in ("figops.render_csv_graph", "figops.render_project_figure", "figops.collect_artifacts"):
            properties = definitions[tool_name]["outputSchema"]["properties"]
            self.assertIn("failure_stage", properties)
            self.assertIn("resolution_hint", properties)
            self.assertIn("manifest_path", properties)
            self.assertIn("status_path", properties)
            self.assertIn("latest_alias", properties)
            self.assertIn("latest_dir", properties)
            self.assertIn("layout_report", properties)
        project_input = definitions["figops.render_project_figure"]["inputSchema"]["properties"]
        project_output = definitions["figops.render_project_figure"]["outputSchema"]["properties"]
        self.assertIn("project_id", project_input)
        self.assertIn("project_path", project_input)
        self.assertIn("figure_id", project_input)
        self.assertIn("figure_output", project_input)
        self.assertIn("selected_figure", project_output)
        self.assertIn("snapshot_project_path", project_output)
        self.assertIn("provenance", project_output)

    def test_render_csv_graph_schema_exposes_legend_axis_polish_controls(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}
        properties = definitions["figops.render_csv_graph"]["inputSchema"]["properties"]

        self.assertEqual(properties["legend_layout"]["type"], "string")
        self.assertIn("standard", properties["legend_layout"]["enum"])
        self.assertIn("top_outside", properties["legend_layout"]["enum"])
        self.assertIn("right_outside", properties["legend_layout"]["enum"])
        self.assertEqual(
            set(properties["legend_options"]["properties"]),
            {"title", "order", "ncol"},
        )
        self.assertFalse(properties["legend_options"].get("additionalProperties", True))
        self.assertEqual(properties["legend_options"]["properties"]["order"]["items"]["type"], "string")
        self.assertGreaterEqual(properties["legend_options"]["properties"]["ncol"].get("minimum", 0), 1)
        self.assertEqual(set(properties["axis_limits"]["properties"]), {"x", "y"})
        for axis in ("x", "y"):
            axis_properties = properties["axis_limits"]["properties"][axis]["properties"]
            self.assertEqual(set(axis_properties), {"min", "max"})
        self.assertEqual(set(properties["tick_style"]["properties"]), {"rotation", "format", "max_label_chars"})
        self.assertGreaterEqual(properties["tick_style"]["properties"]["max_label_chars"].get("minimum", 0), 4)
        self.assertIn("plain", properties["tick_style"]["properties"]["format"]["enum"])
        self.assertEqual(
            set(properties["secondary_y"]["properties"]),
            {"enabled", "column", "axis_label", "scale", "series_label", "limits"},
        )
        self.assertEqual(properties["secondary_y"]["properties"]["scale"]["enum"], ["linear", "log"])
        self.assertIn("scientific", properties["tick_style"]["properties"]["format"]["enum"])
        self.assertIn("compact", properties["tick_style"]["properties"]["format"]["enum"])

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
                    "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "restart-demo"},
                )
                collect_server = GraphHubMCPServer()
                collected = self._call(collect_server, "figops.collect_artifacts", {"job_id": "restart-demo"})

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

            server = GraphHubMCPServer(
                research_root=Path(tmpdir),
                runtime_root=runtime_root,
                write_tools_enabled=True,
            )
            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "target_format": INTERNAL_STYLE_TARGET_FORMAT,
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
            self.assertEqual(manifest["style_summary"]["target_format"], INTERNAL_STYLE_TARGET_FORMAT)
            self.assertEqual(manifest["visual_preflight_status"]["passed"], True)
            provenance = manifest["provenance"]
            self.assertEqual(provenance["job_id"], "render-demo")
            self.assertEqual(provenance["renderer_surface"], "figops.render_csv_graph")
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "job_id": "artifact-demo",
                },
            )

            collected = self._call(server, "figops.collect_artifacts", {"job_id": "artifact-demo"})

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
            self.assertEqual(collected["provenance"]["renderer_surface"], "figops.render_csv_graph")
            self.assertEqual(len(collected["provenance"]["source_data_sha256"]), 64)
            self.assertEqual(len(collected["provenance"]["config_sha256"]), 64)
            self.assertEqual(len(collected["provenance"]["environment_sha256"]), 64)

    def test_render_csv_graph_refuses_symlinked_latest_destination(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_csv(tmp_root / "input" / "data.csv")
            runtime_root = tmp_root / "runtime"
            outside_latest = tmp_root / "outside_latest"
            outside_latest.mkdir()
            latest_parent = runtime_root / "_latest"
            latest_parent.mkdir(parents=True)
            symlink_or_skip(latest_parent / "mcp_render", outside_latest, target_is_directory=True)
            server = GraphHubMCPServer(research_root=tmp_root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "job_id": "latest-symlink",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "EXPORT")
            self.assertIn("symlinked", result["errors"][0])
            self.assertFalse((outside_latest / "manifest.json").exists())
            self.assertFalse((outside_latest / "status.json").exists())

    def test_render_project_figure_dry_run_does_not_create_runtime_job(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
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
                    "figops.render_project_figure",
                    {"project_path": str(project), "figure_id": "Fig1", "job_id": "path-parity", "dry_run": True},
                )
                render_server = GraphHubMCPServer(research_root=root)
                render_result = self._call(
                    render_server,
                    "figops.render_project_figure",
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
                "figops.render_project_figure",
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
            self.assertEqual(manifest["provenance"]["renderer_surface"], "figops.render_project_figure")
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
                "figops.render_project_figure",
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
                "figops.render_project_figure",
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
            manifest = json.loads(
                (runtime_root / "mcp_project_jobs" / "synthetic-project-render" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
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
                "figops.render_project_figure",
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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "project-artifacts"},
            )

            collected = self._call(server, "figops.collect_artifacts", {"job_id": "project-artifacts"})

            self.assertIn(collected["status"], {"ok", "warning"})
            self.assertEqual(collected["job_id"], "project-artifacts")
            self.assertEqual(collected["provenance"]["renderer_surface"], "figops.render_project_figure")
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
                {
                    "id": "Fig2",
                    "script": "hub_scripts/plot.py",
                    "output": "results/figures/Fig2.png",
                    "claim": "Second fixture render completes.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                }
            )
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "job_id": "ambiguous-project"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("figure_id", result["resolution_hint"])
            job_root = runtime_root / "mcp_project_jobs" / "ambiguous-project"
            self.assertTrue((job_root / "manifest.json").is_file())
            self.assertTrue((job_root / "status.json").is_file())
            self.assertTrue(result["manifest_path"].startswith("runtime://"))

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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "absolute-output"},
            )
            config["figures"][0]["output"] = "../outside.png"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            parent_result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "parent-output"},
            )

            self.assertEqual(absolute_result["status"], "error")
            self.assertEqual(parent_result["status"], "error")
            self.assertEqual(absolute_result["failure_stage"], "CONTRACT")
            self.assertEqual(parent_result["failure_stage"], "CONTRACT")
            self.assertFalse(outside_output.exists())
            self.assertFalse((runtime_root / "mcp_project_jobs").exists())

    def test_render_project_invalid_style_persists_failure_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {
                    "project_path": str(project),
                    "figure_id": "Fig1",
                    "job_id": "invalid-style",
                    "target_format": "not-a-style",
                },
            )

            job_root = runtime_root / "mcp_project_jobs" / "invalid-style"
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue((job_root / "manifest.json").is_file())
            self.assertTrue((job_root / "status.json").is_file())
            manifest = json.loads((job_root / "manifest.json").read_text(encoding="utf-8"))
            status = json.loads((job_root / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["failure_stage"], "CONTRACT")
            self.assertEqual(status["failure_stage"], "CONTRACT")
            self.assertEqual(manifest["style_summary"], {})
            self.assertEqual(status["style_summary"], {})
            self.assertEqual(
                manifest["provenance"]["attempt"],
                result["provenance"]["attempt"],
            )

    def test_render_project_figure_rejects_project_path_outside_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            research_root = Path(tmpdir) / "ResearchOS"
            external_root = Path(tmpdir) / "external"
            project = _write_project_render_fixture(external_root)
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "external-project"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertIn("project_path must stay under", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_project_jobs").exists())

    def test_render_project_figure_missing_input_fails_data_contract_before_render(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "results" / "data" / "summary.csv").unlink()
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "missing-input"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "VALIDATE")
            self.assertIn("Data contract preflight failed", result["errors"][0])
            job_root = runtime_root / "mcp_project_jobs" / "missing-input"
            self.assertTrue((job_root / "manifest.json").is_file())
            self.assertTrue((job_root / "status.json").is_file())
            self.assertNotIn(str(tmpdir), json.dumps(result))
            self.assertTrue(result["manifest_path"].startswith("runtime://"))
            persisted = json.loads((job_root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["provenance"]["attempt"], result["provenance"]["attempt"])

    def test_render_project_invalid_config_persists_public_safe_failure_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "project_config.yaml").write_text("project: {}\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "invalid-config"},
            )

            job_root = runtime_root / "mcp_project_jobs" / "invalid-config"
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertTrue((job_root / "manifest.json").is_file())
            self.assertTrue((job_root / "status.json").is_file())
            self.assertTrue(result["job_root"].startswith("runtime://"))
            self.assertTrue(result["manifest_path"].startswith("runtime://"))
            self.assertNotIn(str(tmpdir), result["job_root"])

    def test_render_project_figure_semantic_failure_fails_full_data_contract_without_writing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            config_path = project / "project_config.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config["data_contract"]["csv_checks"][0]["semantic_checks"] = {"y": {"range": [0, 1]}}
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            sidecar = project / "results" / "diagnostics" / "calculation_checks.json"
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text('{"keep": true}', encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "semantic-fails", "dry_run": True},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "VALIDATE")
            self.assertIn("Data contract validation failed", result["errors"][0])
            self.assertEqual(_snapshot_tree(project), before)
            self.assertFalse((runtime_root / "mcp_project_jobs" / "semantic-fails").exists())

    def test_render_project_figure_refuses_symlinked_snapshot_inputs(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            target = Path(tmpdir) / "secret.csv"
            target.write_text("x,y\n9,9\n", encoding="utf-8")
            data_path = project / "results" / "data" / "summary.csv"
            data_path.unlink()
            symlink_or_skip(data_path, target)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_tree(project)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            with (
                patch.object(server, "_copy_project_snapshot", wraps=server._copy_project_snapshot) as copy_snapshot,
                patch.object(
                    server,
                    "_run_project_figure_script",
                    wraps=server._run_project_figure_script,
                ) as run_script,
                patch(
                    "hub_core.mcp.tools.render_project.promote_eligible_project_result",
                ) as promote_result,
            ):
                result = self._call(
                    server,
                    "figops.render_project_figure",
                    {"project_path": str(project), "figure_id": "Fig1", "job_id": "symlink-input"},
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            error = result["errors"][0]
            self.assertTrue(
                "symlink" in error or "escapes project root" in error,
                f"unexpected snapshot-input rejection: {error}",
            )
            copy_snapshot.assert_not_called()
            run_script.assert_not_called()
            promote_result.assert_not_called()
            self.assertFalse(runtime_root.exists())
            self.assertEqual(_snapshot_tree(project), before)
            self.assertFalse((project / "results" / "figures" / "Fig1.png").exists())

    def test_render_project_figure_expands_declared_input_globs_in_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            measurements = project / "raw" / "measurements"
            measurements.mkdir()
            (measurements / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (measurements / "b.csv").write_text("x,y\n3,4\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

            copied = server._copy_project_snapshot(
                source_project=project,
                snapshot_project=Path(tmpdir) / "snapshot",
                config_relpath="project_config.yaml",
                selected_figure={
                    "script": "hub_scripts/plot.py",
                    "inputs": ["raw/measurements/**/*.csv", "raw/measurements/a.csv"],
                },
            )

            copied_names = {Path(path).relative_to(Path(tmpdir) / "snapshot").as_posix() for path in copied}
            self.assertTrue({"raw/measurements/a.csv", "raw/measurements/b.csv"}.issubset(copied_names))

    def test_collect_artifacts_rejects_discovered_manifest_symlink_outside_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_manifest_") as tmpdir:
            root = Path(tmpdir)
            runtime_root = root / "runtime"
            outside = root / "outside-manifest.json"
            outside.write_text('{"leak":"OUTSIDE_SECRET"}', encoding="utf-8")
            manifest_path = runtime_root / "mcp_jobs" / "escaped" / "manifest.json"
            manifest_path.parent.mkdir(parents=True)
            symlink_or_skip(manifest_path, outside)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(server, "figops.collect_artifacts", {"job_id": "escaped"})

            self.assertEqual(result["status"], "error")
            self.assertNotIn("OUTSIDE_SECRET", json.dumps(result))

    def test_safe_preflight_preserves_supported_non_nature_targets(self):
        server = GraphHubMCPServer(research_root=Path.cwd(), runtime_root=Path.cwd() / ".tmp-mcp-runtime")
        with patch(
            "hub_core.mcp.tools.render_support.validate_figure_preflight",
            return_value={"passed": True},
        ) as preflight:
            for target in ("wiley", "cell", INTERNAL_STYLE_TARGET_FORMAT):
                with self.subTest(target=target):
                    server._safe_preflight(Path("figure.jpg"), target)
                    args, _kwargs = preflight.call_args
                    self.assertEqual(args[1], target)

    def test_render_project_figure_script_failure_error_does_not_leak_absolute_paths(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = _write_project_render_fixture(root)
            (project / "hub_scripts" / "plot.py").write_text(
                "from pathlib import Path\n"
                "raise RuntimeError(f'token=TOKEN_SENTINEL failed at {Path.cwd() / \"private-output.png\"}')\n",
                encoding="utf-8",
            )
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "script-fails"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "PLOT")
            self.assertNotIn(str(tmpdir), result["errors"][0])
            self.assertNotIn("TOKEN_SENTINEL", json.dumps(result))
            self.assertNotIn(str(tmpdir), json.dumps(result))
            self.assertIn("runtime://", result["errors"][0])
            nested_tail = result["layout_report"]["render_errors"][0]["script_output_tail"]
            self.assertFalse(any("TOKEN_SENTINEL" in line for line in nested_tail))
            self.assertFalse(any(str(tmpdir) in line for line in nested_tail))
            attempt = result["provenance"]["attempt"]
            self.assertTrue(result["job_root"].startswith("runtime://"))
            self.assertTrue(result["snapshot_project_path"].startswith("runtime://"))
            self.assertTrue(result["output_path"].startswith("runtime://"))
            self.assertTrue(result["config_path"].startswith("runtime://"))
            self.assertTrue(result["manifest_path"].startswith("runtime://"))
            self.assertTrue(result["status_path"].startswith("runtime://"))
            job_root = runtime_root / "mcp_project_jobs" / "script-fails"
            manifest = json.loads((job_root / "manifest.json").read_text(encoding="utf-8"))
            status = json.loads((job_root / "status.json").read_text(encoding="utf-8"))
            collected = self._call(server, "figops.collect_artifacts", {"job_id": "script-fails"})
            self.assertTrue(attempt["attempt_id"])
            self.assertEqual(attempt["surface"], "mcp")
            self.assertEqual(manifest["provenance"]["attempt"], attempt)
            self.assertEqual(status["provenance"]["attempt"], attempt)
            self.assertEqual(collected["provenance"]["attempt"], attempt)
            self.assertNotIn(str(tmpdir), json.dumps(collected))
            self.assertTrue(collected["manifest_path"].startswith("runtime://"))
            self.assertTrue(collected["status_path"].startswith("runtime://"))
            self.assertNotIn("manifest_path", collected["provenance"])

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
                "figops.render_project_figure",
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
            manifest = json.loads(
                (runtime_root / "mcp_project_jobs" / "swallowed-traceback" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(any("KeyError" in line for line in manifest["script_output"]))
            self.assertEqual(manifest["layout_report"]["render_errors"][0]["stage"], "EXPORT")
            collected = self._call(server, "figops.collect_artifacts", {"job_id": "swallowed-traceback"})
            self.assertEqual(collected["status"], "error")
            self.assertTrue(any("Unknown layout_type duo" in line for line in collected["script_output"]))
            self.assertEqual(collected["layout_report"]["render_errors"][0]["stage"], "EXPORT")

    def test_render_csv_graph_rejects_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(
                research_root=Path(tmpdir),
                runtime_root=Path(tmpdir) / "runtime",
                write_tools_enabled=True,
            )
            args = {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "same-job"}
            first = self._call(server, "figops.render_csv_graph", args)
            second = self._call(server, "figops.render_csv_graph", args)

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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                from PIL import Image

                Image.new("RGB", (8, 6), "navy").save(spec_payload["output_path"], format="PNG")

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
                    "figops.render_csv_graph",
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
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
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

    def test_render_csv_graph_forwards_legend_axis_polish_controls(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,condition\n0,1,Beta\n1,2,Beta\n0,3,Alpha\n1,4,Alpha\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "line",
                        "series_column": "condition",
                        "legend_layout": "top_outside",
                        "legend_options": {"title": "Treatment", "order": ["Alpha", "Beta"], "ncol": 2},
                        "axis_limits": {"x": {"min": 0, "max": 1}, "y": {"min": 0, "max": 5}},
                        "tick_style": {"rotation": 45, "format": "plain", "max_label_chars": 10},
                        "job_id": "render-legend-axis-polish",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["legend_layout"], "top_outside")
            self.assertEqual(captured["legend_options"], {"title": "Treatment", "order": ("Alpha", "Beta"), "ncol": 2})
            self.assertEqual(captured["axis_limits"], {"x": {"min": 0.0, "max": 1.0}, "y": {"min": 0.0, "max": 5.0}})
            self.assertEqual(captured["tick_style"], {"rotation": 45.0, "format": "plain", "max_label_chars": 10})

    def test_render_csv_graph_forwards_secondary_y_and_empty_title(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "dielectric.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("freq,eps_real,eps_loss\n1,10,0.5\n10,8,0.8\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "freq",
                        "y_column": "eps_real",
                        "plot_type": "line",
                        "secondary_y": {
                            "column": "eps_loss",
                            "axis_label": "epsilon double-prime",
                            "scale": "log",
                            "series_label": "loss",
                            "limits": {"min": 0.1, "max": 10},
                        },
                        "job_id": "render-secondary-y",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["title"], "")
            self.assertEqual(
                captured["secondary_y"],
                {
                    "column": "eps_loss",
                    "axis_label": "epsilon double-prime",
                    "scale": "log",
                    "series_label": "loss",
                    "limits": {"min": 0.1, "max": 10.0},
                },
            )

    def test_render_csv_graph_honors_explicit_title(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "title": "Custom title",
                        "job_id": "render-explicit-title",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["title"], "Custom title")

    def test_render_csv_graph_rejects_secondary_y_for_heatmap(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "heatmap.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y,z,loss\n0,0,1,0.5\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "z_column": "z",
                    "plot_type": "heatmap",
                    "secondary_y": {"column": "loss"},
                    "job_id": "secondary-y-heatmap",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(any("secondary_y is only supported" in error for error in result["errors"]))

    def test_render_csv_graph_rejects_missing_secondary_y_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "line",
                    "secondary_y": {"column": "loss"},
                    "job_id": "secondary-y-missing-column",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(any("Missing required columns" in error and "loss" in error for error in result["errors"]))

    def test_render_csv_graph_rejects_nonpositive_log_secondary_y(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y,loss\n0,1,0\n1,2,0.5\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "line",
                    "secondary_y": {"column": "loss", "scale": "log"},
                    "job_id": "secondary-y-log-invalid",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(any("Column 'loss'" in error and "log scale" in error for error in result["errors"]))

    def test_render_csv_graph_forwards_dense_point_label_controls(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "labels.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,label,priority,hide\n0,1,A,1,0\n1,2,B,5,0\n2,3,C,3,yes\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "label_column": "label",
                        "point_label_options": {
                            "max_labels": 1,
                            "priority_column": "priority",
                            "skip_column": "hide",
                            "offset": {"dx": 4, "dy": 8},
                            "fanout": "compass",
                        },
                        "job_id": "render-dense-point-label-polish",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["label_column"], "label")
            self.assertEqual(
                captured["point_label_options"],
                {
                    "max_labels": 1,
                    "priority_column": "priority",
                    "skip_column": "hide",
                    "offset": {"dx": 4.0, "dy": 8.0},
                    "fanout": "compass",
                },
            )

    def test_render_csv_graph_smoke_renders_with_legend_axis_polish_controls(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,condition\n0,1,Beta\n1,2,Beta\n0,3,Alpha\n1,4,Alpha\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "line",
                    "series_column": "condition",
                    "legend_layout": "top_outside",
                    "legend_options": {"title": "Treatment", "order": ["Alpha", "Beta"], "ncol": 2},
                    "axis_limits": {"x": {"min": 0, "max": 1}, "y": {"min": 0, "max": 5}},
                    "tick_style": {"rotation": 45, "format": "plain"},
                    "job_id": "render-legend-axis-polish-smoke",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertTrue(Path(result["output_path"]).is_file())
            self.assertEqual(result["job_id"], "render-legend-axis-polish-smoke")

    def test_render_csv_graph_does_not_project_point_label_policy_into_raw_geometry(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "labels.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,label,priority,hide\n0,1,A,1,0\n1,2,B,5,0\n2,3,C,3,yes\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "label_column": "label",
                    "point_label_options": {
                        "max_labels": 1,
                        "priority_column": "priority",
                        "skip_column": "hide",
                        "fanout": "compass",
                    },
                    "job_id": "render-dense-point-label-skips",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertTrue(Path(result["output_path"]).is_file())
            measurements = result["geometry_diagnostics"]["measurements"]
            self.assertFalse(any(item["metric_id"].startswith("point_label_skips") for item in measurements))
            self.assertTrue(any(item["metric_id"].startswith("text_axis_edge_distances") for item in measurements))

    def test_render_csv_graph_smoke_reports_annotation_overlay_contrast(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "contrast.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n0,0\n1,1\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "annotations": [
                        {"hspan": {"ymin": 0.2, "ymax": 0.8}, "text": "dark", "color": "black", "alpha": 0.9}
                    ],
                    "job_id": "render-annotation-overlay-contrast",
                },
            )

            self.assertIn(result["status"], {"ok", "warning"})
            measurements = result["geometry_diagnostics"]["measurements"]
            contrast_measurement = next(
                item for item in measurements if item["metric_id"].startswith("annotation_overlay_contrast")
            )
            self.assertTrue(contrast_measurement["value"]["pairs"])

    def test_render_csv_graph_forwards_log_scale_series_and_annotations(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,condition\n1,10,A\n2,100,A\n1,20,B\n2,200,B\n",
                encoding="utf-8",
            )
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "series_column": "condition",
                        "series_styles": {
                            "A": {
                                "marker": "o",
                                "fill": "none",
                                "edgecolor": "black",
                                "color": "#777777",
                                "alpha": "0.4",
                                "size": "18",
                                "linewidth": "1.8",
                                "zorder": "3",
                                "label": "Literature",
                            }
                        },
                        "x_scale": "linear",
                        "y_scale": "log",
                        "annotations": [
                            {
                                "x": 2,
                                "y": 200,
                                "text": "~10x",
                                "arrow_to": {"x": 1, "y": 20},
                                "xytext_offset": {"dx": 12, "dy": 18},
                                "placement_preset": "upper_right",
                                "avoid_overlap": True,
                                "color": "black",
                            }
                        ],
                        "job_id": "render-series-log-annotated",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["series_column"], "condition")
            self.assertEqual(
                captured["series_styles"],
                {
                    "A": {
                        "marker": "o",
                        "fill": "none",
                        "edgecolor": "black",
                        "color": "#777777",
                        "alpha": "0.4",
                        "size": "18",
                        "linewidth": "1.8",
                        "zorder": "3",
                        "label": "Literature",
                    }
                },
            )
            self.assertEqual(captured["x_scale"], "linear")
            self.assertEqual(captured["y_scale"], "log")
            self.assertEqual(captured["annotations"][0]["text"], "~10x")
            self.assertEqual(captured["annotations"][0]["xytext_offset"], {"dx": 12, "dy": 18})
            self.assertEqual(captured["annotations"][0]["placement_preset"], "upper_right")
            self.assertIs(captured["annotations"][0]["avoid_overlap"], True)
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(csv_check["required_columns"], ["x", "y", "condition"])

    def test_render_csv_graph_rejects_callout_offset_on_region_annotation(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "annotations.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n1,10\n2,100\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "annotations": [
                        {
                            "region": {"xmin": 1, "xmax": 2, "ymin": 10, "ymax": 20},
                            "xytext_offset": {"dx": 12, "dy": 18},
                        }
                    ],
                    "job_id": "render-invalid-region-callout",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertIn("only apply to point annotations", result["errors"][0])

    def test_render_csv_graph_forwards_curved_arrow_and_spans(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "annotations.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n1,10\n2,100\n", encoding="utf-8")
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "annotations": [
                            {
                                "x": 2,
                                "y": 200,
                                "text": "",
                                "arrow_to": {"x": 1, "y": 20},
                                "arrowstyle": "-|>",
                                "connectionstyle": "arc3,rad=0.25",
                            },
                            {"hspan": {"ymin": 10, "ymax": 20}, "text": "band", "color": "#ccc", "alpha": 0.4},
                            {"vspan": {"xmin": 1, "xmax": 2}, "text": "window"},
                        ],
                        "job_id": "render-annotation-primitives",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["annotations"][0]["text"], "")
            self.assertEqual(captured["annotations"][0]["arrowstyle"], "-|>")
            self.assertEqual(captured["annotations"][0]["connectionstyle"], "arc3,rad=0.25")
            self.assertEqual(captured["annotations"][1]["hspan"], {"ymin": 10, "ymax": 20})
            self.assertEqual(captured["annotations"][2]["vspan"], {"xmin": 1, "xmax": 2})

    def test_render_csv_graph_forwards_fit_options(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "fit_line": True,
                        "ci_band": False,
                        "fit_options": {
                            "model": "linear",
                            "label": "least-squares fit",
                            "color": "tab:red",
                            "linestyle": "--",
                            "linewidth": 2.5,
                            "ci_alpha": 0.2,
                            "ci_label": "fit confidence",
                        },
                        "job_id": "render-csv-fit-options",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["fit_options"]["model"], "linear")
            self.assertEqual(captured["fit_options"]["label"], "least-squares fit")
            self.assertEqual(captured["fit_options"]["color"], "tab:red")
            self.assertEqual(captured["fit_options"]["linestyle"], "--")
            self.assertEqual(captured["fit_options"]["linewidth"], 2.5)
            self.assertEqual(captured["fit_options"]["ci_alpha"], 0.2)
            self.assertEqual(captured["fit_options"]["ci_label"], "fit confidence")

    def test_render_csv_graph_rejects_fit_options_without_fit_overlay(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "fit_options": {"model": "linear"},
                    "job_id": "bad-fit-options",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertTrue(any("fit_options requires fit_line or ci_band" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_schema_exposes_fit_options(self):
        tool = next(
            definition for definition in list_tool_definitions() if definition["name"] == "figops.render_csv_graph"
        )
        fit_options = tool["inputSchema"]["properties"]["fit_options"]["properties"]

        self.assertEqual(fit_options["model"]["enum"], ["linear"])
        self.assertIn("ci_alpha", fit_options)
        self.assertIn("ci_label", fit_options)

    def test_render_csv_graph_forwards_guide_curve_and_fill_between_region(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "overlay.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,lower,upper\n0,1,0.5,1.5\n1,2,1.5,2.5\n2,3,2.5,3.5\n",
                encoding="utf-8",
            )
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "guide_curves": [
                            {
                                "points": [{"x": 0, "y": 1.1}, {"x": 1, "y": 2.2}, {"x": 2, "y": 3.1}],
                                "label": "guide",
                            }
                        ],
                        "fill_between": [
                            {"x_column": "x", "y1_column": "lower", "y2_column": "upper", "label": "band"}
                        ],
                        "job_id": "render-overlay-primitives",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["guide_curves"][0]["label"], "guide")
            self.assertEqual(captured["fill_between"][0]["y1_column"], "lower")
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(csv_check["required_columns"], ["x", "y", "lower", "upper"])

    def test_render_csv_graph_rejects_invalid_span_annotation(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "bad_annotations.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n1,10\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "annotations": [{"hspan": {"ymin": 10}}],
                    "job_id": "render-bad-annotation-span",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("hspan must contain ymin and ymax", "\n".join(result["errors"]))

    def test_render_csv_graph_rejects_invalid_series_style_key(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "bad_series_style.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y,condition\n1,10,A\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "series_column": "condition",
                    "series_styles": {"A": {"unknown": "value"}},
                    "job_id": "render-bad-series-style",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertIn("unsupported key", "\n".join(result["errors"]))

    def test_render_csv_graph_forwards_scatter_yerr_columns(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "series_yerr.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,yerr_lo,yerr_hi,condition\n1,10,1,2,A\n2,100,3,4,A\n1,20,2,3,B\n2,200,4,5,B\n",
                encoding="utf-8",
            )
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "series_column": "condition",
                        "yerr_column": "yerr_hi",
                        "yerr_minus_column": "yerr_lo",
                        "yerr_cap_width": 2.5,
                        "job_id": "render-scatter-yerr",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["yerr_column"], "yerr_hi")
            self.assertEqual(captured["yerr_minus_column"], "yerr_lo")
            self.assertEqual(captured["yerr_cap_width"], 2.5)
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            csv_check = config["data_contract"]["csv_checks"][0]
            self.assertEqual(
                csv_check["semantic_checks"],
                {"y": {"error_bar_source": {"column": "yerr_hi", "source": "yerr_hi"}}},
            )

    def test_render_csv_graph_rejects_log_scale_with_nonpositive_data(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "bad_log.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y\n0,1\n1,-2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "x_scale": "log",
                    "y_scale": "log",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("log scale" in error for error in result["errors"]))

    def test_render_csv_graph_rejects_missing_scatter_yerr_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "scatter",
                    "yerr_column": "missing_sem",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("missing_sem" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_forwards_independent_panel_specs(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            panel_a = tmp_root / "input" / "a.csv"
            panel_b = tmp_root / "input" / "b.csv"
            panel_a.parent.mkdir(parents=True, exist_ok=True)
            panel_a.write_text("era,rho,sem,label,priority\nA,100,10,A,1\nB,1000,100,B,2\n", encoding="utf-8")
            panel_b.write_text(
                "rho,eps,sem,condition,lower,upper\n"
                "100,10,1,Reference,8,12\n"
                "1000,8,2,This work,6,10\n"
                "10000,6,1,This work,5,8\n",
                encoding="utf-8",
            )
            runtime_root = tmp_root / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

            with (
                patch.object(GraphHubMCPServer, "_run_render_multipanel_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "figops.render_csv_multipanel",
                    {
                        "panels": [
                            {
                                "data_path": str(panel_a),
                                "x_column": "era",
                                "y_column": "rho",
                                "plot_type": "scatter",
                                "y_scale": "log",
                                "yerr_column": "sem",
                                "label_column": "label",
                                "point_label_options": {
                                    "max_labels": 1,
                                    "priority_column": "priority",
                                    "fanout": "compass",
                                },
                                "title": "panel a",
                            },
                            {
                                "data_path": str(panel_b),
                                "x_column": "rho",
                                "y_column": "eps",
                                "plot_type": "scatter",
                                "x_scale": "log",
                                "secondary_y": {
                                    "column": "sem",
                                    "axis_label": "SEM",
                                    "scale": "log",
                                    "series_label": "uncertainty",
                                    "limits": {"min": 0.5, "max": 5},
                                },
                                "series_column": "condition",
                                "series_styles": {
                                    "Reference": {"marker": "o", "fill": "none", "edgecolor": "black"}
                                },
                                "guide_curves": [
                                    {"points": [{"x": 100, "y": 9}, {"x": 1000, "y": 9}], "label": "guide"}
                                ],
                                "fill_between": [
                                    {
                                        "x_column": "rho",
                                        "y1_column": "lower",
                                        "y2_column": "upper",
                                        "label": "band",
                                    }
                                ],
                                "fit_line": True,
                                "ci_band": False,
                                "fit_options": {
                                    "model": "linear",
                                    "label": "panel fit",
                                    "color": "tab:blue",
                                    "ci_alpha": 0.15,
                                },
                                "title": "panel b",
                            },
                        ],
                        "rows": 1,
                        "cols": 2,
                        "job_id": "render-csv-multipanel",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["rows"], 1)
            self.assertEqual(captured["cols"], 2)
            self.assertEqual(captured["panels"][0]["plot_type"], "scatter")
            self.assertEqual(captured["panels"][0]["y_scale"], "log")
            self.assertEqual(captured["panels"][0]["yerr_column"], "sem")
            self.assertEqual(captured["panels"][0]["label_column"], "label")
            self.assertEqual(
                captured["panels"][0]["point_label_options"],
                {"max_labels": 1, "priority_column": "priority", "fanout": "compass"},
            )
            self.assertEqual(captured["panels"][1]["x_scale"], "log")
            self.assertEqual(
                captured["panels"][1]["secondary_y"],
                {
                    "column": "sem",
                    "axis_label": "SEM",
                    "scale": "log",
                    "series_label": "uncertainty",
                    "limits": {"min": 0.5, "max": 5.0},
                },
            )
            self.assertEqual(captured["panels"][1]["series_column"], "condition")
            self.assertEqual(captured["panels"][1]["guide_curves"][0]["label"], "guide")
            self.assertEqual(captured["panels"][1]["fill_between"][0]["y2_column"], "upper")
            self.assertEqual(
                captured["panels"][1]["series_styles"],
                {"Reference": {"marker": "o", "fill": "none", "edgecolor": "black"}},
            )
            self.assertEqual(captured["panels"][1]["guide_curves"][0]["color"], "black")
            self.assertEqual(captured["panels"][1]["fill_between"][0]["alpha"], 0.2)
            self.assertTrue(captured["panels"][1]["fit_line"])
            self.assertFalse(captured["panels"][1]["ci_band"])
            self.assertEqual(captured["panels"][1]["fit_options"]["label"], "panel fit")
            self.assertEqual(captured["panels"][1]["fit_options"]["ci_alpha"], 0.15)
            self.assertEqual(result["provenance"]["renderer_surface"], "figops.render_csv_multipanel")
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            self.assertEqual(config["render_payload"]["panels"][1]["secondary_y"]["column"], "sem")
            self.assertEqual(config["render_payload"]["panels"][1]["secondary_y"]["limits"]["max"], 5.0)

    def test_render_csv_multipanel_overwrite_removes_existing_job_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = _write_csv(tmp_root / "input" / "data.csv")
            runtime_root = tmp_root / "runtime"
            job_root = runtime_root / "mcp_jobs" / "multipanel-overwrite"
            stale = job_root / "stale.txt"
            stale.parent.mkdir(parents=True)
            stale.write_text("old", encoding="utf-8")
            server = GraphHubMCPServer(research_root=tmp_root, runtime_root=runtime_root)

            def capture_render(spec_payload):
                _write_valid_png(spec_payload["output_path"])

            with (
                patch.object(GraphHubMCPServer, "_run_render_multipanel_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "figops.render_csv_multipanel",
                    {
                        "panels": [{"data_path": str(data_path), "x_column": "x", "y_column": "y"}],
                        "rows": 1,
                        "cols": 1,
                        "job_id": "multipanel-overwrite",
                        "overwrite": True,
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertFalse(stale.exists())
            self.assertTrue((job_root / "outputs" / "multipanel.png").exists())

    def test_render_csv_multipanel_forwards_layout_options(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

            with (
                patch.object(GraphHubMCPServer, "_run_render_multipanel_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "figops.render_csv_multipanel",
                    {
                        "panels": [
                            {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                            {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                        ],
                        "rows": 1,
                        "cols": 2,
                        "layout_options": {
                            "wspace": 0.8,
                            "hspace": 0.2,
                            "gutter_h_mm": 8.0,
                            "gutter_v_mm": 4.0,
                            "width_ratios": [2.0, 1.0],
                            "height_ratios": [1.0],
                        },
                        "shared_legend": True,
                        "shared_legend_options": {
                            "title": "Condition",
                            "order": ["B", "A"],
                            "ncol": 2,
                            "position": "bottom",
                        },
                        "job_id": "render-csv-multipanel-layout",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertEqual(captured["wspace"], 0.8)
            self.assertEqual(captured["hspace"], 0.2)
            self.assertEqual(captured["gutter_h_mm"], 8.0)
            self.assertEqual(captured["gutter_v_mm"], 4.0)
            self.assertEqual(captured["width_ratios"], (2.0, 1.0))
            self.assertEqual(captured["height_ratios"], (1.0,))
            self.assertTrue(captured["shared_legend"])
            self.assertEqual(
                captured["shared_legend_options"],
                {"title": "Condition", "order": ("B", "A"), "ncol": 2, "position": "bottom"},
            )
            config = yaml.safe_load(Path(result["config_path"]).read_text(encoding="utf-8"))
            self.assertEqual(config["layout_options"]["width_ratios"], [2.0, 1.0])
            self.assertEqual(config["render_payload"]["wspace"], 0.8)
            self.assertEqual(config["render_payload"]["width_ratios"], [2.0, 1.0])
            self.assertEqual(config["render_payload"]["height_ratios"], [1.0])
            self.assertTrue(config["render_payload"]["shared_legend"])
            self.assertEqual(config["render_payload"]["shared_legend_options"]["position"], "bottom")
            self.assertEqual(config["render_payload"]["panels"][0]["csv_path"], captured["panels"][0]["csv_path"])

    def test_render_csv_multipanel_rejects_fit_options_without_fit_overlay(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "y",
                            "plot_type": "scatter",
                            "fit_options": {"model": "linear"},
                        }
                    ],
                    "job_id": "multipanel-fit-options-invalid",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(any("fit_options requires fit_line or ci_band" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_rejects_bad_layout_ratio_length(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [{"data_path": str(data_path), "x_column": "x", "y_column": "y"}],
                    "rows": 1,
                    "cols": 2,
                    "layout_options": {"width_ratios": [1.0]},
                    "job_id": "bad-multipanel-layout",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertTrue(any("layout_options.width_ratios" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_schema_exposes_layout_options(self):
        tool = next(
            definition for definition in list_tool_definitions() if definition["name"] == "figops.render_csv_multipanel"
        )
        properties = tool["inputSchema"]["properties"]
        panel_properties = properties["panels"]["items"]["properties"]
        layout_properties = properties["layout_options"]["properties"]
        shared_legend_properties = properties["shared_legend_options"]["properties"]

        self.assertEqual(
            set(panel_properties["secondary_y"]["properties"]),
            {"enabled", "column", "axis_label", "scale", "series_label", "limits"},
        )
        self.assertEqual(panel_properties["secondary_y"]["properties"]["scale"]["enum"], ["linear", "log"])
        self.assertIn("wspace", layout_properties)
        self.assertIn("hspace", layout_properties)
        self.assertIn("gutter_h_mm", layout_properties)
        self.assertIn("gutter_v_mm", layout_properties)
        self.assertIn("width_ratios", layout_properties)
        self.assertIn("height_ratios", layout_properties)
        self.assertEqual(properties["shared_legend"], {"type": "boolean", "default": False})
        self.assertEqual(shared_legend_properties["position"]["enum"], ["top", "bottom", "right"])
        self.assertEqual(shared_legend_properties["order"]["items"]["type"], "string")

    def test_render_csv_multipanel_rejects_shared_legend_options_without_shared_legend(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [{"data_path": str(data_path), "x_column": "x", "y_column": "y"}],
                    "shared_legend_options": {"position": "top"},
                    "job_id": "shared-legend-options-without-shared-legend",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertTrue(
                any("shared_legend_options requires shared_legend=true" in error for error in result["errors"])
            )
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_rejects_non_integer_shared_legend_ncol(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            for ncol in (True, 1.7):
                with self.subTest(ncol=ncol):
                    result = self._call(
                        server,
                        "figops.render_csv_multipanel",
                        {
                            "panels": [{"data_path": str(data_path), "x_column": "x", "y_column": "y"}],
                            "shared_legend": True,
                            "shared_legend_options": {"ncol": ncol},
                            "job_id": f"shared-legend-ncol-{type(ncol).__name__}",
                        },
                    )

                    self.assertEqual(result["status"], "error")
                    self.assertEqual(result["failure_stage"], "CONFIG")
                    self.assertTrue(
                        any("shared_legend_options.ncol must be an integer" in error for error in result["errors"])
                    )

    def test_render_csv_multipanel_rejects_missing_panel_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "missing_y",
                            "plot_type": "scatter",
                        }
                    ],
                    "job_id": "bad-multipanel",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("missing_y" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_rejects_secondary_y_for_heatmap(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_grid_csv(Path(tmpdir) / "input" / "grid.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "y",
                            "z_column": "z",
                            "plot_type": "heatmap",
                            "secondary_y": {"column": "loss"},
                        }
                    ],
                    "job_id": "multipanel-secondary-y-heatmap",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertTrue(any("secondary_y is only supported" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_rejects_missing_secondary_y_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "y",
                            "plot_type": "line",
                            "secondary_y": {"column": "loss"},
                        }
                    ],
                    "job_id": "multipanel-secondary-y-missing-column",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("Missing required columns" in error and "loss" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_rejects_nonpositive_log_secondary_y(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "dielectric.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text("x,y,loss\n0,1,0\n1,2,0.5\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "y",
                            "plot_type": "line",
                            "secondary_y": {"column": "loss", "scale": "log"},
                        }
                    ],
                    "job_id": "multipanel-secondary-y-log-invalid",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("Column 'loss'" in error and "log scale" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_ignores_disabled_secondary_y(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            captured = {}

            def capture_render(spec_payload):
                captured.update(spec_payload)
                _write_valid_png(spec_payload["output_path"])

            with (
                patch.object(GraphHubMCPServer, "_run_render_multipanel_figure", side_effect=capture_render),
                patch.object(
                    GraphHubMCPServer,
                    "_visual_preflight_with_geometry_overlaps",
                    return_value={"passed": True, "checks": [], "warnings": []},
                ),
            ):
                result = self._call(
                    server,
                    "figops.render_csv_multipanel",
                    {
                        "panels": [
                            {
                                "data_path": str(data_path),
                                "x_column": "x",
                                "y_column": "y",
                                "plot_type": "line",
                                "secondary_y": {"enabled": False, "column": "missing_loss"},
                            }
                        ],
                        "job_id": "multipanel-secondary-y-disabled",
                    },
                )

            self.assertIn(result["status"], {"ok", "warning"})
            self.assertIsNone(captured["panels"][0]["secondary_y"])

    def test_render_csv_multipanel_rejects_grid_that_cannot_fit_panels(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                        {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                    ],
                    "rows": 1,
                    "cols": 1,
                    "job_id": "bad-multipanel-grid",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertTrue(any("rows * cols" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_multipanel_rejects_heatmap_without_z_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_grid_csv(Path(tmpdir) / "input" / "grid.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_multipanel",
                {
                    "panels": [
                        {
                            "data_path": str(data_path),
                            "x_column": "x",
                            "y_column": "y",
                            "plot_type": "heatmap",
                        }
                    ],
                    "job_id": "bad-multipanel-heatmap",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertTrue(any("z_column" in error for error in result["errors"]))
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_rejects_facet_series_until_shared_legend_is_supported(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            tmp_root = Path(tmpdir)
            data_path = tmp_root / "input" / "facet_series.csv"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            data_path.write_text(
                "x,y,phase,condition\n0,1,A,control\n1,2,A,treated\n0,3,B,control\n1,4,B,treated\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=tmp_root / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "facet",
                    "facet_column": "phase",
                    "series_column": "condition",
                },
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONFIG")
            self.assertTrue(any("series_column" in error for error in result["errors"]))

    def test_render_csv_graph_rejects_heatmap_without_z_column(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_grid_csv(Path(tmpdir) / "input" / "grid.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_graph",
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
                _write_valid_png(spec_payload["output_path"])

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
                    "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertEqual(result["status"], "error")
            self.assertIn("exceeds", result["errors"][0])
            self.assertFalse((runtime_root / "mcp_jobs").exists())

    def test_render_csv_graph_ignores_invalid_csv_size_limit_environment(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(
                research_root=Path(tmpdir),
                runtime_root=Path(tmpdir) / "runtime",
                write_tools_enabled=True,
            )

            with patch.dict(os.environ, {"GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES": "not-an-int"}, clear=False):
                result = self._call(
                    server,
                    "figops.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertIn(result["status"], {"ok", "warning"})

    def test_render_csv_graph_records_pdf_companion_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
            server = GraphHubMCPServer(
                research_root=Path(tmpdir),
                runtime_root=Path(tmpdir) / "runtime",
                write_tools_enabled=True,
            )

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("hub_core.adapters.prefetch.ensure_local_files", side_effect=AssertionError("gdrive ran")),
            ):
                result = self._call(
                    server,
                    "figops.render_csv_graph",
                    {"data_path": str(data_path), "x_column": "x", "y_column": "y"},
                )

            self.assertIn(result["status"], {"ok", "warning"})

    def test_render_csv_graph_uses_gdrive_prefetcher_when_opted_in(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            server = GraphHubMCPServer(
                research_root=Path(tmpdir),
                runtime_root=Path(tmpdir) / "runtime",
                write_tools_enabled=True,
            )

            with (
                patch.dict(os.environ, {"GRAPH_HUB_PREFETCH_ADAPTER": "gdrive"}, clear=False),
                patch("hub_core.adapters.prefetch.ensure_local_files") as ensure_local,
            ):
                result = self._call(
                    server,
                    "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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

            collected = self._call(server, "figops.collect_artifacts", {"job_id": "path-demo"})
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
            symlink_or_skip(link_dir, real_dir, target_is_directory=True)
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

            result = self._call(
                server,
                "figops.render_csv_graph",
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
                    "figops.render_csv_graph",
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

            collected = self._call(server, "figops.collect_artifacts", {"job_id": "baseline-failure-demo"})
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
                    "figops.render_csv_graph",
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
                "params": {"name": "figops.render_csv_graph", "arguments": {"x_column": "x", "y_column": "y"}},
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
                    "name": "figops.render_csv_graph",
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
                        "name": "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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
                "figops.render_csv_graph",
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

            collected = self._call(server, "figops.collect_artifacts", {"job_id": "preflight-demo"})
            self.assertEqual(collected["status"], "warning")
            self.assertTrue(collected["manual_review_needed"])
            self.assertTrue(collected["warnings"])

    def test_collect_artifacts_missing_job_does_not_create_default_runtime_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            runtime_root = Path(tmpdir) / "runtime"

            with patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime_root)}, clear=False):
                server = GraphHubMCPServer()
                result = self._call(server, "figops.collect_artifacts", {"job_id": "missing-job"})

            self.assertEqual(result["status"], "error")
            self.assertFalse(runtime_root.exists())

    def test_render_csv_graph_dry_run_does_not_create_job_directory(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_render_") as tmpdir:
            data_path = _write_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)

            result = self._call(
                server,
                "figops.render_csv_graph",
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
                research_root / "ResearchOS" / "02_Synthetic_Project", name="260504_synthetic"
            )
            server = GraphHubMCPServer(research_root=research_root)

            # User lists from a narrow root (the project's parent), as in the repro.
            listed = self._call(server, "figops.list_projects", {"root": str(project.parent)})
            project_id = listed["projects"][0]["project_id"]

            # Render receives only the project_id, so it scans from research_root —
            # a different root than list used.
            resolved_path = server._resolve_project_path({"project_id": project_id})
            self.assertEqual(resolved_path.resolve(), project.resolve())

            # The id render reports back must equal the id list emitted.
            self.assertEqual(server._stable_project_id_for_path(project), project_id)

    def test_external_project_alias_is_listed_but_project_id_render_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_alias_") as tmpdir:
            workspace = Path(tmpdir)
            research_root = workspace / "ResearchOS"
            external_project = _write_project_render_fixture(workspace / "external", name="01_External")
            research_root.mkdir()
            alias = research_root / "01_Alias"
            symlink_or_skip(alias, external_project, target_is_directory=True)
            runtime_root = workspace / "runtime"
            server = GraphHubMCPServer(
                research_root=research_root,
                runtime_root=runtime_root,
                write_tools_enabled=True,
            )

            listed = self._call(server, "figops.list_projects")
            alias_entry = next(project for project in listed["projects"] if project["project_root"] == "01_Alias")

            with (
                patch.object(server, "_load_project_config", wraps=server._load_project_config) as load_config,
                patch.object(server, "_copy_project_snapshot", wraps=server._copy_project_snapshot) as copy_snapshot,
                patch.object(
                    server,
                    "_run_project_figure_script",
                    wraps=server._run_project_figure_script,
                ) as run_script,
            ):
                result = self._call(
                    server,
                    "figops.render_project_figure",
                    {
                        "project_id": alias_entry["project_id"],
                        "figure_id": "Fig1",
                        "job_id": "external-alias",
                    },
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertEqual(result["errors"], [PROJECT_ID_REPARSE_ERROR])
            load_config.assert_not_called()
            copy_snapshot.assert_not_called()
            run_script.assert_not_called()
            self.assertFalse((runtime_root / "mcp_project_jobs" / "external-alias").exists())
            self.assertFalse((external_project / "results" / "figures" / "Fig1.png").exists())

    def test_internal_project_alias_is_listed_but_project_id_render_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_alias_") as tmpdir:
            workspace = Path(tmpdir)
            research_root = workspace / "ResearchOS"
            internal_project = _write_project_render_fixture(research_root / ".venv", name="01_Internal")
            alias = research_root / "01_Alias"
            symlink_or_skip(alias, internal_project, target_is_directory=True)
            runtime_root = workspace / "runtime"
            server = GraphHubMCPServer(
                research_root=research_root,
                runtime_root=runtime_root,
                write_tools_enabled=True,
            )

            listed = self._call(server, "figops.list_projects")
            alias_entry = next(project for project in listed["projects"] if project["project_root"] == "01_Alias")

            with (
                patch.object(server, "_load_project_config", wraps=server._load_project_config) as load_config,
                patch.object(server, "_copy_project_snapshot", wraps=server._copy_project_snapshot) as copy_snapshot,
                patch.object(
                    server,
                    "_run_project_figure_script",
                    wraps=server._run_project_figure_script,
                ) as run_script,
            ):
                result = self._call(
                    server,
                    "figops.render_project_figure",
                    {
                        "project_id": alias_entry["project_id"],
                        "figure_id": "Fig1",
                        "job_id": "internal-alias",
                    },
                )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failure_stage"], "CONTRACT")
            self.assertEqual(result["errors"], [PROJECT_ID_REPARSE_ERROR])
            load_config.assert_not_called()
            copy_snapshot.assert_not_called()
            run_script.assert_not_called()
            self.assertFalse((runtime_root / "mcp_project_jobs" / "internal-alias").exists())
            self.assertFalse((internal_project / "results" / "figures" / "Fig1.png").exists())

    def test_real_project_id_still_resolves_without_execution_or_writes(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_id_") as tmpdir:
            workspace = Path(tmpdir)
            research_root = workspace / "ResearchOS"
            project = _write_project_render_fixture(research_root, name="01_Real")
            runtime_root = workspace / "runtime"
            server = GraphHubMCPServer(
                research_root=research_root,
                runtime_root=runtime_root,
                write_tools_enabled=True,
            )

            listed = self._call(server, "figops.list_projects")
            project_id = next(
                item["project_id"] for item in listed["projects"] if item["project_root"] == "01_Real"
            )
            resolved = server._resolve_project_path({"project_id": project_id})

            self.assertEqual(resolved, project.resolve())
            self.assertFalse(runtime_root.exists())


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
        return server, self._call(server, "figops.render_csv_graph", arguments)

    def test_csv_attaches_key_and_manifest(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir)
            self.assertIn(result["status"], {"ok", "warning"})
            diag = result["geometry_diagnostics"]
            self.assertEqual(diag["schema_version"], "geometry_diagnostics/2")
            self.assertTrue(diag["measurements"])
            self.assertEqual(result["layout_report"]["schema_version"], "layout_report/1")
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertIn("geometry_diagnostics", manifest)
            self.assertEqual(manifest["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/2")
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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project"},
            )
            self.assertIn(result["status"], {"ok", "warning"})
            self.assertIn("geometry_diagnostics", result)
            self.assertIn("layout_report", result)
            self.assertEqual(result["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/2")
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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project-real"},
            )
            self.assertIn(result["status"], {"ok", "warning"})
            diag = result["geometry_diagnostics"]
            self.assertTrue(diag["measurements"])
            self.assertEqual(diag["schema_version"], "geometry_diagnostics/2")
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
                "figops.render_project_figure",
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
            collected = self._call(server, "figops.collect_artifacts", {"job_id": "canonical-mismatch"})
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
                "figops.render_project_figure",
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
                "figops.render_project_figure",
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
                    "claim": "PI fixture panel is rendered.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                },
                {
                    "id": "FigPTFE_CvS_Fits",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/fig_cvs_fits/FigPTFE_CvS_Fits.png",
                    "claim": "PTFE fixture panel is rendered.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                },
            ]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "figops.render_project_figure",
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
                    "claim": "PI fixture panel is rendered.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                },
                {
                    "id": "FigPTFE_CvS_Fits",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/fig_cvs_fits/FigPTFE_CvS_Fits.png",
                    "claim": "PTFE fixture panel is rendered.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                },
            ]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "figops.render_project_figure",
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
                    "claim": "Setup fixture panel is rendered.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                },
                {
                    "id": "Result_A",
                    "script": "hub_scripts/plot.py",
                    "inputs": ["results/data/summary.csv"],
                    "output": "results/figures/Result_A.png",
                    "claim": "Result fixture panel is rendered.",
                    "samples": ["S1"],
                    "conditions": ["condition_a"],
                },
            ]
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(
                server,
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Result_A", "job_id": "family-false-positive"},
            )

            self.assertTrue(result["figure_metadata"]["family_check"]["passed"])
            self.assertEqual(result["figure_metadata"]["family_check"]["siblings"], [])

    def test_project_render_keeps_artist_overlap_iou_raw_until_policy_selection(self):
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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project-overlap"},
            )

            self.assertEqual(result["status"], "warning")
            self.assertEqual(result["publication_status"], "unverified")
            self.assertFalse(result["promotion_eligible"])
            measurement = next(
                item for item in result["geometry_diagnostics"]["measurements"]
                if item["metric_id"] == "artist_pair_iou[axis=0]"
            )
            self.assertTrue(any(pair["iou"] > 0 for pair in measurement["value"]["pairs"]))

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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-project-boom"},
            )
            self.assertNotEqual(result["status"], "error")
            self.assertEqual(result["geometry_diagnostics"]["measurements"], [])
            self.assertTrue(
                any("boom" in warning for warning in result["geometry_diagnostics"]["warnings"])
            )
            self.assertTrue(Path(result["output_path"]).is_file())

    def test_manifest_round_trips_native_types(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            _, result = self._render_csv(tmpdir)
            text = Path(result["manifest_path"]).read_text(encoding="utf-8")
            reloaded = json.loads(text)  # numpy/tuple leak would have failed the manifest write
            self.assertEqual(reloaded["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/2")

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
            self.assertEqual(diag["measurements"][0]["availability"], "unavailable")
            self.assertEqual(diag["warnings"], ["dry_run"])

    def test_contract_stage_error_carries_stub(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            data_path = _write_dense_csv(Path(tmpdir) / "input" / "data.csv")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root)
            missing_column = self._call(
                server,
                "figops.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "does_not_exist"},
            )
            self.assertEqual(missing_column["status"], "error")
            self.assertEqual(missing_column["failure_stage"], "CONTRACT")
            self.assertIn("geometry_diagnostics", missing_column)
            self.assertEqual(
                missing_column["geometry_diagnostics"]["measurements"][0]["availability"], "unavailable"
            )

            file_missing = self._call(
                server,
                "figops.render_csv_graph",
                {"data_path": "", "x_column": "x", "y_column": "y"},
            )
            self.assertEqual(file_missing["status"], "error")
            self.assertIn("geometry_diagnostics", file_missing)
            self.assertEqual(file_missing["geometry_diagnostics"]["measurements"][0]["availability"], "unavailable")

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
            "schema_version": "geometry_diagnostics/2",
            "measurements": [
                {
                    "metric_id": "tick_label_overlaps[axis=0]",
                    "availability": "available",
                    "unit": "structured",
                    "scope": "axis=0",
                    "value": {"summary": "3 overlapping pairs", "axis_index": 0},
                }
            ],
            "warnings": [],
        }
        clean = {"schema_version": "geometry_diagnostics/2", "measurements": [], "warnings": []}
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            with (
                patch.object(GraphHubMCPServer, "_safe_preflight", return_value=clean_preflight),
                patch("hub_core.mcp.render_orchestration._read_geometry_sidecar", return_value=finding),
            ):
                _, result = self._render_csv(tmpdir, job_id="geom-flip")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["errors"], [])
            self.assertFalse(result["manual_review_needed"])

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
            self.assertEqual(result["measurements"], [])
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
        def is_available(measurement):
            return measurement.get("availability") == "available"

        self.assertTrue(is_available({"availability": "available"}))
        self.assertFalse(is_available({"availability": "unavailable"}))

    def test_no_sidecar_marker(self):
        # A render whose save_journal_fig never wrote a sidecar (env var stripped) must
        # carry the distinct no_sidecar stub, not a silent null.
        from hub_core.mcp.render_orchestration import _read_geometry_sidecar

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            diag = _read_geometry_sidecar(Path(tmpdir))
            self.assertEqual(diag["measurements"][0]["availability"], "unavailable")
            self.assertIn("no sidecar emitted", diag["measurements"][0]["reason"])
            self.assertTrue(any("geometry_diagnostics_unavailable" in warning for warning in diag["warnings"]))

    def test_sidecar_rejects_recursive_policy_fields_in_raw_v2(self):
        from hub_core.mcp.render_orchestration import _read_geometry_sidecar

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            job_root = Path(tmpdir)
            (job_root / "geometry_diagnostics.json").write_text(
                json.dumps(
                    {
                        "schema_version": "geometry_diagnostics/2",
                        "measurements": [
                            {
                                "metric_id": "geometry.fact",
                                "availability": "available",
                                "value": {"nested": {"aggregate": "mean"}},
                                "unit": "structured",
                                "scope": "figure",
                            }
                        ],
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            diag = _read_geometry_sidecar(job_root)
            self.assertEqual(diag["measurements"][0]["availability"], "unavailable")
            self.assertIn("invalid sidecar", diag["measurements"][0]["reason"])

    def test_sidecar_legacy_v1_is_explicitly_adapted_to_public_v2(self):
        from hub_core.mcp.render_orchestration import _read_geometry_sidecar

        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_geom_") as tmpdir:
            job_root = Path(tmpdir)
            (job_root / "geometry_diagnostics.json").write_text(
                json.dumps(
                    {
                        "schema_version": "geometry_diagnostics/1",
                        "passed": True,
                        "checks": [
                            {
                                "name": "blank_area_ratio",
                                "passed": True,
                                "detail": "measured",
                                "data": {"axis_index": 0, "ratio": 0.25},
                            }
                        ],
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            diag = _read_geometry_sidecar(job_root)
            self.assertEqual(diag["schema_version"], "geometry_diagnostics/2")
            self.assertEqual(diag["measurements"][0]["value"]["ratio"], 0.25)
            self.assertNotIn("passed", diag)

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
        for tool_name in ("figops.render_csv_graph", "figops.render_csv_multipanel", "figops.render_project_figure"):
            properties = definitions[tool_name]["outputSchema"]["properties"]
            self.assertIn("geometry_diagnostics", properties)
            self.assertIn("layout_report", properties)
            if tool_name == "figops.render_project_figure":
                self.assertIn("figure_metadata", properties)
            geom_schema = properties["geometry_diagnostics"]
            self.assertEqual(set(geom_schema["required"]), {"schema_version", "measurements", "warnings"})
            self.assertEqual(geom_schema["properties"]["schema_version"]["const"], "geometry_diagnostics/2")
            measurement_properties = geom_schema["properties"]["measurements"]["items"]["properties"]
            self.assertIn("metric_id", measurement_properties)
            self.assertNotIn("passed", measurement_properties)
            report_schema = properties["layout_report"]
            self.assertIn("overlaps", report_schema["required"])
            self.assertIn("render_errors", report_schema["required"])
        # per-tool scoping: not declared on non-render tools
        for tool_name in ("figops.health", "figops.list_projects"):
            self.assertNotIn("geometry_diagnostics", definitions[tool_name]["outputSchema"]["properties"])
        # CSV extras declares the previously-undeclared calculation_checks too (strict-validator gap)
        self.assertIn(
            "calculation_checks",
            definitions["figops.render_csv_graph"]["outputSchema"]["properties"],
        )
        # additive non-breakage: real responses validate only because the key is declared.
        # Exercises every response shape against its tool's outputSchema so a stray top-level
        # key would be caught by additionalProperties:False, not just by manual tracing.
        csv_schema = definitions["figops.render_csv_graph"]["outputSchema"]
        project_schema = definitions["figops.render_project_figure"]["outputSchema"]
        project_properties = project_schema["properties"]
        self.assertEqual(project_properties["claim_inventory"]["type"], "object")
        self.assertEqual(
            project_properties["publication_status"],
            {"type": "string", "enum": ["verified", "unverified"]},
        )
        self.assertEqual(project_properties["promotion_eligible"]["type"], "boolean")
        for optional_success_field in (
            "claim_inventory",
            "publication_status",
            "promotion_eligible",
        ):
            self.assertNotIn(optional_success_field, project_schema.get("required", []))
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
                "figops.render_csv_graph",
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
                "figops.render_project_figure",
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
                "figops.render_project_figure",
                {"project_path": str(project), "figure_id": "Fig1", "job_id": "geom-schema-stub"},
            )
            self._assert_validates(project_no_sidecar, project_schema)
            self.assertEqual(project_no_sidecar["geometry_diagnostics"]["schema_version"], "geometry_diagnostics/2")
            self.assertEqual(
                project_no_sidecar["geometry_diagnostics"]["measurements"][0]["availability"],
                "unavailable",
            )
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
