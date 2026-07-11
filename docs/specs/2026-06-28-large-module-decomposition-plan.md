# FigOps Large-Module Decomposition Plan - 2026-06-28

## Purpose

Define the next behavior-preserving decomposition track after the maintenance
hardening pass. This plan intentionally does not perform broad refactors. It
names extraction seams, compatibility requirements, and witness tests required
before code is moved.

## Hotspot Snapshot

Initial primary hotspots measured on 2026-06-28 were the target of this
behavior-preserving decomposition track. The closure snapshot below was
measured on 2026-06-29 with `scripts/architecture_inventory.py` and matches
`docs/architecture.md`:

| File | Lines | Primary reason to split |
| --- | ---: | --- |
| `plotting/bridge_renderer.py` | 985 | Prior primary hotspot; now split across plot-type, overlay, shared-legend, layout, and figure-style helper modules. |
| `hub_core/mcp/tools/render_csv.py` | 972 | Prior primary hotspot; argument, multipanel settings, payload, and panel-validation helpers now live in focused modules. |
| `hub_core/config_parser.py` | 913 | Prior primary hotspot; style/schema, metadata, semantic-check, registry, sweep/comparison, and visual-output validators are split out. |
| `hub_core/geometry_diagnostics.py` | 852 | Prior primary hotspot; style, contrast, label, layout, overlap, tick, and bounds checks are split out. |
| `hub_core/mcp/schemas.py` | 831 | Prior schema hotspot; render input/output schema fragments are split out. |
| `hub_core/data_contract_semantics.py` | 503 | Prior primary hotspot; now mainly compatibility/orchestration after semantic helper-family extraction. |

Remaining over-budget files such as `themes/journal_theme.py`,
`hub_core/process_runner.py`, `hub_core/mcp/render_orchestration.py`, and
`hub_core/visual_regression.py` are separate future maintenance candidates, not
unfinished work from this decomposition track.

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
- 2026-06-28: single-axes legend normalization, placement, collision
  avoidance, and application helpers moved to `plotting/renderers/legend.py`;
  `plotting.bridge_renderer` keeps private compatibility aliases.
- 2026-06-29: manual overlays, annotation normalization/drawing, fit/CI
  statistical overlays, and significance marker helpers moved to
  `plotting/renderers/overlays.py`; `plotting.bridge_renderer` keeps private
  compatibility aliases.
- 2026-06-29: multipanel shared-legend option normalization and figure-level
  legend application moved to `plotting/renderers/shared_legend.py`;
  `plotting.bridge_renderer` keeps private compatibility aliases.
- 2026-06-29: manuscript multipanel layout ratio validation, distributed
  lengths, panel geometry, axis-rect placement, and split-bias helpers moved to
  `plotting/renderers/multipanel_layout.py`; `plotting.bridge_renderer` keeps
  private compatibility aliases/wrappers.
- 2026-06-29: figure sizing, column-width, marker-token, scatter-area, and
  marker-axis-margin helpers moved to `plotting/renderers/figure_style.py`;
  `plotting.bridge_renderer` keeps private compatibility aliases and is below
  1000 lines after this extraction.
- 2026-07-11: multi-panel specifications, compose-mode validation,
  draft/manuscript composition, image-panel embedding, and save/fingerprint
  orchestration moved to `plotting/renderers/multipanel.py` behind a
  facade-supplied dependency context. Public spec names, private composition
  helpers, and the `save_journal_fig` patch seam remain available from
  `plotting.bridge_renderer`.
- After this extraction, `plotting/bridge_renderer.py` is no longer the largest
  hotspot. Continue bridge extraction only with tightly scoped visual witness
  tests; otherwise move to D2/D3 based on current inventory.

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
- 2026-06-28: monotonic and monotonic-within-group ordering validators moved
  to `hub_core/data_contract_semantic_ordering.py`; compatibility aliases and
  wrappers remain in `hub_core.data_contract_semantics`.
- 2026-06-29: statistical quality scoring and diagnostics sidecar writing moved
  to `hub_core/data_contract_semantic_quality.py`; compatibility wrapper
  remains in `hub_core.data_contract_semantics`.
- 2026-06-29: calculation-check summary, sidecar writing, group payload, and
  JSON-safe helper utilities moved to `hub_core/data_contract_calculation_checks.py`;
  compatibility exports remain in `hub_core.data_contract_semantics`.
- 2026-06-29: grouped semantic validators for `min_replicates`,
  `expected_sample_count`, and `grouped_cv` moved to
  `hub_core/data_contract_semantic_grouped.py`; compatibility aliases remain in
  `hub_core.data_contract_semantics`.
- 2026-06-29: calculation-style semantic validators for `log_scale_positive`,
  `error_bar_source`, `mean_sem`, `linear_fit`, and `outlier_flag` moved to
  `hub_core/data_contract_semantic_statistics.py`; compatibility aliases remain
  in `hub_core.data_contract_semantics`.
- 2026-06-29: scalar semantic validators for `allow_null`, `range`, and
  `unique` moved to `hub_core/data_contract_semantic_scalar.py`;
  compatibility aliases remain in `hub_core.data_contract` and
  `hub_core.data_contract_semantics`.
- Continue D2 with grouped/statistical helper families only if they remain
  high leverage after the current inventory; otherwise switch to D1/D3/D4 based
  on the largest current hotspots.

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
- 2026-06-28: style target-format, preset-key, font-strategy, and profile
  registry compatibility exports moved to `hub_core/config_style.py`;
  `hub_core.config_parser` keeps existing compatibility exports.
- 2026-06-28: schema-version migration and duplicate-key-safe YAML loading
  moved to `hub_core/config_schema.py`; `hub_core.config_parser` keeps existing
  compatibility exports.
- 2026-06-29: data-contract semantic-check config validators and
  `csv_checks[].semantic_checks` validation moved to
  `hub_core/config_semantic_checks.py`; `hub_core.config_parser` keeps existing
  compatibility exports and error strings.
- 2026-06-29: top-level config-key typo detection and Levenshtein suggestion
  helpers moved to `hub_core/config_top_level_keys.py`;
  `hub_core.config_parser` keeps existing compatibility exports and error
  strings.
- 2026-06-29: canonical-docs, experimental-conditions, sample-registry,
  raw-integrity, and relative-path validators moved to
  `hub_core/config_research_metadata.py`; `hub_core.config_parser` keeps
  existing compatibility exports and error strings.
- 2026-06-29: legacy project registry operational-state loading, path
  normalization, and longest-prefix matching moved to
  `hub_core/config_project_registry.py`; `hub_core.config_parser` keeps
  existing private compatibility aliases.
- 2026-06-29: sweep/comparison validation and normalized parser helpers moved
  to `hub_core/config_sweep_comparison.py`; `hub_core.config_parser` keeps
  existing `parse_sweep_config` and `parse_comparison_config` compatibility
  exports plus private validation aliases.
- 2026-06-29: figure/diagram visual-output validation, including traceability
  declarations, input path checks, theme/format validation, preset references,
  expansion rules, and language-policy checks moved to
  `hub_core/config_visual_outputs.py`; `hub_core.config_parser` keeps the
  private `_validate_visual_outputs` compatibility wrapper and is below 1000
  lines after this extraction.

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
- 2026-06-28: marker color/style normalization helpers moved to
  `hub_core/geometry_marker_styles.py`; `hub_core.geometry_diagnostics` keeps
  existing private compatibility exports.
- 2026-06-29: font-token drift, journal compliance, font-floor, and line-width
  offender checks moved to `hub_core/geometry_style_checks.py`;
  `hub_core.geometry_diagnostics` keeps existing private compatibility exports.
- 2026-06-29: annotation overlay contrast and color/luminance helpers moved to
  `hub_core/geometry_overlay_contrast.py`; `hub_core.geometry_diagnostics`
  keeps existing private compatibility exports.
- 2026-06-29: repeated-label offset consistency and nearest-marker direction
  helpers moved to `hub_core/geometry_label_offsets.py`;
  `hub_core.geometry_diagnostics` keeps existing private compatibility wrappers.
- 2026-06-29: point-label skip reporting moved to
  `hub_core/geometry_label_offsets.py`; `hub_core.geometry_diagnostics` keeps
  existing private compatibility exports.
- 2026-06-29: text-axis-edge proximity reporting moved to
  `hub_core/geometry_label_offsets.py`; `hub_core.geometry_diagnostics` keeps
  existing private compatibility wrappers.
- 2026-06-29: axis-label/title and figure-title/panel-title overlap checks
  moved to `hub_core/geometry_layout_checks.py`;
  `hub_core.geometry_diagnostics` keeps existing private compatibility wrappers.
- 2026-06-29: generic artist-overlap candidate collection, line overlap boxes,
  reportability filtering, and leader-marker suppression helpers moved to
  `hub_core/geometry_artist_overlaps.py`; `hub_core.geometry_diagnostics` keeps
  existing private compatibility aliases and wrappers.
- 2026-06-29: tick-label visibility, overlap, truncation, and crowding checks
  moved to `hub_core/geometry_tick_labels.py`; `hub_core.geometry_diagnostics`
  keeps existing private compatibility wrappers.
- 2026-06-29: visible data extent, data-outside-axes, chrome-outside-figure,
  and degenerate outside-fraction helpers moved to
  `hub_core/geometry_bounds_checks.py`; `hub_core.geometry_diagnostics` keeps
  existing private compatibility aliases and wrappers.

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

Progress:

- 2026-06-29: CSV render argument normalization helpers for legends, axes,
  ticks, multipanel layout, point labels, annotations, series styles, fit
  options, guide curves, and fill-between overlays moved to
  `hub_core/mcp/tools/render_csv_args.py`; `hub_core.mcp.tools.render_csv`
  keeps private compatibility imports.
- 2026-06-29: CSV render plot-argument compatibility validation for
  `annotate_values`, error bars, labels, series, guide curves, and fill-between
  overlays moved to `hub_core/mcp/tools/render_csv_args.py`;
  `hub_core.mcp.tools.render_csv` keeps private compatibility imports.
- 2026-06-29: multipanel layout/shared-legend settings normalization moved to
  `hub_core/mcp/tools/render_csv_args.py`, and multipanel copied-panel payload
  plus config YAML assembly moved to `hub_core/mcp/tools/render_csv_multipanel.py`;
  `hub_core.mcp.tools.render_csv` keeps the public tool envelope unchanged.
- 2026-06-29: multipanel panel normalization, plot compatibility checks, data
  contract validation, calculation-check accumulation, and panel spec assembly
  moved to `hub_core/mcp/tools/render_csv_multipanel.py`; the
  `figops.render_csv_multipanel` envelope remains unchanged and
  `hub_core/mcp/tools/render_csv.py` is below 1000 lines.

Compatibility:

- `figops.render_csv_graph` and `figops.render_csv_multipanel` inputs/outputs
  must remain stable.
- Do not widen write-tool behavior or data-root access.

Witness tests:

- `tests/test_mcp_rendering.py`
- `tests/test_mcp_batch_quality.py`
- `tests/test_plot_type_registry.py`
- Generated `docs/tools.md` freshness test if schemas change.

### D6 - `hub_core/mcp/schemas.py`

First extraction seam:

- Move render schema fragments into focused MCP schema modules while preserving
  the existing `hub_core.mcp.schemas` tool registry and private compatibility
  aliases.

Progress:

- 2026-06-29: render geometry diagnostics metric/output schema fragments moved
  to `hub_core/mcp/render_geometry_schemas.py`; `hub_core.mcp.schemas` keeps
  private compatibility aliases.
- 2026-06-29: render input schema fragments for annotations, legends, axes,
  ticks, multipanel layout, guide curves, fit options, fill-between overlays,
  and series styles moved to `hub_core/mcp/render_input_schemas.py`;
  `hub_core.mcp.schemas` keeps private compatibility aliases.

Compatibility:

- `list_tool_definitions()` output must stay schema-compatible for all MCP
  tools.
- Do not change tool names, input schema keys, output schema keys, or write-tool
  trust boundaries.

Witness tests:

- `tests/test_mcp_read_only.py`
- `tests/test_mcp_rendering.py`

## Review Gate For Each Future Extraction

Before merging any extraction PR:

1. Show the old and new import paths.
2. Show the witness test that protects behavior.
3. Run compileall.
4. Run the narrow tests listed above for the moved area.
5. State whether visual outputs were intended to change. The default answer
   should be no.
