# FigOps Polish Gap Audit Report

Status: Wave 2 draft generated from current source inspection.  
Goal: choose the first implementation slice for a journal-safe polish layer.

## Summary verdict

FigOps has a strong compliance renderer but a thin polish affordance layer. The highest value first slice is **typed MCP style schemas for existing polish primitives**, because the renderer already has annotations, spans, guide curves, fill-between overlays, y-error bars, and series style hooks, but the MCP schema advertises several of those as generic objects. That makes agents guess keys and makes docs/tests less precise.

## Evidence-backed gaps

### G1. Complex MCP style inputs are weakly typed

Evidence:

- `hub_core/mcp/schemas.py:476` exposes `series_styles` as an object of generic objects.
- `hub_core/mcp/schemas.py:479-481` exposes `annotations`, `guide_curves`, and `fill_between` as arrays of generic objects.
- `hub_core/mcp/schemas.py:547` and `hub_core/mcp/schemas.py:550-552` repeat the same generic panel-level shapes for multipanel rendering.

Impact: agents cannot discover valid keys reliably, and docs generated from schema cannot teach the polish API.

Recommended slice: P1.

### G2. Series style controls exist but do not cover visual hierarchy

Evidence:

- `hub_core/mcp/tools/render_csv.py:47-82` only accepts marker, fill, face/edge colors, marker face/edge colors, linestyle, and hatch.

Missing for polish:

- per-series color
- alpha
- marker size
- linewidth
- z-order
- legend label override

Impact: FigOps can distinguish open/filled or marker shape, but cannot fully express this-work/reference emphasis without fallback code.

Recommended slice: P1 after schema slice.

### G3. Callouts are supported but not smart

Evidence:

- `plotting/bridge_renderer.py:1154-1241` normalizes text, point, arrow, hspan, vspan, and region annotations.
- `plotting/bridge_renderer.py:1266-1387` draws them with fixed alignment and simple arrowprops.
- `plotting/bridge_renderer.py:1389-1396` draws facet annotations only on the first visible facet axis.

Missing for polish:

- collision-aware offsets
- automatic quadrant choice
- callout presets
- panel or facet targeting
- text box styling and contrast handling

Impact: publication-style leader labels still need manual matplotlib tuning.

Recommended slice: P2.

### G4. Point labels are naive

Evidence:

- `plotting/bridge_renderer.py:726-744` uses a fixed `(0, 4)` offset and centered bottom alignment.

Missing for polish:

- repel/adjust behavior
- priority labels
- per-label offset
- density-aware skip or small-label strategy

Impact: dense scatter labels can pass compliance but look cluttered.

Recommended slice: P2.

### G5. Fit overlays are linear and stylistically fixed

Evidence:

- `plotting/bridge_renderer.py:1427-1431` routes `fit_line` and `ci_band` to linear fit overlay.
- `plotting/bridge_renderer.py:1447-1473` draws a black linear fit and black 95 percent CI band.

Missing for polish:

- explicit model choice
- styled fit line
- trend label placement
- non-model guide semantics distinct from statistical fit

Impact: hand-drawn trend or semantic guide can use `guide_curves`, but data-driven polish remains narrow.

Recommended slice: P3 unless a specific project needs it.

### G6. Renderer spec has knobs not clearly exposed as first-class MCP affordances

Evidence:

- `plotting/bridge_renderer.py:175-215` includes `legend_layout`, `font_scale`, `series_styles`, `guide_curves`, and `fill_between` in `BridgeFigureSpec`.
- `hub_core/mcp/schemas.py:466-513` does not expose all renderer polish knobs with typed documentation.

Impact: renderer capability and MCP-agent usability drift apart.

Recommended slice: P1.

### G7. Diagnostics are objective geometry checks, not aesthetic scoring

Evidence:

- `hub_core/geometry_diagnostics.py:45-62` lists overlap, crowding, outside-figure, legend, font-token, and journal-compliance warnings.
- `hub_core/geometry_diagnostics.py:66-117` returns check results and pass/fail information.

Missing for polish:

- palette harmony
- semantic emphasis
- general text contrast
- excessive series count warning
- figure story or panel balance heuristics

Impact: FigOps can warn about collisions but cannot yet say whether a figure looks finished.

Recommended slice: P3.

## Recommended first implementation slice

**Slice A: typed MCP style schemas for existing polish primitives.**

Why first:

1. It improves agent usability without changing pixels.
2. It reduces hallucinated or unsupported keys.
3. It is low risk and testable through schema/tool-reference tests.
4. It prepares later implementation slices for series style expansion and callout polish.

Acceptance criteria:

- `figops.render_csv_graph` and `figops.render_csv_multipanel` expose typed item schemas for `series_styles`, `annotations`, `guide_curves`, and `fill_between`.
- Normalization behavior remains backward compatible for currently accepted keys.
- Tests cover allowed/unsupported keys where current normalizers enforce them.
- Tool docs generated from schema become more self-describing.

## Deferred implementation slices

1. Series visual hierarchy extension: color, alpha, marker size, linewidth, z-order, label override.
2. Smart callout v1: deterministic label offsets, leader presets, and collision-aware placement.
3. Legend and axis polish controls: legend title/order/ncol, axis limits, tick formatting.
4. Aesthetic diagnostics: contrast, density, palette overload, and panel balance checks.
5. Multipanel mosaic: panel spans and width/height ratios.
