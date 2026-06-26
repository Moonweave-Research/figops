# Polish Layer Wave: Series Visual Hierarchy

Status: implementation wave for the second polish-layer PR.

## Objective

Expose journal-safe visual hierarchy controls for individual data series without creating a new plotting DSL or bypassing FigOps theme constraints.

This wave turns `series_styles` from marker/fill-only polish into a bounded visual-emphasis layer for common publication use cases such as reference-vs-this-work comparisons.

## Scope

Supported per-series keys:

- `color`: line/scatter marker color.
- `alpha`: series transparency.
- `size`: scatter area or line marker size, depending on plot path.
- `linewidth`: line/errorbar line width.
- `zorder`: draw order for emphasizing this-work data.
- `label`: legend label override.

Existing keys remain supported:

- `marker`
- `fill`
- `facecolor` / `markerfacecolor`
- `edgecolor` / `markeredgecolor`
- `linestyle`
- `hatch`

## Non-goals

- No new dependencies.
- No arbitrary rcParams escape hatch.
- No global palette override.
- No behavior change for callers that do not pass the new keys.

## Execution workflow

1. Red test: assert renderer does not yet forward hierarchy keys to scatter/line kwargs.
2. Implement renderer bridge:
   - normalize numeric style values at render time;
   - preserve open-marker behavior;
   - map color to line color, marker face, and marker edge unless more specific overrides are supplied;
   - apply label override to legend entries.
3. Implement MCP contract:
   - accept the new keys in `render_csv_graph` and `render_csv_multipanel` normalization;
   - expose the keys in typed MCP schemas.
4. Regenerate tool reference.
5. Verify with targeted renderer, MCP, schema, and docs tests.
6. Run independent review and fix any schema/runtime mismatch.

## Acceptance evidence

- `tests/test_bridge_renderer.py::SeriesStyleOverrideTest` proves the new keys reach matplotlib kwargs for scatter and line paths.
- `tests/test_mcp_rendering.py::RenderCSVGraphMCPTest::test_render_csv_graph_forwards_log_scale_series_and_annotations` proves the MCP handler forwards the new style keys.
- `tests/test_plot_type_registry.py::test_render_csv_schema_accepts_axis_scale_series_and_annotations_args` proves the dynamic tool schema exposes the keys.
- `docs/tools.md` is regenerated from live schemas.

## Journal-safety rationale

The keys are bounded visual hierarchy tokens, not arbitrary plotting code. They are deterministic, explicit, schema-visible, and still rendered through the FigOps bridge and journal theme stack.
