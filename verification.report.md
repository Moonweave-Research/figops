# Verification Report

Workflow: `docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json`

Date: 2026-06-29

## confirmed

| Claim | Evidence |
| --- | --- |
| Wave 0 baseline exists and records blocked/local environment state. | `baseline.receipt.md` contains `git_status`, `available_python_env`, `blocked_commands`, `r_runtime_status`, and `initial_test_slice`. |
| MCP project render now runs full data-contract validation before rendering. | `hub_core/mcp/tools/render_project.py` calls `validate_data_contract(..., write_sidecar=False)` after preflight. `tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_semantic_failure_fails_full_data_contract_without_writing` covers semantic failure. |
| MCP preflight no longer maps supported non-Nature targets to Nature. | `hub_core/mcp/tools/render_support.py` passes the normalized requested target to `validate_figure_preflight`. `test_safe_preflight_preserves_supported_non_nature_targets` covers `wiley`, `cell`, and internal style. |
| MCP runtime writes reject symlinked latest/job-root destinations before writing outside runtime. | `hub_core/mcp/render_orchestration.py` provides symlink detection; render tools call it before write. `test_render_csv_graph_refuses_symlinked_latest_destination` verifies no external manifest/status writes. |
| `figops.render_csv_multipanel` overwrite behavior now clears a safe existing job root. | `hub_core/mcp/tools/render_csv.py` removes the existing safe job root when `overwrite=true`. `test_render_csv_multipanel_overwrite_removes_existing_job_root` verifies stale file removal. |
| Documented `python -m unittest tests.test_smoke` command is healthy in this environment. | `tests/test_smoke.py` uses `unittest.skipUnless` and explicit `mock`; command returned `OK (skipped=1)`. |
| `--list-root-only` has an implementation-level depth cap. | `hub_core/config_parser.py` uses `scan_depth = max_depth if recursive else 1`. `test_legacy_list_projects_non_recursive_caps_scan_depth` verifies `[1, 4]`. |
| `graphhub_mcp_launcher.py` no longer uses stale `graph-making-hub` venv paths or direct `.py` exec fallback. | Launcher uses `preview_runtime_root`, `uv_envs/figops`, Windows `Scripts/python.exe`, POSIX `bin/python`, and `sys.executable hub_uv.py ...`. `tests/test_uv_runtime.py` covers venv path and fallback args. |
| README/roadmap distinguish source `0.17.10` from locally documented published `0.17.9`. | `README.md` Current State table and `docs/ROADMAP.md` status baseline are updated. |
| Canonical document hierarchy is unambiguous. | `AGENTS.md` names current architecture/roadmap docs and marks `Research_Central_Architecture.md`/`task.md` historical; `Research_Central_Architecture.md` contains a FigOps/Graph Hub compatibility note. |
| Public examples use publication-safe FigOps helpers. | Both public example plot scripts call `apply_journal_theme(..., profile_name="baseline")` and `save_journal_fig`. Public-safe project render tests passed. |
| SVG vector width preflight is implemented and documented. | `hub_core/figure_preflight.py` parses SVG physical `width`/`height`; `test_over_width_svg_with_physical_units_fails` passed; `docs/QA.md` documents SVG versus PDF/EPS policy. |
| Public release scan still passes after docs/source edits. | `scripts/check_public_release.py --root .` returned `public_release_check: ok`. |

## refuted

| Claim | Refutation |
| --- | --- |
| Bare `python` can run the repo tests in this shell. | Refuted by baseline: bare Python lacks `pytest` and `yaml`. The existing external FigOps venv was required. |
| `python hub_uv.py run ...` is usable in this shell without further setup. | Refuted by baseline: `uv` is not on PATH and wrapper exits with an actionable error. No dependency install was performed. |
| R scaffold smoke fully executes in this shell. | Refuted by baseline: `Rscript` is not on PATH. R-dependent smoke is skipped, not passed. |

## unverified

| Item | Reason |
| --- | --- |
| Live PyPI/GitHub latest release state. | Network verification was a human-gated action and was not performed. Docs intentionally say `0.17.9` is the latest locally documented public release. |
| Full repository test suite. | Focused suites covering the changed surfaces passed. The entire 304-file test set was not run in this turn. |
| R/readr full scaffold run. | `Rscript` is unavailable in this environment. |

## final_commands

```powershell
git status --short --branch
python hub_uv.py --print-env
python hub_uv.py run python orchestrator.py --list-projects
python -m pytest tests/test_runtime_paths.py tests/test_smoke.py -q
uv --version
Rscript --version
```

Baseline result: `hub_uv.py --print-env` succeeded; `hub_uv.py run`, bare
pytest, `uv --version`, and `Rscript --version` were blocked by missing local
tools/dependencies.

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_mcp_rendering.py tests/test_journal_theme_layout.py -q -p no:cacheprovider
```

P1 result: exit 0, `169 passed, 2 skipped, 11 subtests passed`.

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_mcp_rendering.py tests/test_mcp_read_only.py tests/test_smoke.py tests/test_uv_runtime.py tests/test_project_discovery.py -q -p no:cacheprovider
```

P2 result: exit 0, `212 passed, 8 skipped, 11 subtests passed`.

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_figure_preflight.py tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_runs_public_safe_synthetic_fixture tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_runs_public_safe_multipanel_fixture -q -p no:cacheprovider
```

P3 result: exit 0, `18 passed`.

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B scripts/check_public_release.py --root .
```

Result: exit 0, `public_release_check: ok`.

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_mcp_rendering.py tests/test_mcp_read_only.py tests/test_smoke.py tests/test_uv_runtime.py tests/test_project_discovery.py tests/test_figure_preflight.py tests/test_journal_theme_layout.py -q -p no:cacheprovider
```

Final focused result: exit 0, `278 passed, 8 skipped, 17 subtests passed`.

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m py_compile graphhub_mcp_launcher.py hub_core/config_parser.py hub_core/data_contract.py hub_core/data_contract_semantics.py hub_core/figure_preflight.py hub_core/mcp/render_orchestration.py hub_core/mcp/tools/render_csv.py hub_core/mcp/tools/render_project.py hub_core/mcp/tools/render_support.py tests/test_figure_preflight.py tests/test_mcp_rendering.py tests/test_project_discovery.py tests/test_smoke.py tests/test_uv_runtime.py examples/synthetic_project/hub_scripts/plot_response_curve.py examples/materials_polymer_recipe/hub_scripts/plot_polymer_domain_helper.py
```

Result: exit 0.

## residual_risk

- `uv` is still not on PATH, so the preferred wrapper command remains blocked
  in this shell unless the user installs or exposes `uv`.
- `Rscript` is still unavailable, so R-dependent scaffold smoke remains skipped.
- Live public package state was not checked over the network; docs avoid claiming
  "latest" beyond locally documented release state.
- Full all-tests regression was not run; focused changed-surface suites passed.
