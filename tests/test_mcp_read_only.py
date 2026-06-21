import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from io import BytesIO
from pathlib import Path

from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS
from hub_core.mcp import GraphHubMCPServer, McpServerConfig
from hub_core.mcp.config import ROOT_ADAPTER_SECURITY_ENV_VARS
from hub_core.mcp.schemas import list_tool_definitions
from hub_core.mcp.transport import (
    JSONRPC_INVALID_REQUEST,
    _dispatch_json_rpc,
    _handle_json_rpc,
    _matches_json_schema_type,
    _validate_tool_arguments,
    run_stdio_server,
)
from hub_core.project_discovery import ProjectDiscoveryService
from themes.style_profiles import PROFILE_ALIASES, list_profiles

HUB_ROOT = Path(__file__).resolve().parent.parent


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
      dtypes: {{ x: float, y: float }}
pipeline:
  analysis:
    - script: hub_scripts/analysis.R
      inputs: ["data/raw.csv"]
      outputs: ["results/data/summary.csv"]
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    output: results/figures/Fig1.png
diagrams:
  - id: Diagram1
    script: hub_scripts/diagram.py
    output: results/figures/Diagram1.svg
"""


INVALID_CONFIG = """
project: {{}}
visual_style:
  target_format: baseline
data_contract:
  csv_checks:
    - required_columns: ["x"]
"""


def _snapshot_files(root: Path) -> dict[str, tuple[int, int]]:
    snapshot = {}
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [dirname for dirname in dirs if dirname != "__pycache__"]
        for filename in files:
            path = Path(current_root) / filename
            stat = path.stat()
            snapshot[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class ReadOnlyMCPTest(unittest.TestCase):
    def _write_project(self, root: Path, name: str, config_text: str = VALID_CONFIG) -> Path:
        project = root / name
        project.mkdir(parents=True, exist_ok=True)
        (project / "project_config.yaml").write_text(config_text.format(name=name), encoding="utf-8")
        return project

    def _write_legacy_project_context(self, project: Path) -> None:
        hub_scripts = project / "hub_scripts"
        hub_scripts.mkdir(parents=True, exist_ok=True)
        (hub_scripts / "project_context.py").write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "\n"
            "def setup_hub_path() -> Path:\n"
            "    hub_path = Path(__file__).resolve().parents[3] / '[Graph_making_hub]'\n"
            "    if str(hub_path) not in sys.path:\n"
            "        sys.path.insert(0, str(hub_path))\n"
            "    return hub_path\n",
            encoding="utf-8",
        )

    def _write_legacy_project(self, root: Path, name: str) -> Path:
        project = root / name
        config_dir = project / "scripts"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "project_config.yaml").write_text(VALID_CONFIG.format(name=name), encoding="utf-8")
        return project

    def _call(self, server: GraphHubMCPServer, tool_name: str, arguments: dict | None = None) -> dict:
        response = server.call_tool(tool_name, arguments or {})
        self.assertIn("structuredContent", response)
        self.assertIn("content", response)
        self.assertEqual(json.loads(response["content"][0]["text"]), response["structuredContent"])
        return response["structuredContent"]

    def test_server_runs_with_explicit_config_and_no_special_env(self):
        with (
            tempfile.TemporaryDirectory(prefix="graph_hub_mcp_explicit_") as tmpdir,
            unittest.mock.patch.dict(os.environ, {}, clear=True),
        ):
            root = Path(tmpdir)
            research_root = root / "research"
            runtime_root = root / "runtime"
            extra_root = root / "extra_data"
            research_root.mkdir()
            extra_root.mkdir()
            config = McpServerConfig(
                hub_path=HUB_ROOT,
                research_root=research_root,
                runtime_root=runtime_root,
                write_tools_enabled=False,
                allowed_data_roots=(extra_root,),
            )

            server = GraphHubMCPServer(config=config)
            health = self._call(server, "graphhub.health")

        self.assertEqual(server.research_root, research_root.resolve())
        self.assertEqual(server.runtime_root, runtime_root.resolve())
        self.assertIn(extra_root.resolve(), server.allowed_data_roots)
        self.assertFalse(server.write_tools_enabled)
        self.assertEqual(health["runtime_root"], str(runtime_root.resolve()))

    def test_env_trust_model_documents_root_adapter_security_env_vars(self):
        trust_model = (HUB_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        missing = [name for name in sorted(ROOT_ADAPTER_SECURITY_ENV_VARS) if f"`{name}`" not in trust_model]

        self.assertEqual(missing, [])

    def test_read_only_mcp_import_does_not_require_bridge_renderer(self):
        runtime_root = str(Path(tempfile.gettempdir()) / "graph_hub_mcp_no_bridge")
        code = f"""
import importlib.abc
import sys

class BlockBridgeRenderer(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "plotting.bridge_renderer":
            raise RuntimeError("bridge renderer import attempted")
        return None

sys.meta_path.insert(0, BlockBridgeRenderer())
from hub_core.mcp import GraphHubMCPServer
server = GraphHubMCPServer(runtime_root={runtime_root!r})
result = server.call_tool("graphhub.health", {{}})
assert result["structuredContent"]["status"] in ("ok", "warning")
"""
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=HUB_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_tool_definitions_include_read_only_tools_and_schemas(self):
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}

        self.assertTrue(
            {
                "graphhub.health",
                "graphhub.describe",
                "graphhub.list_styles",
                "graphhub.list_projects",
                "graphhub.inspect_project",
                "graphhub.validate_project",
            }.issubset(set(definitions))
        )
        for tool in definitions.values():
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertEqual(tool["outputSchema"]["type"], "object")

    def test_list_styles_uses_graph_hub_canonical_contract(self):
        server = GraphHubMCPServer()

        result = self._call(server, "graphhub.list_styles")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["target_formats"], sorted(ALLOWED_TARGET_FORMATS))
        self.assertEqual(result["output_formats"], sorted(ALLOWED_OUTPUT_FORMATS))
        self.assertEqual(result["profiles"], list_profiles())
        self.assertEqual(result["profile_aliases"], dict(sorted(PROFILE_ALIASES.items())))
        self.assertIn("style_packs", result)
        self.assertTrue(any(pack["name"] == "surfur_internal" for pack in result["style_packs"]))
        self.assertIn("nature_surfur", result["target_formats"])

    def test_describe_exposes_registry_backed_capabilities(self):
        server = GraphHubMCPServer()
        definitions = {tool["name"]: tool for tool in list_tool_definitions()}

        result = self._call(server, "graphhub.describe")
        described_tools = {tool["name"]: tool for tool in result["tools"]}
        described_plot_types = {plot_type["name"]: plot_type for plot_type in result["plot_types"]}
        render_plot_enum = definitions["graphhub.render_csv_graph"]["inputSchema"]["properties"]["plot_type"]["enum"]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(set(described_tools), set(definitions))
        self.assertEqual(set(described_plot_types), set(render_plot_enum))
        self.assertIn("arg_schema", described_plot_types["heatmap"])
        self.assertIn("capabilities", described_plot_types["heatmap"])
        self.assertIn("z_column", described_plot_types["heatmap"]["arg_schema"]["required"])
        self.assertEqual(
            described_plot_types["heatmap"]["worked_example"]["arguments"]["z_column"],
            "z",
        )
        self.assertIn("range", {check["name"] for check in result["semantic_checks"]})
        described_semantic_checks = {check["name"]: check for check in result["semantic_checks"]}
        self.assertIn("monotonic_within_group", described_semantic_checks)
        self.assertIn("expected_sample_count", described_semantic_checks)
        self.assertIn("unit_coherence", described_semantic_checks)
        described_domain_helpers = {helper["name"]: helper for helper in result["domain_helpers"]}
        self.assertIn("materials_polymer.signal_smooth_baseline", described_domain_helpers)
        self.assertIn("materials_polymer.resistivity_transform", described_domain_helpers)
        self.assertIn("params_schema", described_domain_helpers["materials_polymer.resistivity_transform"])

    def test_read_only_tools_use_fixture_root_without_writing_files(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "01_Valid")
            self._write_project(root, "02_Invalid", INVALID_CONFIG)
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_files(root)

            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root, write_tools_enabled=False)
            health = self._call(server, "graphhub.health", {"root": str(root)})
            projects = self._call(server, "graphhub.list_projects", {"root": str(root), "max_depth": 3})

            after = _snapshot_files(root)
            self.assertEqual(after, before)
            self.assertFalse((root / "workspace_state.md").exists())
            self.assertFalse((root / "workspace_state.json").exists())
            self.assertFalse((runtime_root / "mcp_jobs").exists())

            self.assertEqual(health["status"], "ok")
            self.assertFalse(health["write_tools_enabled"])
            self.assertEqual(health["discovery_status"]["project_count"], 2)
            self.assertEqual(health["discovery_status"]["invalid_count"], 1)

            by_path = {project["project_root"]: project for project in projects["projects"]}
            discovery_paths = {project.path for project in ProjectDiscoveryService(root).discover(max_depth=3)}
            self.assertEqual(set(by_path), {"01_Valid", "02_Invalid"})
            self.assertEqual(set(by_path), discovery_paths)
            self.assertEqual(by_path["01_Valid"]["status"], "valid")
            self.assertEqual(by_path["02_Invalid"]["status"], "invalid")
            self.assertEqual(by_path["01_Valid"]["declared_figures"], 1)
            self.assertEqual(by_path["01_Valid"]["declared_diagrams"], 1)

    def test_write_tool_guard_blocks_dispatch_when_disabled(self):
        server = GraphHubMCPServer(write_tools_enabled=False)

        health = self._call(server, "graphhub.health")
        styles = self._call(server, "graphhub.list_styles")
        blocked = server.call_tool(
            "graphhub.scaffold_project",
            {"project_name": "Blocked", "project_root": "/tmp/blocked", "dry_run": True},
        )

        self.assertFalse(health["write_tools_enabled"])
        self.assertEqual(styles["status"], "ok")
        self.assertTrue(blocked["isError"])
        self.assertEqual(blocked["structuredContent"]["status"], "error")
        self.assertIn("Write tools are disabled", blocked["structuredContent"]["errors"][0])

    def test_write_tools_fail_closed_by_default(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED", None)
            server = GraphHubMCPServer()
            self.assertFalse(server.write_tools_enabled)
            blocked = server.call_tool(
                "graphhub.scaffold_project",
                {"project_name": "Blocked", "project_root": "/tmp/blocked", "dry_run": True},
            )
        self.assertTrue(blocked["isError"])

    def test_write_tools_enabled_via_env_opt_in(self):
        with (
            unittest.mock.patch.dict(os.environ, {"GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED": "1"}),
            tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir,
        ):
            server = GraphHubMCPServer()
            self.assertTrue(server.write_tools_enabled)
            # Witness that the write guard does not block a write tool when enabled.
            result = server.call_tool(
                "graphhub.scaffold_project",
                {"project_name": "Allowed", "project_root": str(Path(tmpdir) / "Allowed"), "dry_run": True},
            )
        self.assertNotIn(
            "Write tools are disabled",
            " ".join(result["structuredContent"].get("errors", [])),
        )

    def test_allowed_data_roots_drop_bad_env_entries_and_warn(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_roots_") as tmpdir:
            root = Path(tmpdir)
            valid_extra = root / "extra"
            valid_extra.mkdir()
            missing = root / "missing"
            runtime_root = root / "runtime"
            raw_roots = os.pathsep.join(["relative-root", str(missing), str(valid_extra)])

            with unittest.mock.patch.dict(
                os.environ,
                {"GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS": raw_roots},
                clear=False,
            ):
                server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
                health = self._call(server, "graphhub.health")

            self.assertIn(valid_extra.resolve(), server.allowed_data_roots)
            self.assertNotIn(Path("relative-root").resolve(), server.allowed_data_roots)
            self.assertNotIn(missing.resolve(), server.allowed_data_roots)
            self.assertEqual(health["status"], "warning")
            self.assertTrue(any("not absolute" in warning for warning in health["warnings"]))
            self.assertTrue(any("does not exist" in warning for warning in health["warnings"]))

    def test_allowed_data_roots_warn_for_broad_root_and_refuse_in_strict_mode(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_broad_") as tmpdir:
            root = Path(tmpdir)
            runtime_root = root / "runtime"

            with unittest.mock.patch.dict(
                os.environ,
                {"GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS": os.path.abspath(os.sep)},
                clear=False,
            ):
                server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
                health = self._call(server, "graphhub.health")

            broad_root = Path(os.path.abspath(os.sep)).resolve()
            self.assertIn(broad_root, server.allowed_data_roots)
            self.assertTrue(any("broad data root" in warning for warning in health["warnings"]))

            with unittest.mock.patch.dict(
                os.environ,
                {
                    "GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS": os.path.abspath(os.sep),
                    "GRAPH_HUB_MCP_STRICT_ROOTS": "1",
                },
                clear=False,
            ):
                strict_server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)
                strict_health = self._call(strict_server, "graphhub.health")

            self.assertNotIn(broad_root, strict_server.allowed_data_roots)
            self.assertTrue(any("refused broad data root" in warning for warning in strict_health["warnings"]))

    def test_default_allowed_data_roots_keep_data_paths_contained(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_containment_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            root.mkdir()
            outside = Path(tmpdir) / "outside.csv"
            outside.write_text("x,y\n1,2\n", encoding="utf-8")
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

            with self.assertRaises(ValueError):
                server._resolve_allowed_data_path(str(outside), field_name="data_path")

    def test_scan_root_rejects_root_outside_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            research_root = Path(tmpdir) / "research"
            research_root.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            server = GraphHubMCPServer(research_root=research_root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(server, "graphhub.list_projects", {"root": str(outside)})
            self.assertEqual(result["status"], "error")
            self.assertIn("root must stay under", result["errors"][0])

    def test_inspect_project_rejects_project_path_outside_research_root(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            research_root = Path(tmpdir) / "research"
            research_root.mkdir()
            server = GraphHubMCPServer(research_root=research_root, runtime_root=Path(tmpdir) / "runtime")
            result = self._call(server, "graphhub.inspect_project", {"project_path": "/etc"})
            self.assertEqual(result["status"], "error")
            self.assertIn("project_path must stay under", result["errors"][0])

    def test_list_projects_preserves_legacy_and_ephemeral_statuses(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_legacy_project(root, "03_Legacy")
            self._write_project(root, ".worktrees/feature/04_Worktree")

            with unittest.mock.patch.dict(os.environ, {"GRAPH_HUB_CONVENTIONS_ADAPTER": "surfur"}, clear=False):
                server = GraphHubMCPServer(research_root=Path(tmpdir))
                result = self._call(
                    server,
                    "graphhub.list_projects",
                    {"root": str(root), "include_worktrees": True, "include_ephemeral": True, "max_depth": 5},
                )

                by_path = {project["project_root"]: project for project in result["projects"]}
                self.assertEqual(by_path["03_Legacy"]["status"], "legacy")
                self.assertEqual(by_path[".worktrees/feature/04_Worktree"]["status"], "ephemeral")

                inspected = self._call(
                    server,
                    "graphhub.inspect_project",
                    {
                        "root": str(root),
                        "project_id": by_path[".worktrees/feature/04_Worktree"]["project_id"],
                        "include_worktrees": True,
                        "include_ephemeral": True,
                        "max_depth": 5,
                    },
                )
            self.assertEqual(inspected["status"], "ok")
            self.assertEqual(inspected["style_summary"]["target_format"], "nature_surfur")

    def test_inspect_and_validate_project_do_not_execute_or_write(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = self._write_project(root, "01_Valid")
            before = _snapshot_files(root)

            server = GraphHubMCPServer(research_root=Path(tmpdir))
            inspected = self._call(server, "graphhub.inspect_project", {"project_path": str(project)})
            validated = self._call(server, "graphhub.validate_project", {"project_path": str(project)})

            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(inspected["status"], "ok")
            self.assertEqual(inspected["project_metadata"]["name"], "01_Valid")
            self.assertEqual(inspected["style_summary"]["target_format"], "nature_surfur")
            self.assertEqual(inspected["pipeline_steps"]["analysis"], 1)
            self.assertEqual(inspected["figure_outputs"], ["results/figures/Fig1.png"])
            self.assertEqual(inspected["diagram_outputs"], ["results/figures/Diagram1.svg"])
            self.assertEqual(inspected["missing_outputs"], ["results/figures/Fig1.png", "results/figures/Diagram1.svg"])

            self.assertEqual(validated["status"], "ok")
            self.assertTrue(validated["valid"])
            self.assertEqual(validated["config_errors"], [])
            self.assertEqual(validated["data_contract_errors"], [])
            self.assertEqual(validated["style_errors"], [])
            self.assertEqual(validated["recommended_next_action"], "ready_for_render")

    def test_validate_project_warns_about_legacy_project_context_without_executing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = self._write_project(root, "01_Legacy_Context")
            self._write_legacy_project_context(project)
            before = _snapshot_files(root)

            server = GraphHubMCPServer(research_root=Path(tmpdir))
            validated = self._call(server, "graphhub.validate_project", {"project_path": str(project)})

            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(validated["status"], "warning")
            self.assertTrue(validated["valid"])
            self.assertEqual(validated["recommended_next_action"], "ready_for_render")
            self.assertTrue(
                any(
                    "RESEARCH_HUB_PATH" in warning and "project_context.py" in warning
                    for warning in validated["warnings"]
                )
            )

    def test_validate_project_naming_lint_warns_without_failing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = self._write_project(root, "저항 측정/26013_bad_date")

            server = GraphHubMCPServer(research_root=Path(tmpdir))
            validated = self._call(
                server,
                "graphhub.validate_project",
                {"project_path": str(project), "include_naming_lint": True},
            )
            inspected = self._call(
                server,
                "graphhub.inspect_project",
                {"project_path": str(project), "include_naming_lint": True},
            )

            self.assertTrue(validated["valid"])
            self.assertEqual(validated["config_errors"], [])
            self.assertTrue(validated["naming_lint"]["warnings"])
            self.assertEqual(inspected["naming_lint"], validated["naming_lint"])
            self.assertTrue(any("YYMMDD" in warning for warning in validated["warnings"]))

    def test_validate_project_naming_lint_accepts_conforming_names(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = self._write_project(root, "저항 측정/260130/PET_control")

            server = GraphHubMCPServer(research_root=Path(tmpdir))
            validated = self._call(
                server,
                "graphhub.validate_project",
                {"project_path": str(project), "include_naming_lint": True},
            )

            self.assertTrue(validated["valid"])
            self.assertEqual(validated["naming_lint"]["warnings"], [])

    def test_json_rpc_tools_list_and_call_return_structured_content(self):
        server = GraphHubMCPServer()

        listed = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        called = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "graphhub.list_styles", "arguments": {}},
            },
        )

        listed_tools = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("graphhub.health", listed_tools)
        self.assertIn("graphhub.describe", listed_tools)
        self.assertIn("structuredContent", called["result"])
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(called["result"]["structuredContent"]["target_formats"], sorted(ALLOWED_TARGET_FORMATS))

    def test_json_rpc_initialize_advertises_resources_and_prompts(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 10, "method": "initialize"})

        capabilities = response["result"]["capabilities"]
        self.assertIn("tools", capabilities)
        self.assertIn("resources", capabilities)
        self.assertIn("prompts", capabilities)

    def test_json_rpc_resources_and_prompts_list(self):
        server = GraphHubMCPServer()

        resources = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 11, "method": "resources/list"})
        templates = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 12, "method": "resources/templates/list"})
        prompts = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 13, "method": "prompts/list"})

        self.assertIn("graphhub://styles", {item["uri"] for item in resources["result"]["resources"]})
        self.assertIn(
            "graphhub://projects/{project_id}/config",
            {item["uriTemplate"] for item in templates["result"]["resourceTemplates"]},
        )
        self.assertIn("make_publication_graph_from_csv", {item["name"] for item in prompts["result"]["prompts"]})
        self.assertIn("render_project_figure", {item["name"] for item in prompts["result"]["prompts"]})

    def test_resources_read_styles_matches_list_styles(self):
        server = GraphHubMCPServer()

        resource = _handle_json_rpc(
            server,
            {"jsonrpc": "2.0", "id": 20, "method": "resources/read", "params": {"uri": "graphhub://styles"}},
        )
        styles = server.call_tool("graphhub.list_styles", {})["structuredContent"]
        content = resource["result"]["contents"][0]
        payload = json.loads(content["text"])

        self.assertEqual(content["mimeType"], "application/json")
        self.assertEqual(payload["target_formats"], styles["target_formats"])
        self.assertIn("nature_surfur", payload["target_formats"])

    def test_resources_read_projects_and_legacy_config_are_read_only(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_resource_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            self._write_project(root, "01_Valid")
            self._write_legacy_project(root, "02_Legacy")
            runtime_root = Path(tmpdir) / "runtime"
            before = _snapshot_files(root)
            server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

            projects_response = _handle_json_rpc(
                server,
                {"jsonrpc": "2.0", "id": 21, "method": "resources/read", "params": {"uri": "graphhub://projects"}},
            )
            projects_payload = json.loads(projects_response["result"]["contents"][0]["text"])
            legacy_project = next(project for project in projects_payload["projects"] if project["status"] == "legacy")
            config_response = _handle_json_rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 22,
                    "method": "resources/read",
                    "params": {"uri": f"graphhub://projects/{legacy_project['project_id']}/config"},
                },
            )

            self.assertEqual(_snapshot_files(root), before)
            self.assertFalse((runtime_root / "mcp_jobs").exists())
            self.assertEqual(projects_payload["count"], 2)
            self.assertIn("project:", config_response["result"]["contents"][0]["text"])
            self.assertEqual(config_response["result"]["contents"][0]["mimeType"], "application/x-yaml")

    def test_resources_read_job_manifest_after_render(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_resource_") as tmpdir:
            data_path = Path(tmpdir) / "input" / "data.csv"
            data_path.parent.mkdir(parents=True)
            data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
            runtime_root = Path(tmpdir) / "runtime"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=runtime_root, write_tools_enabled=True)
            rendered = self._call(
                server,
                "graphhub.render_csv_graph",
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "resource-render"},
            )

            response = _handle_json_rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 23,
                    "method": "resources/read",
                    "params": {"uri": "graphhub://jobs/resource-render/manifest"},
                },
            )
            payload = json.loads(response["result"]["contents"][0]["text"])

            self.assertEqual(rendered["job_id"], "resource-render")
            self.assertEqual(payload["job_id"], "resource-render")
            self.assertEqual(response["result"]["contents"][0]["mimeType"], "application/json")
            self.assertNotIn(str(runtime_root), response["result"]["contents"][0]["text"])
            self.assertNotIn(str(data_path), response["result"]["contents"][0]["text"])
            self.assertEqual(payload["source_data_path"], "input://data_path")

    def test_resources_read_errors_distinguish_malformed_and_missing(self):
        server = GraphHubMCPServer()

        malformed_uris = [
            "graphhub://styles/",
            "graphhub://jobs/missing-job/manifest/",
            "graphhub://jobs/missing-job//manifest",
            "graphhub://projects/%2E%2E/config",
            "graphhub://projects/foo%2Fbar/config",
            "graphhub://styles?x=1",
        ]
        missing = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 25,
                "method": "resources/read",
                "params": {"uri": "graphhub://jobs/missing-job/manifest"},
            },
        )

        for uri in malformed_uris:
            with self.subTest(uri=uri):
                malformed = _handle_json_rpc(
                    server,
                    {"jsonrpc": "2.0", "id": 24, "method": "resources/read", "params": {"uri": uri}},
                )
                self.assertEqual(malformed["error"]["code"], -32602)
        self.assertEqual(missing["error"]["code"], -32002)

    def test_resources_read_project_config_refuses_symlinked_config(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_resource_") as tmpdir:
            root = Path(tmpdir) / "ResearchOS"
            project = root / "01_Symlink"
            project.mkdir(parents=True)
            secret = Path(tmpdir) / ".env"
            secret.write_text(
                "SECRET_TOKEN=do-not-read\nvisual_style:\n  target_format: super_secret\n",
                encoding="utf-8",
            )
            (project / "project_config.yaml").symlink_to(secret)
            server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
            projects_response = _handle_json_rpc(
                server,
                {"jsonrpc": "2.0", "id": 26, "method": "resources/read", "params": {"uri": "graphhub://projects"}},
            )
            projects_payload = json.loads(projects_response["result"]["contents"][0]["text"])
            project_id = projects_payload["projects"][0]["project_id"]

            response = _handle_json_rpc(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": 27,
                    "method": "resources/read",
                    "params": {"uri": f"graphhub://projects/{project_id}/config"},
                },
            )

            self.assertEqual(response["error"]["code"], -32602)
            self.assertNotIn("SECRET_TOKEN", json.dumps(response))
            self.assertNotIn("SECRET_TOKEN", projects_response["result"]["contents"][0]["text"])
            self.assertNotIn("super_secret", projects_response["result"]["contents"][0]["text"])
            self.assertEqual(projects_payload["projects"][0]["target_format"], "")

    def test_json_rpc_rejects_non_object_params(self):
        server = GraphHubMCPServer()

        resource_response = _handle_json_rpc(
            server,
            {"jsonrpc": "2.0", "id": 28, "method": "resources/read", "params": "bad"},
        )
        prompt_response = _handle_json_rpc(
            server,
            {"jsonrpc": "2.0", "id": 29, "method": "prompts/get", "params": "bad"},
        )

        self.assertEqual(resource_response["error"]["code"], -32602)
        self.assertEqual(prompt_response["error"]["code"], -32602)

    def test_prompts_get_publication_graph_workflow(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "prompts/get",
                "params": {
                    "name": "make_publication_graph_from_csv",
                    "arguments": {"data_path": "data.csv", "x_column": "x", "y_column": "y"},
                },
            },
        )
        text = response["result"]["messages"][0]["content"]["text"]

        self.assertIn("graphhub.render_csv_graph", text)
        self.assertIn("dry_run=true", text)
        self.assertIn("calculation_checks", text)
        self.assertIn("visual_preflight_status", text)
        self.assertIn("graphhub.collect_artifacts", text)
        self.assertIn("manual_review_needed", text)

    def test_prompts_get_project_figure_workflow_mentions_project_render(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "prompts/get",
                "params": {
                    "name": "render_project_figure",
                    "arguments": {"project_path": "project", "figure_id": "Fig1"},
                },
            },
        )
        text = response["result"]["messages"][0]["content"]["text"]

        self.assertIn("graphhub.inspect_project", text)
        self.assertIn("graphhub.validate_project", text)
        self.assertIn("graphhub.render_project_figure", text)
        self.assertIn("dry_run=true", text)
        self.assertIn("graphhub.collect_artifacts", text)
        self.assertIn("manual_review_needed", text)

    def test_prompts_get_validation_errors(self):
        server = GraphHubMCPServer()

        missing_arg = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "prompts/get",
                "params": {"name": "make_publication_graph_from_csv", "arguments": {"data_path": "data.csv"}},
            },
        )
        unknown_prompt = _handle_json_rpc(
            server,
            {"jsonrpc": "2.0", "id": 32, "method": "prompts/get", "params": {"name": "missing_prompt"}},
        )
        missing_selector = _handle_json_rpc(
            server,
            {"jsonrpc": "2.0", "id": 33, "method": "prompts/get", "params": {"name": "inspect_graph_project_quality"}},
        )
        missing_project_render_selector = _handle_json_rpc(
            server,
            {"jsonrpc": "2.0", "id": 34, "method": "prompts/get", "params": {"name": "render_project_figure"}},
        )

        self.assertEqual(missing_arg["error"]["code"], -32602)
        self.assertEqual(unknown_prompt["error"]["code"], -32002)
        self.assertEqual(missing_selector["error"]["code"], -32602)
        self.assertEqual(missing_project_render_selector["error"]["code"], -32602)

    def test_json_rpc_unknown_tool_returns_protocol_error(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "graphhub.nope", "arguments": {}},
            },
        )

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("Unknown tool", response["error"]["message"])

    def test_json_rpc_notifications_never_return_response(self):
        server = GraphHubMCPServer()

        initialized = _handle_json_rpc(server, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        unknown = _handle_json_rpc(server, {"jsonrpc": "2.0", "method": "missing/method"})
        invalid_params = _handle_json_rpc(server, {"jsonrpc": "2.0", "method": "tools/call", "params": "bad"})

        self.assertIsNone(initialized)
        self.assertIsNone(unknown)
        self.assertIsNone(invalid_params)

    def test_json_schema_number_type_rejects_bool_and_unknown_types(self):
        self.assertTrue(_matches_json_schema_type(1.5, "number"))
        self.assertTrue(_matches_json_schema_type(1, "number"))
        self.assertFalse(_matches_json_schema_type(True, "number"))
        self.assertFalse(_matches_json_schema_type("1", "number"))
        self.assertFalse(_matches_json_schema_type("x", "unknown"))

    def _call_rpc(self, server: GraphHubMCPServer, tool_name: str, arguments: dict) -> dict:
        return _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )

    def test_json_rpc_validation_errors_include_taxonomy_data(self):
        server = GraphHubMCPServer()

        response = self._call_rpc(server, "graphhub.list_projects", {"max_depth": 99})

        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(
            response["error"]["data"],
            {"category": "validation", "code": "GRAPHHUB_VALIDATION", "jsonrpc_code": -32602},
        )

    def test_json_rpc_not_found_errors_include_taxonomy_data(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 98,
                "method": "resources/read",
                "params": {"uri": "graphhub://jobs/missing-job/manifest"},
            },
        )

        self.assertEqual(response["error"]["code"], -32002)
        self.assertEqual(
            response["error"]["data"],
            {"category": "not_found", "code": "GRAPHHUB_NOT_FOUND", "jsonrpc_code": -32002},
        )

    def test_tool_disabled_errors_include_taxonomy_fields(self):
        server = GraphHubMCPServer(write_tools_enabled=False)

        response = server.call_tool(
            "graphhub.scaffold_project",
            {"project_name": "Blocked", "project_root": "/tmp/blocked", "dry_run": True},
        )

        structured = response["structuredContent"]
        self.assertTrue(response["isError"])
        self.assertEqual(structured["status"], "error")
        self.assertEqual(structured["error_category"], "disabled")
        self.assertEqual(structured["error_code"], "GRAPHHUB_DISABLED")
        self.assertEqual(structured["jsonrpc_code"], -32600)

    def test_tool_internal_errors_include_taxonomy_fields(self):
        server = GraphHubMCPServer()

        def fail(_arguments):
            raise RuntimeError("boom")

        server._handlers["graphhub.health"] = fail
        response = server.call_tool("graphhub.health", {})

        structured = response["structuredContent"]
        self.assertTrue(response["isError"])
        self.assertEqual(structured["status"], "error")
        self.assertEqual(structured["error_category"], "internal")
        self.assertEqual(structured["error_code"], "GRAPHHUB_INTERNAL")
        self.assertEqual(structured["jsonrpc_code"], -32603)

    def test_rpc_rejects_max_depth_above_advertised_maximum(self):
        server = GraphHubMCPServer()

        response = self._call_rpc(server, "graphhub.health", {"max_depth": 999})

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("max_depth", response["error"]["message"])
        self.assertIn("<= 12", response["error"]["message"])

    def test_rpc_rejects_max_depth_below_advertised_minimum(self):
        server = GraphHubMCPServer()

        response = self._call_rpc(server, "graphhub.health", {"max_depth": 0})

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn(">= 1", response["error"]["message"])

    def test_rpc_rejects_max_projects_above_advertised_maximum(self):
        server = GraphHubMCPServer()

        response = self._call_rpc(server, "graphhub.batch_check", {"max_projects": 99})

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("max_projects", response["error"]["message"])

    def test_rpc_accepts_in_range_numeric_bounds(self):
        server = GraphHubMCPServer()

        response = self._call_rpc(server, "graphhub.health", {"max_depth": 12})

        self.assertNotIn("error", response)
        self.assertIn("result", response)

    def test_rpc_rejects_out_of_enum_target_format(self):
        server = GraphHubMCPServer()

        response = self._call_rpc(
            server,
            "graphhub.render_csv_graph",
            {"data_path": "a.csv", "x_column": "x", "y_column": "y", "target_format": "made_up_format"},
        )

        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("target_format", response["error"]["message"])

    def test_rpc_accepts_in_enum_profile_alias(self):
        argument_errors = _validate_tool_arguments(
            "graphhub.render_csv_graph",
            {"data_path": "a.csv", "x_column": "x", "y_column": "y", "profile": "premium"},
        )

        self.assertEqual(argument_errors, [])

    def test_validate_accepts_mixed_case_case_normalized_enums(self):
        # Handler lowercases profile/target_format/output_format, so the enum check
        # must accept mixed-case input it would normalize rather than reject it.
        argument_errors = _validate_tool_arguments(
            "graphhub.render_csv_graph",
            {
                "data_path": "a.csv",
                "x_column": "x",
                "y_column": "y",
                "profile": "Premium",
                "target_format": "Nature",
                "output_format": "PNG",
            },
        )

        self.assertEqual(argument_errors, [])

    def test_validate_rejects_render_project_figure_without_selector(self):
        argument_errors = _validate_tool_arguments(
            "graphhub.render_project_figure",
            {"figure_id": "Fig1"},
        )

        self.assertTrue(any("exactly one" in error for error in argument_errors))

    def test_validate_rejects_render_project_figure_with_both_selectors(self):
        argument_errors = _validate_tool_arguments(
            "graphhub.render_project_figure",
            {"project_id": "01_Demo", "project_path": "/tmp/demo", "figure_id": "Fig1"},
        )

        self.assertTrue(any("exactly one" in error for error in argument_errors))

    def test_validate_accepts_render_project_figure_with_single_selector(self):
        argument_errors = _validate_tool_arguments(
            "graphhub.render_project_figure",
            {"project_id": "01_Demo", "figure_id": "Fig1"},
        )

        self.assertEqual(argument_errors, [])

    def test_health_status_is_warning_when_discovery_root_missing(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_") as tmpdir:
            missing = Path(tmpdir) / "ResearchOS"
            server = GraphHubMCPServer(research_root=Path(tmpdir), runtime_root=Path(tmpdir) / "runtime")

            health = self._call(server, "graphhub.health", {"root": str(missing)})

            self.assertEqual(health["status"], "warning")
            self.assertTrue(health["warnings"])
            self.assertIn("warning", health["summary"].lower())
            self.assertIn("does not exist", health["warnings"][0])

    def test_read_stdio_message_rejects_negative_content_length_without_draining(self):
        from hub_core.mcp.transport import _read_stdio_message

        body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
        stream = BytesIO(b"Content-Length: -1\r\n\r\n" + body)
        with self.assertRaises(ValueError):
            _read_stdio_message(stream)
        # Must reject before reading: a negative size would otherwise drain the whole stream.
        self.assertEqual(stream.read(), body)

    def test_read_stdio_message_rejects_oversized_content_length_without_draining(self):
        from hub_core.mcp.transport import MCP_MAX_MESSAGE_BYTES, _read_stdio_message

        oversize = MCP_MAX_MESSAGE_BYTES + 1
        stream = BytesIO(b"Content-Length: " + str(oversize).encode("ascii") + b"\r\n\r\nshort")
        with self.assertRaises(ValueError):
            _read_stdio_message(stream)
        self.assertEqual(stream.read(), b"short")

    def test_stdio_server_accepts_content_length_framed_messages(self):
        request = {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
        body = json.dumps(request).encode("utf-8")
        input_stream = BytesIO(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
        output_stream = BytesIO()

        rc = run_stdio_server(GraphHubMCPServer(), input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        raw_output = output_stream.getvalue()
        header, payload = raw_output.split(b"\r\n\r\n", 1)
        self.assertIn(b"Content-Length:", header)
        response = json.loads(payload.decode("utf-8"))
        self.assertEqual(response["id"], 4)
        self.assertEqual(response["result"]["tools"][0]["name"], "graphhub.health")

    def test_stdio_handler_stdout_does_not_leak_into_the_wire(self):
        import contextlib
        import io

        server = GraphHubMCPServer()
        original_call_tool = server.call_tool

        def printing_call_tool(*args, **kwargs):
            print("POISON_WIRE")  # a stray handler print must not reach fd1
            return original_call_tool(*args, **kwargs)

        request = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "graphhub.health", "arguments": {}},
        }
        body = json.dumps(request).encode("utf-8")
        input_stream = BytesIO(b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
        output_stream = BytesIO()
        process_stdout = io.StringIO()

        with unittest.mock.patch.object(server, "call_tool", side_effect=printing_call_tool):
            with contextlib.redirect_stdout(process_stdout):
                rc = run_stdio_server(server, input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        # The handler's print went to stderr, not the process stdout / framed response.
        self.assertNotIn("POISON_WIRE", process_stdout.getvalue())
        self.assertNotIn(b"POISON_WIRE", output_stream.getvalue())
        _, payload = output_stream.getvalue().split(b"\r\n\r\n", 1)
        self.assertEqual(json.loads(payload.decode("utf-8"))["id"], 7)

    def test_stdio_server_mirrors_newline_delimited_messages(self):
        request = {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}
        input_stream = BytesIO(json.dumps(request).encode("utf-8") + b"\n")
        output_stream = BytesIO()

        rc = run_stdio_server(GraphHubMCPServer(), input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        raw_output = output_stream.getvalue()
        self.assertNotIn(b"Content-Length:", raw_output)
        self.assertTrue(raw_output.endswith(b"\n"))
        response = json.loads(raw_output.decode("utf-8"))
        self.assertEqual(response["id"], 5)
        self.assertEqual(response["result"]["tools"][0]["name"], "graphhub.health")

    def test_stdio_server_reports_malformed_content_length_frame(self):
        input_stream = BytesIO(b"Content-Length: nope\r\n\r\n{}")
        output_stream = BytesIO()

        rc = run_stdio_server(GraphHubMCPServer(), input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        header, payload = output_stream.getvalue().split(b"\r\n\r\n", 1)
        self.assertIn(b"Content-Length:", header)
        response = json.loads(payload.decode("utf-8"))
        self.assertEqual(response["error"]["code"], -32603)
        self.assertIn("Invalid Content-Length", response["error"]["message"])

    def test_stdio_server_frames_newline_parse_error_as_newline(self):
        input_stream = BytesIO(b"{bad json\n")
        output_stream = BytesIO()

        rc = run_stdio_server(GraphHubMCPServer(), input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        raw_output = output_stream.getvalue()
        self.assertFalse(raw_output.startswith(b"Content-Length:"))
        self.assertNotIn(b"Content-Length:", raw_output)
        self.assertTrue(raw_output.endswith(b"\n"))
        response = json.loads(raw_output.decode("utf-8"))
        self.assertEqual(response["error"]["code"], -32700)
        self.assertIn("Parse error", response["error"]["message"])

    def test_mcp_server_smoke_cli_reports_read_only_status(self):
        completed = subprocess.run(
            [sys.executable, "graphhub_mcp_server.py", "--smoke"],
            cwd=HUB_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["tool_surface"], "graphhub_mcp")
        self.assertGreater(payload["style_format_count"], 0)


class JsonRpcProtocolTest(unittest.TestCase):
    def test_batch_request_returns_array_of_responses_with_matching_ids(self):
        server = GraphHubMCPServer()

        batch = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "graphhub.list_styles", "arguments": {}},
            },
        ]
        responses = _dispatch_json_rpc(server, batch)

        self.assertIsInstance(responses, list)
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertGreater(len(responses[0]["result"]["tools"]), 0)
        self.assertIn("structuredContent", responses[1]["result"])

    def test_batch_of_only_notifications_returns_nothing(self):
        server = GraphHubMCPServer()

        batch = [
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "notifications/cancelled"},
        ]
        self.assertIsNone(_dispatch_json_rpc(server, batch))

    def test_empty_batch_is_invalid_request(self):
        server = GraphHubMCPServer()

        response = _dispatch_json_rpc(server, [])

        self.assertEqual(response["error"]["code"], JSONRPC_INVALID_REQUEST)

    def test_stdio_server_reads_newline_framed_batch_as_one_message(self):
        batch = [
            {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 8, "method": "resources/list"},
        ]
        input_stream = BytesIO(json.dumps(batch).encode("utf-8") + b"\n")
        output_stream = BytesIO()

        rc = run_stdio_server(GraphHubMCPServer(), input_stream=input_stream, output_stream=output_stream)

        self.assertEqual(rc, 0)
        responses = json.loads(output_stream.getvalue().decode("utf-8"))
        self.assertEqual([response["id"] for response in responses], [7, 8])

    def test_fractional_id_is_invalid_request(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 1.5, "method": "tools/list"})

        self.assertEqual(response["error"]["code"], JSONRPC_INVALID_REQUEST)
        self.assertIsNone(response["id"])

    def test_wrong_jsonrpc_version_is_invalid_request(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(server, {"jsonrpc": "1.0", "id": 3, "method": "tools/list"})

        self.assertEqual(response["error"]["code"], JSONRPC_INVALID_REQUEST)
        self.assertEqual(response["id"], 3)

    def test_missing_jsonrpc_field_is_invalid_request(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(server, {"id": 1, "method": "tools/list"})

        self.assertEqual(response["error"]["code"], JSONRPC_INVALID_REQUEST)

    def test_valid_integer_and_string_ids_still_work(self):
        server = GraphHubMCPServer()

        int_id = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 42, "method": "tools/list"})
        str_id = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": "abc", "method": "tools/list"})

        self.assertEqual(int_id["id"], 42)
        self.assertEqual(str_id["id"], "abc")

    def test_bool_id_is_invalid_request(self):
        server = GraphHubMCPServer()

        response = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": True, "method": "tools/list"})

        self.assertEqual(response["error"]["code"], JSONRPC_INVALID_REQUEST)
        self.assertIsNone(response["id"])

    def test_ping_before_initialize_returns_empty_result(self):
        server = GraphHubMCPServer(require_initialize=True)

        response = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 1, "method": "ping"})

        self.assertNotIn("error", response)
        self.assertEqual(response["result"], {})
        self.assertEqual(response["id"], 1)

    def test_require_initialize_rejects_pre_initialize_call_then_succeeds(self):
        server = GraphHubMCPServer(require_initialize=True)

        rejected = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "graphhub.list_styles", "arguments": {}},
            },
        )
        self.assertEqual(rejected["error"]["code"], JSONRPC_INVALID_REQUEST)
        self.assertEqual(rejected["id"], 1)

        init = _handle_json_rpc(
            server, {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}
        )
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        self.assertTrue(server.initialized)

        accepted = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "graphhub.list_styles", "arguments": {}},
            },
        )
        self.assertIn("structuredContent", accepted["result"])

    def test_lenient_server_allows_pre_initialize_calls(self):
        server = GraphHubMCPServer()
        self.assertFalse(server.require_initialize)

        response = _handle_json_rpc(
            server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "graphhub.list_styles", "arguments": {}},
            },
        )
        self.assertIn("structuredContent", response["result"])

    def test_stdio_server_require_initialize_rejects_then_accepts_tools_list(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        ]
        input_bytes = b"".join(json.dumps(message).encode("utf-8") + b"\n" for message in messages)
        input_stream = BytesIO(input_bytes)
        output_stream = BytesIO()

        rc = run_stdio_server(
            GraphHubMCPServer(require_initialize=True),
            input_stream=input_stream,
            output_stream=output_stream,
        )

        self.assertEqual(rc, 0)
        responses = [json.loads(line) for line in output_stream.getvalue().decode("utf-8").splitlines() if line]
        by_id = {response["id"]: response for response in responses}
        self.assertEqual(by_id[1]["error"]["code"], JSONRPC_INVALID_REQUEST)
        self.assertEqual(by_id[2]["result"]["protocolVersion"], "2025-06-18")
        self.assertGreater(len(by_id[3]["result"]["tools"]), 0)


if __name__ == "__main__":
    unittest.main()
