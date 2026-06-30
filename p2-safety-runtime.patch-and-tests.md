# P2 Safety And Runtime Receipt

Workflow: `docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json`

Date: 2026-06-29

## changed_files

- `graphhub_mcp_launcher.py`
- `hub_core/config_parser.py`
- `hub_core/mcp/render_orchestration.py`
- `hub_core/mcp/tools/render_csv.py`
- `hub_core/mcp/tools/render_project.py`
- `tests/test_mcp_rendering.py`
- `tests/test_project_discovery.py`
- `tests/test_smoke.py`
- `tests/test_uv_runtime.py`

## symlink_destination_test

Implemented:

- Added runtime write path symlink detection in
  `hub_core/mcp/render_orchestration.py`.
- CSV graph, CSV multipanel, and project render paths now reject symlinked job
  roots or symlinked latest destinations before writing render artifacts.
- Overwrite paths refuse symlinked runtime job roots instead of following or
  deleting them.

Regression test:

- `tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_csv_graph_refuses_symlinked_latest_destination`

Focused result:

```text
5 passed, 1 skipped in 0.27s
```

## multipanel_overwrite_test

Implemented:

- `figops.render_csv_multipanel` now matches single CSV/project render behavior:
  when `overwrite=true` and the existing job root is safe, it removes the stale
  job root before rendering.

Regression test:

- `tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_csv_multipanel_overwrite_removes_existing_job_root`

Focused result:

```text
5 passed, 1 skipped in 0.27s
```

## smoke_command_test

Implemented:

- `tests/test_smoke.py` now uses `unittest.skipUnless` for the R/readr-dependent
  scaffold smoke so `python -m unittest tests.test_smoke` honors the skip.
- The ambient runtime-root test imports `mock` explicitly instead of relying on
  `unittest.mock` being loaded as an attribute.

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m unittest tests.test_smoke
```

Result: exit 0

```text
Ran 2 tests in 0.004s
OK (skipped=1)
```

## list_root_only_test

Implemented:

- `hub_core.config_parser.list_projects(..., recursive=False)` now caps scan
  depth at `1` instead of ignoring the `recursive` flag.

Regression test:

- `tests/test_project_discovery.py::ProjectDiscoveryServiceTest::test_legacy_list_projects_non_recursive_caps_scan_depth`

Focused result:

```text
5 passed, 1 skipped in 0.27s
```

## launcher_drift_test

Implemented:

- `graphhub_mcp_launcher.py` now uses FigOps runtime-root resolution and the
  `uv_envs/figops` environment name.
- Windows venv fallback points at `Scripts/python.exe`; POSIX fallback points at
  `bin/python`.
- If the venv Python is unavailable, the launcher execs
  `sys.executable hub_uv.py run python ...` instead of trying to exec the
  `.py` file directly.

Regression tests:

- `tests/test_uv_runtime.py::UvRuntimeTest::test_graphhub_launcher_uses_figops_uv_environment_name`
- `tests/test_uv_runtime.py::UvRuntimeTest::test_graphhub_launcher_fallback_execs_hub_uv_with_current_python`

## command_results

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m py_compile hub_core/config_parser.py graphhub_mcp_launcher.py tests/test_smoke.py tests/test_project_discovery.py tests/test_uv_runtime.py hub_core/mcp/render_orchestration.py hub_core/mcp/tools/render_csv.py hub_core/mcp/tools/render_project.py tests/test_mcp_rendering.py
```

Result: exit 0

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_mcp_rendering.py tests/test_mcp_read_only.py tests/test_smoke.py tests/test_uv_runtime.py tests/test_project_discovery.py -q -p no:cacheprovider
```

Result: exit 0

```text
212 passed, 8 skipped, 11 subtests passed in 73.64s (0:01:13)
```

## residual_risk

- The preferred `python hub_uv.py run ...` path still depends on `uv` being
  available on PATH. This wave fixed launcher fallback behavior but did not
  install dependencies or modify user PATH.
- R/readr scaffold coverage remains skipped in this environment because
  `Rscript` is unavailable.
