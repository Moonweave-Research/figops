# Project-Aware MCP Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `graphhub.render_project_figure`, an MCP tool that renders one `project_config.yaml` figure from an existing Graph Hub project while preserving runtime-root isolation, structured artifacts, failure taxonomy, and provenance.

**Architecture:** Reuse Graph Hub's existing project discovery, config validation, style contract, process runner, preflight, artifact collection, and provenance conventions. The MCP tool must not write into source research projects by default: it copies the selected project into `runtime_root/mcp_project_jobs/<job_id>/project`, runs only the selected figure pipeline there, and returns the same envelope shape used by `graphhub.render_csv_graph`. Source-project rendering can be considered later as an explicit non-default mode, but is out of scope for this slice.

**Tech Stack:** Python 3.12, stdlib JSON-RPC MCP surface, `pytest`, `ruff`, existing `ProjectDiscoveryService`, `hub_core.config_parser`, `hub_core.process_runner`, `hub_core.figure_preflight`, and `hub_core.mcp_surface.GraphHubMCPServer`.

---

## Current Gap

`graphhub.render_csv_graph` is implemented and tested, but it only supports ad hoc CSV graph jobs. The default Graph Hub user workflow is project-aware: an agent discovers a project, inspects `project_config.yaml`, chooses a configured `figures[]` entry, renders it, collects artifacts, and reviews manifest/status/provenance. MCP cannot yet do that without dropping back to the CLI or Athena legacy bridge.

This is the final promotion blocker for using Graph Hub MCP as the default graph surface.

## Non-Goals

- Do not make Athena call this tool in the same slice.
- Do not render every figure in a project.
- Do not mutate source project folders by default.
- Do not add a new plotting engine.
- Do not support raw-instrument preprocessing.
- Do not implement source-project writes unless a later spec defines explicit user approval semantics.

## File Map

- Modify: `hub_core/mcp_surface.py`
  - Add `graphhub.render_project_figure` tool definition.
  - Add `GraphHubMCPServer.render_project_figure()`.
  - Add helpers for figure selection, project snapshot creation, output redirection, process execution, and project render provenance.
- Modify: `tests/test_mcp_rendering.py`
  - Add runtime-isolation, failure-taxonomy, provenance, and collect-artifacts tests for project-aware render.
- Modify: `tests/test_mcp_read_only.py`
  - Assert `tools/list` includes `graphhub.render_project_figure` and schemas expose required fields.
- Modify: `docs/hks/00_agent_graph_workflow.md`
  - Add direct project-render workflow step.
- Modify: `docs/hks/05_mcp_tool_playbook.md`
  - Add tool sequence for project-aware figure rendering.
- Modify: `docs/02-design/graph_hub_independent_completion_spec_20260608.md`
  - Mark the project-aware render blocker resolved after implementation.

## Tool Contract

Tool name:

```text
graphhub.render_project_figure
```

Input schema:

```json
{
  "type": "object",
  "properties": {
    "project_id": {"type": "string"},
    "project_path": {"type": "string"},
    "root": {"type": "string"},
    "figure_id": {"type": "string"},
    "figure_output": {"type": "string"},
    "target_format": {"type": "string"},
    "profile": {"type": "string"},
    "output_format": {"type": "string"},
    "dry_run": {"type": "boolean", "default": false},
    "overwrite": {"type": "boolean", "default": false},
    "job_id": {"type": "string"},
    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4}
  },
  "additionalProperties": false
}
```

Selection rules:

- Exactly one of `project_id` or `project_path` should normally be supplied. If both are supplied, they must resolve to the same project.
- `figure_id` selects `figures[].id`.
- `figure_output` selects `figures[].output`.
- If neither `figure_id` nor `figure_output` is supplied and the project has exactly one figure, select it.
- If neither is supplied and the project has multiple figures, return `status=error`, `failure_stage=CONTRACT`, and list available figure selectors.
- `target_format`, `profile`, and `output_format` are optional runtime overrides applied only inside the runtime snapshot.

Output fields must include the standard MCP envelope plus:

```json
{
  "job_id": "project-render-demo",
  "project_id": "02_Surfur_Polymer__...",
  "source_project_path": "research://02_Surfur_Polymer/...",
  "job_root": "runtime://mcp_project_jobs/project-render-demo",
  "snapshot_project_path": "runtime://mcp_project_jobs/project-render-demo/project",
  "selected_figure": {
    "id": "Fig1",
    "script": "hub_scripts/plot.py",
    "output": "results/figures/Fig1.png"
  },
  "output_path": "runtime://mcp_project_jobs/project-render-demo/project/results/figures/Fig1.png",
  "config_path": "runtime://mcp_project_jobs/project-render-demo/project/project_config.yaml",
  "manifest_path": ".../manifest.json",
  "status_path": ".../status.json",
  "latest_dir": ".../_latest/mcp_project_render",
  "latest_alias": ".../_latest/mcp_project_render",
  "style_summary": {},
  "visual_preflight_status": {},
  "artifact_status": "ready|manual_review_needed|failed",
  "baseline_comparison": {},
  "provenance": {},
  "failure_stage": "CONFIG|CONTRACT|EXPORT|TIMEOUT|PLOT",
  "resolution_hint": ""
}
```

## Task 1: Tool Definition And Selection Tests

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_read_only.py`
- Modify: `tests/test_mcp_rendering.py`

- [ ] **Step 1: Add failing tool-list schema test**

Add this test to `tests/test_mcp_read_only.py`:

```python
def test_tool_definitions_include_project_aware_render_tool(self):
    definitions = {tool["name"]: tool for tool in list_tool_definitions()}

    tool = definitions["graphhub.render_project_figure"]
    properties = tool["inputSchema"]["properties"]
    output_properties = tool["outputSchema"]["properties"]

    assert "project_id" in properties
    assert "project_path" in properties
    assert "figure_id" in properties
    assert "figure_output" in properties
    assert "job_id" in properties
    assert "selected_figure" in output_properties
    assert "snapshot_project_path" in output_properties
    assert "provenance" in output_properties
    assert "failure_stage" in output_properties
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_tool_definitions_include_project_aware_render_tool -q
```

Expected:

```text
KeyError: 'graphhub.render_project_figure'
```

- [ ] **Step 3: Add tool name and schema**

In `hub_core/mcp_surface.py`, add the tool name next to `graphhub.render_csv_graph`:

```python
TOOL_NAMES = (
    "graphhub.health",
    "graphhub.list_styles",
    "graphhub.list_projects",
    "graphhub.inspect_project",
    "graphhub.validate_project",
    "graphhub.render_csv_graph",
    "graphhub.render_project_figure",
    "graphhub.collect_artifacts",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
WRITE_TOOL_NAMES = (
    "graphhub.render_csv_graph",
    "graphhub.render_project_figure",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
```

Add a `ToolDefinition` after `graphhub.render_csv_graph`:

```python
ToolDefinition(
    "graphhub.render_project_figure",
    "Render one configured project figure in an isolated runtime-root MCP job workspace.",
    _object_schema(
        {
            "project_id": {"type": "string"},
            "project_path": {"type": "string"},
            "root": root_arg,
            "figure_id": {"type": "string"},
            "figure_output": {"type": "string"},
            "target_format": {"type": "string"},
            "profile": {"type": "string"},
            "output_format": {"type": "string"},
            "dry_run": {"type": "boolean", "default": False},
            "overwrite": {"type": "boolean", "default": False},
            "job_id": {"type": "string"},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
        }
    ),
    _standard_output_schema(
        {
            "job_id": {"type": "string"},
            "project_id": {"type": "string"},
            "source_project_path": {"type": "string"},
            "job_root": {"type": "string"},
            "snapshot_project_path": {"type": "string"},
            "selected_figure": {"type": "object"},
            "output_path": {"type": "string"},
            "config_path": {"type": "string"},
            "style_summary": {"type": "object"},
            "visual_preflight_status": {"type": "object"},
            "artifact_status": {"type": "string"},
            "baseline_comparison": {"type": "object"},
            "provenance": {"type": "object"},
        }
    ),
),
```

Register the handler in `GraphHubMCPServer.__init__`:

```python
self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "graphhub.health": self.health,
    "graphhub.list_styles": self.list_styles,
    "graphhub.list_projects": self.list_projects,
    "graphhub.inspect_project": self.inspect_project,
    "graphhub.validate_project": self.validate_project,
    "graphhub.render_csv_graph": self.render_csv_graph,
    "graphhub.render_project_figure": self.render_project_figure,
    "graphhub.collect_artifacts": self.collect_artifacts,
    "graphhub.scaffold_project": self.scaffold_project,
    "graphhub.normalize_project_structure": self.normalize_project_structure,
    "graphhub.batch_check": self.batch_check,
}
```

Temporarily add this stub so the server can instantiate:

```python
def render_project_figure(self, arguments: dict[str, Any]) -> dict[str, Any]:
    return self._envelope(
        "graphhub.render_project_figure",
        arguments,
        status="error",
        summary="Project-aware render is not implemented.",
        errors=["Project-aware render is not implemented."],
        manual_review_needed=True,
        failure_stage="CONFIG",
        resolution_hint="Implement render_project_figure before using this tool.",
        artifact_status="failed",
        baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
    )
```

- [ ] **Step 4: Run the schema test**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_tool_definitions_include_project_aware_render_tool -q
```

Expected:

```text
1 passed
```

## Task 2: Project And Figure Selector Contract

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_rendering.py`

- [ ] **Step 1: Add selector error tests**

Add helper config near the existing render tests:

```python
PROJECT_RENDER_CONFIG = """
project:
  name: "Project Render Demo"
visual_style:
  target_format: nature_surfur
  profile: baseline
figures:
  - id: FigA
    script: hub_scripts/plot_a.py
    output: results/figures/FigA.png
  - id: FigB
    script: hub_scripts/plot_b.py
    output: results/figures/FigB.png
"""
```

Add tests:

```python
def test_render_project_figure_requires_figure_selector_when_multiple_figures(self):
    with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
        root = Path(tmpdir) / "ResearchOS"
        project = root / "01_Project"
        project.mkdir(parents=True)
        (project / "project_config.yaml").write_text(PROJECT_RENDER_CONFIG, encoding="utf-8")
        server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

        result = self._call(server, "graphhub.render_project_figure", {"project_path": str(project)})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["failure_stage"], "CONTRACT")
        self.assertIn("figure_id", result["resolution_hint"])
        self.assertIn("FigA", result["errors"][0])
        self.assertFalse((Path(tmpdir) / "runtime" / "mcp_project_jobs").exists())


def test_render_project_figure_rejects_unknown_figure_id(self):
    with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
        root = Path(tmpdir) / "ResearchOS"
        project = root / "01_Project"
        project.mkdir(parents=True)
        (project / "project_config.yaml").write_text(PROJECT_RENDER_CONFIG, encoding="utf-8")
        server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

        result = self._call(
            server,
            "graphhub.render_project_figure",
            {"project_path": str(project), "figure_id": "FigMissing"},
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["failure_stage"], "CONTRACT")
        self.assertIn("FigMissing", result["errors"][0])
        self.assertFalse((Path(tmpdir) / "runtime" / "mcp_project_jobs").exists())
```

- [ ] **Step 2: Run selector tests and verify failure**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_requires_figure_selector_when_multiple_figures tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_rejects_unknown_figure_id -q
```

Expected:

```text
FAILED ... failure_stage mismatch
```

- [ ] **Step 3: Implement selector helpers**

Add these helpers to `GraphHubMCPServer`:

```python
def _project_figure_entries(self, config: dict[str, Any]) -> list[dict[str, Any]]:
    figures = config.get("figures")
    if not isinstance(figures, list):
        return []
    return [dict(item) for item in figures if isinstance(item, dict)]

def _select_project_figure(
    self,
    figures: list[dict[str, Any]],
    *,
    figure_id: str = "",
    figure_output: str = "",
) -> tuple[dict[str, Any] | None, list[str]]:
    if figure_id:
        matches = [figure for figure in figures if str(figure.get("id") or "") == figure_id]
        if len(matches) == 1:
            return matches[0], []
        return None, [f"Unknown figure_id '{figure_id}'. Available: {self._figure_selector_summary(figures)}"]
    if figure_output:
        matches = [figure for figure in figures if str(figure.get("output") or "") == figure_output]
        if len(matches) == 1:
            return matches[0], []
        return None, [f"Unknown figure_output '{figure_output}'. Available: {self._figure_selector_summary(figures)}"]
    if len(figures) == 1:
        return figures[0], []
    if not figures:
        return None, ["Project config has no figures[] entries."]
    return None, [f"Project has multiple figures. Provide figure_id or figure_output. Available: {self._figure_selector_summary(figures)}"]

@staticmethod
def _figure_selector_summary(figures: list[dict[str, Any]]) -> str:
    parts = []
    for figure in figures:
        parts.append(f"id={figure.get('id', '')}, output={figure.get('output', '')}")
    return "; ".join(parts)
```

Update `render_project_figure()` to load config and return selector errors:

```python
def render_project_figure(self, arguments: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(arguments.get("dry_run", False))
    try:
        project_path = self._resolve_project_path(arguments)
    except Exception as exc:
        return self._envelope(
            "graphhub.render_project_figure",
            arguments,
            status="error",
            summary="Project selection failed.",
            errors=[str(exc)],
            manual_review_needed=True,
            is_dry_run=dry_run,
            failure_stage="CONTRACT",
            resolution_hint="Provide a valid project_id or project_path.",
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
        )
    loaded = self._load_project_config(project_path, allow_invalid=True)
    config = loaded["config"] if isinstance(loaded["config"], dict) else {}
    config_errors = validate_config(config) if isinstance(config, dict) else list(loaded["errors"])
    if config_errors:
        return self._envelope(
            "graphhub.render_project_figure",
            arguments,
            status="error",
            summary="Project config is invalid.",
            errors=config_errors,
            manual_review_needed=True,
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Fix project_config.yaml before rendering through MCP.",
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
        )
    figures = self._project_figure_entries(config)
    selected, selector_errors = self._select_project_figure(
        figures,
        figure_id=str(arguments.get("figure_id") or "").strip(),
        figure_output=str(arguments.get("figure_output") or "").strip(),
    )
    if selected is None:
        return self._envelope(
            "graphhub.render_project_figure",
            arguments,
            status="error",
            summary="Project figure selection failed.",
            errors=selector_errors,
            manual_review_needed=True,
            is_dry_run=dry_run,
            failure_stage="CONTRACT",
            resolution_hint="Provide figure_id or figure_output for the configured figure.",
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
        )
    return self._envelope(
        "graphhub.render_project_figure",
        arguments,
        status="error",
        summary="Project figure selected but render execution is not implemented.",
        errors=["Project figure execution is not implemented."],
        manual_review_needed=True,
        is_dry_run=dry_run,
        failure_stage="PLOT",
        resolution_hint="Implement runtime snapshot execution.",
        artifact_status="failed",
        selected_figure=selected,
        baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
    )
```

- [ ] **Step 4: Run selector tests**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_requires_figure_selector_when_multiple_figures tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_rejects_unknown_figure_id -q
```

Expected:

```text
2 passed
```

## Task 3: Dry-Run Project Render Planning

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_rendering.py`

- [ ] **Step 1: Add dry-run test**

Add this test:

```python
def test_render_project_figure_dry_run_validates_without_writing_runtime(self):
    with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
        root = Path(tmpdir) / "ResearchOS"
        project = root / "01_Project"
        project.mkdir(parents=True)
        (project / "project_config.yaml").write_text(
            PROJECT_RENDER_CONFIG.replace(
                "  - id: FigB\n    script: hub_scripts/plot_b.py\n    output: results/figures/FigB.png\n",
                "",
            ),
            encoding="utf-8",
        )
        server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")

        result = self._call(
            server,
            "graphhub.render_project_figure",
            {"project_path": str(project), "dry_run": True, "job_id": "project-dry-run"},
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["is_dry_run"])
        self.assertEqual(result["job_id"], "project-dry-run")
        self.assertEqual(result["selected_figure"]["id"], "FigA")
        self.assertEqual(result["failure_stage"], "")
        self.assertFalse((Path(tmpdir) / "runtime").exists())
```

- [ ] **Step 2: Run dry-run test and verify failure**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_dry_run_validates_without_writing_runtime -q
```

Expected:

```text
FAILED ... status == 'error'
```

- [ ] **Step 3: Implement dry-run response**

After successful figure selection, add:

```python
job_id = self._render_job_id(arguments.get("job_id"))
job_root = self.runtime_root / "mcp_project_jobs" / job_id
snapshot_project_path = job_root / "project"
output_relpath = str(selected.get("output") or "")
output_path = snapshot_project_path / output_relpath
if dry_run:
    return self._envelope(
        "graphhub.render_project_figure",
        arguments,
        status="ok",
        summary="Project figure render validated in dry-run mode; no files were created.",
        manual_review_needed=False,
        is_dry_run=True,
        job_id=job_id,
        project_id=self._stable_project_id_for_path(project_path),
        source_project_path=self._display_path(project_path),
        job_root=str(job_root),
        snapshot_project_path=str(snapshot_project_path),
        selected_figure=self._public_selected_figure(selected),
        output_path=str(output_path),
        config_path=str(snapshot_project_path / loaded["config_relpath"]),
        manifest_path=str(job_root / "manifest.json"),
        status_path=str(job_root / "status.json"),
        latest_dir=str(self.runtime_root / "_latest" / "mcp_project_render"),
        latest_alias=str(self.runtime_root / "_latest" / "mcp_project_render"),
        style_summary=self._selected_figure_style_summary(config, selected, arguments),
        visual_preflight_status={"passed": None, "checks": [], "warnings": ["dry_run"]},
        failure_stage="",
        resolution_hint="",
        artifact_status="validated",
        baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
        provenance={},
    )
```

Add helpers:

```python
def _stable_project_id_for_path(self, project_path: Path) -> str:
    for project in ProjectDiscoveryService(self.research_root).discover(max_depth=12):
        if (self.research_root / project.path).resolve() == project_path.resolve():
            return project.project_id
    return self._operation_id("graphhub.project", {"project_path": str(project_path)})

@staticmethod
def _public_selected_figure(figure: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(figure.get("id") or ""),
        "script": str(figure.get("script") or ""),
        "output": str(figure.get("output") or ""),
    }

def _selected_figure_style_summary(
    self,
    config: dict[str, Any],
    figure: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
    return {
        "target_format": str(arguments.get("target_format") or figure.get("target_format") or figure.get("theme") or visual_style.get("target_format") or "nature").lower(),
        "profile": str(arguments.get("profile") or figure.get("profile") or visual_style.get("profile") or DEFAULT_PROFILE),
        "output_format": str(arguments.get("output_format") or figure.get("format") or figure.get("output_format") or Path(str(figure.get("output") or "")).suffix.lstrip(".") or "png").lower(),
    }
```

- [ ] **Step 4: Run dry-run test**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_dry_run_validates_without_writing_runtime -q
```

Expected:

```text
1 passed
```

## Task 4: Runtime Snapshot Execution

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_rendering.py`

- [ ] **Step 1: Add execution test with a Python plot script**

Add:

```python
def test_render_project_figure_runs_selected_figure_in_runtime_snapshot(self):
    with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
        root = Path(tmpdir) / "ResearchOS"
        project = root / "01_Project"
        script = project / "hub_scripts" / "plot_a.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "from pathlib import Path\n"
            "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
            "Path('results/figures/FigA.png').write_bytes(b'png')\n",
            encoding="utf-8",
        )
        (project / "project_config.yaml").write_text(
            PROJECT_RENDER_CONFIG.replace(
                "  - id: FigB\n    script: hub_scripts/plot_b.py\n    output: results/figures/FigB.png\n",
                "",
            ),
            encoding="utf-8",
        )
        runtime_root = Path(tmpdir) / "runtime"
        server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

        result = self._call(
            server,
            "graphhub.render_project_figure",
            {"project_path": str(project), "job_id": "project-render-demo"},
        )

        self.assertIn(result["status"], {"ok", "warning"})
        self.assertFalse((project / "results").exists())
        self.assertTrue(Path(result["output_path"]).is_file())
        self.assertTrue(str(Path(result["output_path"]).resolve()).startswith(str(runtime_root.resolve())))
        self.assertTrue(Path(result["manifest_path"]).is_file())
        self.assertTrue(Path(result["status_path"]).is_file())
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["job_id"], "project-render-demo")
        self.assertEqual(manifest["selected_figure"]["id"], "FigA")
        self.assertIn("provenance", manifest)
        self.assertEqual(manifest["provenance"]["renderer_surface"], "graphhub.render_project_figure")
```

- [ ] **Step 2: Run execution test and verify failure**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_runs_selected_figure_in_runtime_snapshot -q
```

Expected:

```text
FAILED ... Project figure execution is not implemented
```

- [ ] **Step 3: Implement selective snapshot copy and selected script execution**

Add helpers:

```python
def _selected_figure_declared_inputs(self, selected_figure: dict[str, Any]) -> list[str]:
    raw_inputs = selected_figure.get("inputs") or selected_figure.get("input") or []
    if isinstance(raw_inputs, str):
        raw_inputs = [raw_inputs]
    if not isinstance(raw_inputs, list):
        return []
    return [str(item) for item in raw_inputs if isinstance(item, str) and item.strip()]

def _copy_project_snapshot(
    self,
    *,
    source_project: Path,
    snapshot_project: Path,
    config_relpath: str,
    selected_figure: dict[str, Any],
) -> list[str]:
    if snapshot_project.exists():
        shutil.rmtree(snapshot_project)
    snapshot_project.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    ignored_names = {".git", ".venv", "__pycache__", ".pytest_cache", ".dvc/cache"}

    def copy_relative_path(raw_relpath: str) -> None:
        relpath = Path(raw_relpath)
        if relpath.is_absolute() or ".." in relpath.parts:
            raise ValueError(f"Snapshot path must be project-relative: {raw_relpath}")
        source_path = source_project / relpath
        destination_path = snapshot_project / relpath
        if not source_path.exists():
            raise FileNotFoundError(f"Required project snapshot path not found: {raw_relpath}")
        if source_path.is_dir():
            shutil.copytree(
                source_path,
                destination_path,
                dirs_exist_ok=True,
                symlinks=False,
                ignore=shutil.ignore_patterns(*ignored_names),
            )
            return
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied.append(str(destination_path))

    copy_relative_path(config_relpath)
    script_rel = str(selected_figure.get("script") or "").split("::")[0]
    if script_rel:
        copy_relative_path(script_rel)
    for input_rel in self._selected_figure_declared_inputs(selected_figure):
        copy_relative_path(input_rel)
    for standard_folder in ("hub_scripts", "results/data"):
        source_folder = source_project / standard_folder
        if source_folder.is_dir():
            copy_relative_path(standard_folder)
    return [str(path) for path in snapshot_project.rglob("*") if path.is_file()]

def _run_project_figure_script(
    self,
    *,
    snapshot_project_path: Path,
    selected_figure: dict[str, Any],
    style_summary: dict[str, Any],
) -> None:
    script_rel = str(selected_figure.get("script") or "").split("::")[0]
    if not script_rel:
        raise ValueError("Selected figure has no script.")
    script_path = snapshot_project_path / script_rel
    if not script_path.is_file():
        raise FileNotFoundError(f"Selected figure script not found: {script_rel}")
    env = os.environ.copy()
    env.update(
        {
            "RESEARCH_HUB_PATH": str(self.hub_path),
            "PROJECT_ROOT": str(snapshot_project_path),
            "THEME_FORMAT": str(style_summary["target_format"]),
            "THEME_PROFILE": str(style_summary["profile"]),
            "THEME_OUTPUT_FORMAT": str(style_summary["output_format"]),
        }
    )
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(snapshot_project_path),
        text=True,
        capture_output=True,
        check=False,
        timeout=MCP_RENDER_TIMEOUT_SECONDS,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"Figure script exited {completed.returncode}.")
```

In `render_project_figure()`, for non-dry-run:

```python
self._activate_runtime_root_for_runtime_access()
job_root = self.runtime_root / "mcp_project_jobs" / job_id
snapshot_project_path = job_root / "project"
manifest_path = job_root / "manifest.json"
status_path = job_root / "status.json"
latest_dir = self.runtime_root / "_latest" / "mcp_project_render"
if job_root.exists() and not overwrite:
    return self._envelope(
        "graphhub.render_project_figure",
        arguments,
        status="error",
        summary="Project render job already exists.",
        errors=[f"Project render job already exists: {self._runtime_uri(job_root)}. Set overwrite=true to replace it."],
        manual_review_needed=True,
        is_dry_run=False,
        job_id=job_id,
        job_root=str(job_root),
        failure_stage="EXPORT",
        resolution_hint="Set overwrite=true to replace the existing MCP project render job.",
        artifact_status="failed",
        baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
    )
if job_root.exists() and overwrite:
    shutil.rmtree(job_root)
style_summary = self._selected_figure_style_summary(config, selected, arguments)
created_paths = self._copy_project_snapshot(
    source_project=project_path,
    snapshot_project=snapshot_project_path,
    config_relpath=str(loaded["config_path"].relative_to(project_path)),
    selected_figure=selected,
)
self._run_project_figure_script(
    snapshot_project_path=snapshot_project_path,
    selected_figure=selected,
    style_summary=style_summary,
)
output_path = snapshot_project_path / str(selected.get("output") or "")
if not output_path.is_file():
    raise FileNotFoundError(f"Selected figure output was not created: {selected.get('output')}")
```

Then write manifest/status using the same fields as `render_csv_graph`. Use `_rendered_figure_artifacts(output_path)`, `_safe_preflight(output_path, style_summary["target_format"])`, `_baseline_comparison(output_path, arguments.get("baseline_path"))`, and a new `_mcp_project_render_provenance()` helper.

- [ ] **Step 4: Run execution test**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_runs_selected_figure_in_runtime_snapshot -q
```

Expected:

```text
1 passed
```

## Task 5: Failure Taxonomy And Sanitization

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_rendering.py`

- [ ] **Step 1: Add script failure test**

Add:

```python
def test_render_project_figure_script_failure_writes_failure_artifacts(self):
    with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
        root = Path(tmpdir) / "ResearchOS"
        project = root / "01_Project"
        script = project / "hub_scripts" / "plot_a.py"
        script.parent.mkdir(parents=True)
        script.write_text("raise RuntimeError('plot failed')\n", encoding="utf-8")
        (project / "project_config.yaml").write_text(
            PROJECT_RENDER_CONFIG.replace(
                "  - id: FigB\n    script: hub_scripts/plot_b.py\n    output: results/figures/FigB.png\n",
                "",
            ),
            encoding="utf-8",
        )
        runtime_root = Path(tmpdir) / "runtime"
        server = GraphHubMCPServer(research_root=root, runtime_root=runtime_root)

        result = self._call(
            server,
            "graphhub.render_project_figure",
            {"project_path": str(project), "job_id": "project-failure"},
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["failure_stage"], "PLOT")
        self.assertTrue(result["manual_review_needed"])
        self.assertTrue(Path(result["manifest_path"]).is_file())
        self.assertTrue(Path(result["status_path"]).is_file())
        self.assertNotIn(str(tmpdir), json.dumps(result))
        self.assertIn("plot failed", result["errors"][0])
```

- [ ] **Step 2: Implement failure artifact writing**

Add a project variant of `_write_render_failure_artifacts()`:

```python
def _write_project_render_failure_artifacts(
    self,
    *,
    job_id: str,
    job_root: Path,
    snapshot_project_path: Path,
    selected_figure: dict[str, Any],
    manifest_path: Path,
    status_path: Path,
    latest_dir: Path,
    created_paths: list[str],
    failure_stage: str,
    resolution_hint: str,
) -> list[str]:
    created = list(created_paths)
    manifest = {
        "job_id": job_id,
        "job_root": str(job_root),
        "snapshot_project_path": str(snapshot_project_path),
        "selected_figure": self._public_selected_figure(selected_figure),
        "status_path": str(status_path),
        "latest_dir": str(latest_dir),
        "latest_alias": str(latest_dir),
        "figures": [],
        "diagrams": [],
        "assemblies": [],
        "logs": [],
        "created_paths": created,
        "modified_paths": [],
        "skipped_paths": [],
        "style_summary": {},
        "visual_preflight_status": {"passed": False, "checks": [], "warnings": ["project_render_failed"]},
        "failure_stage": failure_stage,
        "resolution_hint": resolution_hint,
        "artifact_status": "failed",
        "baseline_comparison": self._baseline_comparison(None, None),
        "manual_review_needed": True,
        "provenance": {},
    }
    status_payload = self._render_status_payload(
        job_id=job_id,
        status="error",
        summary="Project figure render failed.",
        manifest_path=manifest_path,
        output_path=snapshot_project_path / str(selected_figure.get("output") or ""),
        artifact_status="failed",
        manual_review_needed=True,
        failure_stage=failure_stage,
        resolution_hint=resolution_hint,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    status_path.write_text(json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    latest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, latest_dir / "manifest.json")
    shutil.copy2(status_path, latest_dir / "status.json")
    return created + [str(manifest_path), str(status_path)]
```

In the non-dry-run execution block, catch exceptions and map:

- `TimeoutError` or message containing `timed out` -> `TIMEOUT`
- `FileNotFoundError` for missing script/output -> `EXPORT`
- other script/runtime errors -> `PLOT`

- [ ] **Step 3: Run failure test**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_script_failure_writes_failure_artifacts -q
```

Expected:

```text
1 passed
```

## Task 6: Collect Artifacts For Project Render

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_rendering.py`

- [ ] **Step 1: Add collect test**

Add:

```python
def test_collect_artifacts_supports_project_render_provenance(self):
    with tempfile.TemporaryDirectory(prefix="graph_hub_mcp_project_render_") as tmpdir:
        root = Path(tmpdir) / "ResearchOS"
        project = root / "01_Project"
        script = project / "hub_scripts" / "plot_a.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "from pathlib import Path\n"
            "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
            "Path('results/figures/FigA.png').write_bytes(b'png')\n",
            encoding="utf-8",
        )
        (project / "project_config.yaml").write_text(
            PROJECT_RENDER_CONFIG.replace(
                "  - id: FigB\n    script: hub_scripts/plot_b.py\n    output: results/figures/FigB.png\n",
                "",
            ),
            encoding="utf-8",
        )
        server = GraphHubMCPServer(research_root=root, runtime_root=Path(tmpdir) / "runtime")
        self._call(
            server,
            "graphhub.render_project_figure",
            {"project_path": str(project), "job_id": "project-collect"},
        )

        collected = self._call(server, "graphhub.collect_artifacts", {"job_id": "project-collect"})

        self.assertIn(collected["status"], {"ok", "warning"})
        self.assertEqual(collected["job_id"], "project-collect")
        self.assertEqual(collected["provenance"]["renderer_surface"], "graphhub.render_project_figure")
        self.assertEqual(len(collected["figures"]), 1)
        self.assertTrue(Path(collected["figures"][0]["path"]).is_file())
```

- [ ] **Step 2: Run collect test**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_collect_artifacts_supports_project_render_provenance -q
```

Expected:

```text
1 passed
```

If this fails because `_find_job_manifest_path()` only looks under `mcp_jobs`, update it to search both:

```python
for jobs_dir_name in ("mcp_jobs", "mcp_project_jobs"):
    candidate = root / jobs_dir_name / job_id / "manifest.json"
```

## Task 7: Docs And Prompts

**Files:**
- Modify: `docs/hks/00_agent_graph_workflow.md`
- Modify: `docs/hks/05_mcp_tool_playbook.md`
- Modify: `docs/02-design/graph_hub_independent_completion_spec_20260608.md`
- Modify: `hub_core/mcp_surface.py`
- Modify: `tests/test_mcp_read_only.py`

- [ ] **Step 1: Add prompt/list expectations**

Update `test_prompts_get_publication_graph_workflow` or add a new prompt test:

```python
def test_prompts_get_project_figure_workflow_mentions_project_render(self):
    server = GraphHubMCPServer()

    response = _handle_json_rpc(
        server,
        {
            "jsonrpc": "2.0",
            "id": 40,
            "method": "prompts/get",
            "params": {
                "name": "render_project_figure",
                "arguments": {"project_id": "demo", "figure_id": "Fig1"},
            },
        },
    )
    text = response["result"]["messages"][0]["content"]["text"]

    self.assertIn("graphhub.inspect_project", text)
    self.assertIn("graphhub.validate_project", text)
    self.assertIn("graphhub.render_project_figure", text)
    self.assertIn("graphhub.collect_artifacts", text)
    self.assertIn("manual_review_needed", text)
```

- [ ] **Step 2: Implement prompt definition**

Add to `list_prompt_definitions()`:

```python
{
    "name": "render_project_figure",
    "description": "Workflow for rendering one configured project figure through Graph Hub MCP.",
    "arguments": [
        {"name": "project_id", "description": "Discovered Graph Hub project ID.", "required": False},
        {"name": "project_path", "description": "Project path.", "required": False},
        {"name": "figure_id", "description": "Configured figures[].id.", "required": False},
        {"name": "figure_output", "description": "Configured figures[].output.", "required": False},
    ],
}
```

Add `get_prompt()` branch:

```python
if name == "render_project_figure":
    if not (arguments.get("project_id") or arguments.get("project_path")):
        raise ValueError("render_project_figure requires project_id or project_path.")
    selector = arguments.get("figure_id") or arguments.get("figure_output") or "<single configured figure>"
    text = (
        "Project figure workflow:\n"
        "1. Call graphhub.inspect_project for the selected project.\n"
        "2. Call graphhub.validate_project and stop on status=error.\n"
        f"3. Call graphhub.render_project_figure for selector {selector!r} with dry_run=true first.\n"
        "4. If dry_run is clean, call graphhub.render_project_figure without dry_run.\n"
        "5. Call graphhub.collect_artifacts for the returned job_id.\n"
        "6. Report manifest_path, status_path, provenance, failure_stage, resolution_hint, and manual_review_needed.\n"
    )
    return self._prompt_payload(
        "Workflow for rendering one configured project figure through Graph Hub MCP.",
        text,
    )
```

- [ ] **Step 3: Update HKS docs**

In `docs/hks/00_agent_graph_workflow.md`, replace the render step block with:

```markdown
6. Call `graphhub.render_project_figure` for configured project figures.
7. Call `graphhub.render_csv_graph` for explicit structured CSV graph requests.
8. Call `graphhub.collect_artifacts` after render.
9. Inspect `manifest_path`, `status_path`, `failure_stage`, `resolution_hint`, `manual_review_needed`, `visual_preflight_status`, and `provenance`.
```

In `docs/hks/05_mcp_tool_playbook.md`, add:

```markdown
## Project Figure Render

User request:

```text
Render Fig1 for the sulfur resistance project using its project_config.yaml style.
```

Tool sequence:

```text
graphhub.list_projects
graphhub.inspect_project
graphhub.validate_project
graphhub.render_project_figure with dry_run=true
graphhub.render_project_figure
graphhub.collect_artifacts
```

Do not mutate the source project unless a future explicit source-write mode is approved.
```

In `docs/02-design/graph_hub_independent_completion_spec_20260608.md`, change the blocker paragraph to state that project-aware render is implemented and the remaining risk is real-project/server acceptance.

- [ ] **Step 4: Run docs/prompt tests**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_prompts_get_project_figure_workflow_mentions_project_render -q
```

Expected:

```text
1 passed
```

## Task 8: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused MCP suites**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_project_discovery.py tests/test_mcp_normalization.py tests/test_mcp_batch_quality.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run lint**

Run:

```bash
python hub_uv.py run --with ruff python -m ruff check graphhub_mcp_server.py hub_core/mcp_surface.py hub_core/project_discovery.py tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_project_discovery.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run smoke**

Run:

```bash
python hub_uv.py run python graphhub_mcp_server.py --smoke
```

Expected:

```json
{"health_status": "ok", "status": "ok", "style_format_count": 10, "tool_surface": "graphhub_mcp"}
```

- [ ] **Step 4: Run active MCP config check**

Run:

```bash
codex mcp list | rg graphhub
```

Expected:

```text
graphhub ... enabled
```

- [ ] **Step 5: Run diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected:

```text
git diff --check has no output
status shows only intended Graph Hub changes
```

## Review

### Review 1 - Spec Coverage

Findings:

1. **Covered:** The plan adds `graphhub.render_project_figure`, the missing project-aware MCP render tool.
2. **Covered:** Source-project write risk is handled by runtime snapshot execution under `runtime_root/mcp_project_jobs/<job_id>/project`.
3. **Covered:** Multi-figure ambiguity is handled through explicit `figure_id` or `figure_output`.
4. **Covered:** Failure taxonomy maps config, contract, export, timeout, and plot failures.
5. **Covered:** Provenance is required in manifest/status/collect output.
6. **Covered:** Agent workflow docs and prompt support are included.
7. **Residual risk:** The plan uses direct Python script execution for the selected figure in the snapshot. This is the smallest safe slice, but it does not yet support R figure scripts. A later slice should either call the existing process runner or add language dispatch for R/Python parity.

### Review 2 - Implementation Risk

Findings:

1. **High:** If the selected figure script depends on analysis outputs that are absent, project render will fail. This is acceptable for the first project-aware render tool if failure is `EXPORT` or `PLOT` with clear `resolution_hint`; later work can add `run_analysis=true` or dependency planning.
2. **Resolved in plan:** Copying whole projects can include large raw/media files, so this plan requires selective snapshot copy by default: `project_config.yaml`, the selected script, declared figure inputs, `hub_scripts`, and `results/data`. Any future full-copy mode must be explicit and user-approved.
3. **Medium:** Running arbitrary project scripts from MCP is a write-capable execution surface. The tool must remain in `WRITE_TOOL_NAMES`, use runtime-root isolation, and expose `dry_run=true` first in prompts.
4. **Medium:** `collect_artifacts` must search `mcp_project_jobs` as well as `mcp_jobs`; otherwise render works but artifact collection fails.
5. **Medium:** Active-agent promotion is still blocked until this tool is callable through the actual MCP server after implementation, not only through direct Python tests.

### Review 3 - Plan Quality

Findings:

1. **No placeholder task remains.** Every task has concrete tests, implementation snippets, commands, and expected outputs.
2. **The task order is TDD-compatible.** Schema, selector, dry-run, execution, failure handling, collect, docs, and final verification can be implemented independently.
3. **The plan intentionally avoids broad orchestrator refactor.** This is correct for the current blocker; broad process-runner unification can come after the MCP project-render contract is proven.

## Acceptance Gate

The feature is done only when:

- `tools/list` exposes `graphhub.render_project_figure`,
- `graphhub.render_project_figure` can render one configured Python figure from a project snapshot,
- source project files are unchanged after render,
- project snapshot copy is selective and does not copy undeclared raw/media folders by default,
- manifest/status/collect include provenance,
- failure stages are structured and sanitized,
- HKS and MCP prompts teach agents to use project render before CSV render for configured projects,
- focused MCP tests and ruff pass.
