# FigOps Large-Module Decomposition Plan - 2026-06-28

## Purpose

Define the next behavior-preserving decomposition track after the maintenance
hardening pass. This plan intentionally does not perform broad refactors. It
names extraction seams, compatibility requirements, and witness tests required
before code is moved.

## Current Hotspots

Measured on 2026-06-28 with the line-count inventory documented in
`docs/architecture.md`:

| File | Lines | Primary reason to split |
| --- | ---: | --- |
| `plotting/bridge_renderer.py` | 2144 | Multipanel layout, overlay/statistical annotation, legend placement, diagnostics, and export behavior still share one file. |
| `hub_core/config_parser.py` | 2025 | Config loading, migration, validation, role/status policy, presets, and listing helpers are coupled. |
| `hub_core/geometry_diagnostics.py` | 1890 | Detection primitives, overlap checks, scoring, and report shaping are co-located. |
| `hub_core/data_contract_semantics.py` | 1861 | Many independent semantic checks and unit/statistical helpers share one module. |
| `hub_core/mcp/tools/render_csv.py` | 1670 | CSV render argument parsing, normalization, execution, envelope shaping, and multipanel behavior share one tool mixin. |

## Extraction Rules

- Move behavior only behind compatibility shims.
- Keep existing public imports and monkeypatch seams stable until tests prove
  consumers no longer need them.
- Extract one concern at a time.
- Add or identify a witness test before moving code.
- Do not change visual output and architecture in the same PR unless the visual
  change is the explicit tested behavior.

## Proposed Sequence

### D1 - `plotting/bridge_renderer.py`

First extraction seam:

- Move plot-type-specific renderers into `plotting/renderers/`.
- Start with one low-risk family, such as box/violin or heatmap, before moving
  XY/bar/facet paths.

Progress:

- 2026-06-28: box/violin distribution renderers moved to
  `plotting/renderers/distribution.py`; `plotting.bridge_renderer` keeps
  `_render_box_plot` and `_render_violin_plot` compatibility imports.
- 2026-06-28: heatmap rendering moved to `plotting/renderers/heatmap.py`;
  `plotting.bridge_renderer` keeps `_render_heatmap_plot` compatibility import.
- 2026-06-28: bar aggregate validation/calculation helpers moved to
  `plotting/renderers/bar.py`; `plotting.bridge_renderer` keeps
  `_validate_bar_aggregate` and `_aggregate_single_series_bar_points`
  compatibility imports.
- 2026-06-28: bar rendering moved behind `plotting/renderers/bar.py` with a
  dependency context; `plotting.bridge_renderer` keeps `_render_bar_plot` as a
  compatibility wrapper.
- 2026-06-28: renderer grouping, explicit category order resolution, and
  y-error normalization helpers moved to `plotting/renderers/common.py`;
  `plotting.bridge_renderer` keeps private compatibility aliases.
- 2026-06-28: line/scatter XY rendering moved behind
  `plotting/renderers/xy.py` with a dependency context;
  `plotting.bridge_renderer` keeps `_render_xy_plot` as a compatibility
  wrapper.
- 2026-06-28: broken-axis XY axis creation, series drawing, and label routing
  moved behind `plotting/renderers/broken_axis.py`; `plotting.bridge_renderer`
  keeps broken-axis private compatibility wrappers.
- 2026-06-28: facet grid resolution, panel creation, shared-axis marker
  expansion, and facet grouping moved behind `plotting/renderers/facet.py`;
  `plotting.bridge_renderer` keeps facet private compatibility wrappers.
- 2026-06-28: point-label normalization, candidate selection, drawing, and
  skip-report helpers moved to `plotting/renderers/labels.py`;
  `plotting.bridge_renderer` keeps private compatibility aliases.
- 2026-06-28: axis scale/limit validation, axis/tick application, and tick
  label truncation helpers moved to `plotting/renderers/axes.py`;
  `plotting.bridge_renderer` keeps private compatibility aliases.
- After this extraction, `hub_core/data_contract_semantics.py` is the largest
  file in the architecture inventory. Continue bridge extraction only with
  tightly scoped visual witness tests; otherwise move to D2.

Compatibility:

- Keep old private function names importable from `plotting.bridge_renderer`
  during the first extraction wave.
- `hub_core.rendering.registry` should not need a broad rewrite.

Witness tests:

- Existing visual regression fixtures for the moved plot type.
- Existing MCP render tests that exercise `figops.render_csv_graph`.
- A direct unit test proving the old import path still resolves.

### D2 - `hub_core/data_contract_semantics.py`

First extraction seam:

- Move semantic-check registry metadata and schema descriptions into
  `hub_core/data_contract_semantic_registry.py`.
- Then move independent check families into focused modules, for example:
  `data_contract_semantic_units.py`, `data_contract_semantic_statistics.py`,
  and `data_contract_semantic_ordering.py`.

Progress:

- 2026-06-28: semantic-check registry metadata and schema descriptions moved to
  `hub_core/data_contract_semantic_registry.py`; `hub_core.data_contract` and
  `hub_core.data_contract_semantics` keep existing compatibility exports.
- 2026-06-28: unit signature parsing/formatting and Pint compatibility checks
  moved to `hub_core/data_contract_semantic_units.py`;
  `hub_core.data_contract` and `hub_core.data_contract_semantics` keep existing
  private helper compatibility exports.
- 2026-06-28: `unit_coherence` and `axis_unit` semantic validator bodies moved
  to `hub_core/data_contract_semantic_units.py`; compatibility wrappers remain
  in `hub_core.data_contract_semantics`.
- Continue D2 with statistics/order helper families, or switch to D3 if
  `hub_core.config_parser.py` becomes the better next high-leverage hotspot.

Compatibility:

- Keep `hub_core.data_contract.SEMANTIC_CHECK_DEFINITIONS` and existing private
  helper monkeypatch paths working through re-exports until tests are migrated.

Witness tests:

- `tests/test_data_contract_new.py`
- `tests/test_data_contract_quality.py`
- `tests/test_mcp_rendering.py` cases for semantic checks.
- Tool reference freshness if schemas or descriptions move.

### D3 - `hub_core/config_parser.py`

First extraction seam:

- Move style/preset resolution into `hub_core/config_style.py`.
- Move project role/status helpers into `hub_core/project_roles.py` only after
  current imports are inventoried.

Progress:

- 2026-06-28: style preset resolution helpers moved to
  `hub_core/config_style.py`; `hub_core.config_parser` keeps existing
  compatibility exports.
- 2026-06-28: project role/status helpers moved to
  `hub_core/project_roles.py`; `hub_core.config_parser` keeps existing
  compatibility exports.

Compatibility:

- Keep `hub_core.config_parser` exports stable.
- Do not change accepted config schema or error strings without tests.

Witness tests:

- `tests/test_config_parser_sweep.py`
- `tests/test_presets.py`
- `tests/test_project_roles.py`
- `tests/test_config_placeholders.py`

### D4 - `hub_core/geometry_diagnostics.py`

First extraction seam:

- Move low-level bbox/area/intersection primitives into a pure helper module.
- Keep the no-cycle constraint: diagnostics helpers must not import `themes/` or
  higher-level `hub_core` modules.

Progress:

- 2026-06-28: low-level pixel-space bbox/overlap primitives moved to
  `hub_core/geometry_primitives.py`; `hub_core.geometry_diagnostics` keeps
  existing private compatibility exports.

Compatibility:

- Preserve private helper imports used by `plotting.bridge_renderer` until that
  caller is migrated.

Witness tests:

- `tests/test_geometry_diagnostics.py`
- `tests/test_journal_theme_layout.py`
- Any visual regression tests that assert diagnostic sidecars.

### D5 - `hub_core/mcp/tools/render_csv.py`

First extraction seam:

- Move argument normalization and render request construction into a pure helper
  module under `hub_core/mcp/tools/`.
- Keep tool method names and schemas unchanged.

Compatibility:

- `figops.render_csv_graph` and `figops.render_csv_multipanel` inputs/outputs
  must remain stable.
- Do not widen write-tool behavior or data-root access.

Witness tests:

- `tests/test_mcp_rendering.py`
- `tests/test_mcp_batch_quality.py`
- `tests/test_plot_type_registry.py`
- Generated `docs/tools.md` freshness test if schemas change.

## Review Gate For Each Future Extraction

Before merging any extraction PR:

1. Show the old and new import paths.
2. Show the witness test that protects behavior.
3. Run compileall.
4. Run the narrow tests listed above for the moved area.
5. State whether visual outputs were intended to change. The default answer
   should be no.
