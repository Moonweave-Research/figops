# Autonomous Roadmap Team Workflow

## Research And Prior Art

This run followed the Depone workflow pattern set: parallel fan-out/fan-in for
independent audits, adversarial verification through tests, and a bounded first
implementation wave. The local roadmap and decomposition spec identify
large-module debt as the current priority, especially data-contract semantics,
MCP CSV rendering, bridge rendering, config parsing, and geometry diagnostics.

## Product Position And Non-Goals

The objective was to advance FigOps toward maintainable, modular research
operations without changing the public runtime contract. The run intentionally
did not install dependencies, rewrite git history, reformat unrelated files, or
start high-risk visual/rendering refactors before the data-contract seam was
made small and testable.

## Workflow Architecture

The main agent owned implementation and integration. Two read-only explorers ran
in parallel:

- D2 compatibility audit: remaining semantic helper families, monkeypatch risks,
  and witness tests.
- Roadmap audit: largest remaining modules, safest next slices, and test gates.

Their outputs were fanned in before final reporting.

## Execution Model

The first wave completed D2 data-contract semantic helper extraction:

- calculation-check summary, sidecar, group, and JSON-safe utilities
- grouped validators for `min_replicates`, `expected_sample_count`, `grouped_cv`
- statistical/calculation-style validators for `log_scale_positive`,
  `error_bar_source`, `mean_sem`, `linear_fit`, and `outlier_flag`
- compatibility aliases retained through `hub_core.data_contract_semantics`

## Safety And Verification Gates

Risk gates:

- no dependency installation
- no destructive git cleanup
- no unrelated dirty-file reverts
- defer broad render/visual refactors until focused data-contract tests pass

Verification gates:

- Python compile checks for touched modules and related tests
- focused data-contract regression tests
- selected MCP semantic/calculation witness tests

## Evaluation Fixtures

Primary witness suites:

- `tests/test_data_contract_quality.py`
- `tests/test_data_contract_new.py`
- selected semantic/calculation cases from `tests/test_mcp_rendering.py`

## Release Or Implementation Plan

Completed in this run:

1. D2 helper extraction through focused modules.
2. Compatibility aliases preserved.
3. Decomposition spec progress updated.
4. Workflow record emitted as JSON and Markdown.

Closure state:

1. Current hotspot line counts were re-measured on 2026-06-29 and synced to
   `docs/architecture.md`.
2. The active D1-D6 primary-hotspot decomposition track is complete with
   compatibility shims retained and focused witness tests passing.
3. Future extractions should start from the new live inventory rather than
   treating the original 2026-06-28 hotspot list as still open.

Completed follow-up:

- 2026-06-29: pure MCP `render_csv` argument normalization moved to
  `hub_core/mcp/tools/render_csv_args.py` with compatibility imports retained in
  `hub_core.mcp.tools.render_csv`.
- 2026-06-29: bridge renderer overlays and annotations moved to
  `plotting/renderers/overlays.py` with compatibility aliases retained in
  `plotting.bridge_renderer`.
- 2026-06-29: config semantic-check schema validation moved to
  `hub_core/config_semantic_checks.py` with compatibility aliases retained in
  `hub_core.config_parser`.
- 2026-06-29: geometry diagnostics font-token drift, journal compliance, and
  line-width offender checks moved to `hub_core/geometry_style_checks.py` with
  compatibility aliases retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: data-contract scalar validators for `allow_null`, `range`, and
  `unique` moved to `hub_core/data_contract_semantic_scalar.py` with
  compatibility aliases retained in `hub_core.data_contract` and
  `hub_core.data_contract_semantics`.
- 2026-06-29: geometry diagnostics annotation overlay contrast and
  color/luminance helpers moved to `hub_core/geometry_overlay_contrast.py` with
  compatibility aliases retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: geometry diagnostics repeated-label offset consistency and
  nearest-marker direction helpers moved to `hub_core/geometry_label_offsets.py`
  with compatibility wrappers retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: config top-level key typo detection and Levenshtein suggestion
  helpers moved to `hub_core/config_top_level_keys.py` with compatibility
  aliases retained in `hub_core.config_parser`.
- 2026-06-29: config canonical-docs, experimental-conditions,
  sample-registry, raw-integrity, and relative-path validators moved to
  `hub_core/config_research_metadata.py` with compatibility aliases/wrappers
  retained in `hub_core.config_parser`.
- 2026-06-29: MCP CSV render plot-argument compatibility validation moved to
  `hub_core/mcp/tools/render_csv_args.py` with compatibility import retained in
  `hub_core.mcp.tools.render_csv`.
- 2026-06-29: MCP CSV multipanel layout/shared-legend settings normalization
  moved to `hub_core/mcp/tools/render_csv_args.py`, and copied-panel payload
  plus config YAML assembly moved to `hub_core/mcp/tools/render_csv_multipanel.py`
  while keeping the `figops.render_csv_multipanel` envelope unchanged.
- 2026-06-29: geometry diagnostics point-label skip reporting moved to
  `hub_core/geometry_label_offsets.py` with compatibility alias retained in
  `hub_core.geometry_diagnostics`.
- 2026-06-29: geometry diagnostics text-axis-edge proximity reporting moved to
  `hub_core/geometry_label_offsets.py` with compatibility wrapper retained in
  `hub_core.geometry_diagnostics`.
- 2026-06-29: geometry diagnostics axis-label/title and figure-title/panel-title
  overlap checks moved to `hub_core/geometry_layout_checks.py` with
  compatibility wrappers retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: geometry diagnostics generic artist-overlap candidate collection,
  line overlap boxes, reportability filtering, and leader-marker suppression
  helpers moved to `hub_core/geometry_artist_overlaps.py` with compatibility
  aliases/wrappers retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: geometry diagnostics tick-label visibility, overlap, truncation,
  and crowding checks moved to `hub_core/geometry_tick_labels.py` with
  compatibility wrappers retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: geometry diagnostics visible data extent, data-outside-axes,
  chrome-outside-figure, and degenerate outside-fraction helpers moved to
  `hub_core/geometry_bounds_checks.py` with compatibility aliases/wrappers
  retained in `hub_core.geometry_diagnostics`.
- 2026-06-29: config parser legacy project registry operational-state loading,
  path normalization, and longest-prefix matching moved to
  `hub_core/config_project_registry.py` with compatibility aliases retained in
  `hub_core.config_parser`.
- 2026-06-29: bridge renderer multipanel shared-legend option normalization and
  figure-level legend application moved to
  `plotting/renderers/shared_legend.py` with compatibility aliases retained in
  `plotting.bridge_renderer`.
- 2026-06-29: bridge renderer manuscript multipanel layout ratio validation,
  distributed lengths, panel geometry, axis-rect placement, and split-bias
  helpers moved to `plotting/renderers/multipanel_layout.py` with compatibility
  aliases/wrappers retained in `plotting.bridge_renderer`.
- 2026-06-29: MCP render geometry diagnostics and layout output schema fragments
  moved to `hub_core/mcp/render_geometry_schemas.py` with compatibility aliases
  retained in `hub_core.mcp.schemas`.
- 2026-06-29: MCP render input schema fragments for annotations, legends, axes,
  ticks, multipanel layout, overlays, and series styles moved to
  `hub_core/mcp/render_input_schemas.py` with compatibility aliases retained in
  `hub_core.mcp.schemas`.
- 2026-06-29: MCP CSV multipanel panel normalization, plot compatibility checks,
  data contract validation, calculation-check accumulation, and panel spec
  assembly moved to `hub_core/mcp/tools/render_csv_multipanel.py` while keeping
  the `figops.render_csv_multipanel` envelope unchanged.
- 2026-06-29: config sweep/comparison validation and parser helpers moved to
  `hub_core/config_sweep_comparison.py` with compatibility exports retained in
  `hub_core.config_parser`.
- 2026-06-29: bridge renderer figure sizing, column-width, marker-token,
  scatter-area, and marker-axis-margin helpers moved to
  `plotting/renderers/figure_style.py` with compatibility aliases retained in
  `plotting.bridge_renderer`.
- 2026-06-29: config figure/diagram visual-output validation, including
  traceability declarations, input path checks, theme/format validation, preset
  references, expansion rules, and language-policy checks moved to
  `hub_core/config_visual_outputs.py` with compatibility wrapper retained in
  `hub_core.config_parser`.
