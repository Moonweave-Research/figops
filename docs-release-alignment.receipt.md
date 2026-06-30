# Docs, Examples, And Policy Alignment Receipt

Workflow: `docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json`

Date: 2026-06-29

## version_policy

Implemented:

- `README.md` now distinguishes the source checkout version (`0.17.10`) from
  the latest locally documented published package/release asset (`0.17.9`).
- `docs/ROADMAP.md` now labels the scorecard as the `0.17.10` source line while
  retaining `0.17.9` as the locally documented public release baseline.
- Packaging docs keep `APPROVED_VERSION=0.17.9` snippets as release-runbook
  examples and explicitly say to replace them with the approved release version.

Evidence:

```text
README.md: Current State table separates source checkout and published package.
docs/ROADMAP.md: Status baseline names source checkout 0.17.10 and public release 0.17.9.
docs/packaging: APPROVED_VERSION snippets remain parameterized release-runbook examples.
```

## canonical_doc_policy

Implemented:

- `AGENTS.md` now identifies `docs/architecture.md` and `docs/ROADMAP.md` as
  current-state documents.
- `Research_Central_Architecture.md` and `task.md` are explicitly marked as
  historical context unless a current document points back to them.
- `Research_Central_Architecture.md` now opens with a FigOps/Graph Hub
  compatibility note and a current checkout path.

## example_policy

Implemented:

- `examples/synthetic_project/hub_scripts/plot_response_curve.py` now uses
  `apply_journal_theme("nature", profile_name="baseline")` and
  `save_journal_fig`.
- `examples/materials_polymer_recipe/hub_scripts/plot_polymer_domain_helper.py`
  now uses the same publication-safe helper path.

## vector_preflight_policy

Implemented:

- `hub_core/figure_preflight.py` now validates SVG physical width when the SVG
  declares `width` and `height` in supported units.
- PDF/EPS remain explicit dimension-skip targets because physical width
  extraction depends on renderer-specific parsing not present in this runtime
  surface.
- `docs/QA.md` documents the SVG versus PDF/EPS vector dimension policy.

Regression test:

- `tests/test_figure_preflight.py::test_over_width_svg_with_physical_units_fails`

## docs_changed

- `AGENTS.md`
- `README.md`
- `Research_Central_Architecture.md`
- `docs/QA.md`
- `docs/ROADMAP.md`
- `examples/synthetic_project/hub_scripts/plot_response_curve.py`
- `examples/materials_polymer_recipe/hub_scripts/plot_polymer_domain_helper.py`
- `hub_core/figure_preflight.py`
- `tests/test_figure_preflight.py`

## command_results

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_figure_preflight.py tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_runs_public_safe_synthetic_fixture tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_project_figure_runs_public_safe_multipanel_fixture -q -p no:cacheprovider
```

Result: exit 0

```text
18 passed in 2.65s
```

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B scripts/check_public_release.py --root .
```

Result: exit 0

```text
public_release_check: ok
```

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m py_compile hub_core/figure_preflight.py examples/synthetic_project/hub_scripts/plot_response_curve.py examples/materials_polymer_recipe/hub_scripts/plot_polymer_domain_helper.py
```

Result: exit 0

## residual_risk

- No network lookup was performed, per the workflow risk gate. Claims about
  `0.17.9` are therefore framed as "locally documented" rather than live latest
  public state.
