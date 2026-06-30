# Multipanel Secondary-Y Parity

Status: implemented in this PR.
Scope: extend the implemented `figops.render_csv_graph` `secondary_y` contract to
panel-level `figops.render_csv_multipanel` renders without broadening the API
shape.

## Motivation

The dielectric-comparison slice added a narrow, publication-safe twin y-axis API
for single CSV renders. The same real figure workflow often needs a composite
layout: dielectric spectra next to modulus, conductivity, or control panels.
Today that requires falling back to custom Matplotlib for any panel that needs a
right-side y-axis, even though the single-panel render surface already supports
the contract.

## Product Rule

`render_csv_graph` and `render_csv_multipanel` should expose the same panel-level
polish controls whenever the renderer semantics are identical and fail-fast
validation can be preserved. `secondary_y` is such a case for line, scatter, and
xy panels.

## Implementation Plan

1. Add `secondary_y` to the multipanel panel schema using the existing
   `_SECONDARY_Y_SCHEMA`.
2. Normalize each panel's `secondary_y` with the existing argument normalizer,
   wrapping errors with `panels[index]` context.
3. Reject `secondary_y` for unsupported panel `plot_type` values.
4. Include the secondary column in required CSV columns and semantic log-scale
   validation.
5. Forward the normalized object through copied panel specs and render payload.
6. Render a multipanel panel with `secondary_y` through the same bridge helper
   used by single CSV renders, preserving normal axes metadata, title handling,
   ticks, limits, and annotations.
7. Add targeted MCP and bridge-renderer tests plus regenerated tool docs.

## Acceptance

- `figops.render_csv_multipanel` schema exposes `panels[].secondary_y`.
- A line/scatter/xy panel forwards normalized `secondary_y` into the render
  payload and copied project config.
- Missing secondary columns fail during data-contract validation.
- Non-positive values fail when `secondary_y.scale` is `log`.
- Unsupported plot types, including `heatmap`, reject `secondary_y`.
- A multipanel panel render creates a right-side axis tagged as `secondary_y`
  and keeps the default empty-title behavior.
- `scripts/gen_tool_reference.py --check` passes after docs regeneration.

## Non-Goals

- Per-series assignment to primary or secondary axes.
- More than one secondary y-axis per panel.
- `secondary_y` with broken-axis panels (`y_break_range`) or facet subpanels.
- A new multipanel layout DSL.
