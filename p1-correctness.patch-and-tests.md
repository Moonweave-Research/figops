# P1 Correctness Receipt

Workflow: `docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json`

Date: 2026-06-29

## changed_files

- `hub_core/data_contract.py`
- `hub_core/data_contract_semantics.py`
- `hub_core/mcp/tools/render_project.py`
- `hub_core/mcp/tools/render_support.py`
- `tests/test_mcp_rendering.py`

## data_contract_parity_test

Implemented:

- `validate_data_contract` now accepts `write_sidecar: bool = True`.
- MCP project render calls both:
  - `validate_data_contract_preflight(... require_existing=True)`
  - `validate_data_contract(... write_sidecar=False)`
- MCP full validation therefore catches dtype/semantic/range failures before
  render while preserving the existing CLI default diagnostics behavior.
- MCP validation does not write calculation sidecars, semantic reports, quality
  metrics, or quality reports into the source project during dry-run or
  pre-render validation.

Regression test:

- `tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_semantic_failure_fails_full_data_contract_without_writing`

Focused result:

```text
4 passed in 1.97s
```

## preflight_target_parity_test

Implemented:

- `_safe_preflight` now passes the requested normalized target format directly
  to `validate_figure_preflight`.
- Supported non-Nature targets such as `wiley`, `cell`, and the internal style
  target are no longer silently mapped to `nature`.

Regression test:

- `tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_safe_preflight_preserves_supported_non_nature_targets`

Focused result:

```text
2 passed, 3 subtests passed in 0.19s
```

## command_results

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m py_compile hub_core/data_contract.py hub_core/data_contract_semantics.py hub_core/mcp/tools/render_project.py hub_core/mcp/tools/render_support.py tests/test_mcp_rendering.py
```

Result: exit 0

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_mcp_rendering.py tests/test_journal_theme_layout.py -q -p no:cacheprovider
```

Result: exit 0

```text
169 passed, 2 skipped, 11 subtests passed in 69.26s (0:01:09)
```

## residual_risk

- The validation parity now covers MCP project render. CSV render paths already
  had independent semantic checks and were not modified in this wave.
- The external FigOps venv was used because bare Python lacks `yaml`/`pytest`
  and `uv` is not on PATH.
