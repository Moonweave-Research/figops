# Polish Layer Wave: Legend and Axis Polish v1

Status: proposed next implementation wave.
Depends on: completed typed schemas, series visual hierarchy, and Smart Callout v1.

## Objective

Expose bounded legend and axis polish controls through MCP so common publication cleanup can be done without bespoke matplotlib while preserving FigOps journal-theme constraints.

## User problem

After series hierarchy and callout controls, the most likely remaining fallback-to-matplotlib cases are:

- legends collide with data or need a clear title/order/ncol;
- reference and this-work series need semantic legend ordering;
- long categorical ticks crowd the axis;
- log axes need readable tick formatting;
- axis limits need explicit, reproducible framing.

## Scope

### Legend controls

Preserve the existing `legend_layout` string preset contract. It remains the macro placement/layout selector and must not be changed into an object.

Existing or proposed `legend_layout` values:

- `auto`
- `smart`
- `standard`
- `best`
- `top_outside`
- `right_outside`

Add a separate `legend_options` object for typed legend details:

- `title`: string legend title.
- `order`: array of raw series keys in desired legend order. Ordering is based on source series keys, not display labels after `series_styles.*.label` overrides.
- `ncol`: positive integer number of legend columns.

Deferred from v1 unless implementation proves it is safe in one PR:

- `legend_options.location`: deferred because it overlaps with `legend_layout` macro placement.
- `legend_options.show`: deferred because suppressing legends for multi-series figures needs diagnostics semantics.

### Axis controls

Proposed axis keys:

- `axis_limits.x`: `{min, max}` numeric/string bounds.
- `axis_limits.y`: `{min, max}` numeric/string bounds.
- `tick_style.rotation`: numeric degree value or bounded preset.
- `tick_style.format`: enum `default`, `plain`, `scientific`, `compact`.

Deferred from v1 unless implementation proves it is safe in one PR:

- `tick_style.max_label_chars`: defer to Tick Readability v1 so it does not conflict with the existing `compress_labels` path.

The exact key names may be adjusted during implementation if existing renderer structures already provide a better home, but the public contract must remain typed and documented.

## Non-goals

- No arbitrary rcParams.
- No user-supplied Python formatter functions.
- No global palette override.
- No automatic scientific model fitting.
- No full auto-layout solver.
- No mosaic or panel-span DSL in this wave.
- No default behavior change when callers omit the new keys.
- No conversion of existing `legend_layout` string presets into an object or string/object union.

## Adversarial risks and mitigations

| Risk | Mitigation |
|---|---|
| Legend controls become an arbitrary matplotlib escape hatch. | Use bounded enums and typed scalar/list fields only. |
| Existing `legend_layout` callers break. | Preserve `legend_layout` as a string preset and put new details in `legend_options`. |
| Runtime silently drops unknown keys. | Normalizers must reject unsupported keys. |
| `legend_options.order` becomes ambiguous after label overrides. | Define order by raw source series key, not displayed label. |
| `legend_options.location` conflicts with `legend_layout`. | Defer location or allow it only under a future explicit manual layout mode. |
| Legend suppression hides multi-series semantics. | Defer `show=false`; if later added, emit diagnostics when hiding legends for multi-series figures. |
| Tick compression hides scientific/category meaning. | Defer `max_label_chars`; preserve source labels and existing `compress_labels` semantics. |
| Axis limits hide data. | Explicit limits are user-supplied only; validate finite min/max and `min < max`. |
| Log axis limits can create invalid plots. | For log axes, require finite positive limits. |
| Numeric axis controls are applied to categorical axes. | For categorical axes, reject numeric limits and numeric-only tick formats unless category semantics are explicitly designed. |
| Outside legends break journal dimensions. | Keep outside placement bounded by existing `legend_layout` presets and verify geometry diagnostics. |
| Multipanel behavior becomes ambiguous. | Prefer panel-level controls first; graph-level defaults require explicit merge semantics and tests. |

## Implementation plan

1. RED tests:
   - schema tests for `legend_layout` string presets, `legend_options`, `axis_limits`, and `tick_style` keys;
   - MCP normalization tests for forwarding supported keys and rejecting unsupported/conflicting keys;
   - renderer tests proving legend title/order/ncol and axis/tick controls reach matplotlib;
   - backward-compatibility test proving existing `legend_layout="standard"`, `"smart"`, `"best"`, `"top_outside"`, and `"right_outside"` calls remain string-based;
   - validation tests for log-axis limits, categorical-axis restrictions, and multipanel panel-level behavior.
2. Implement schema and normalization.
3. Implement renderer support using existing theme constraints.
4. Regenerate `docs/tools.md`.
5. Run targeted tests plus a render smoke for:
   - `legend-data-collision` fixture;
   - `log-axis-tick-readability` fixture.
6. Run review focused on schema/runtime mismatch, journal-safety, and silent behavior changes.

## Acceptance evidence

Required before merge:

- `figops.render_csv_graph` exposes `legend_layout` as a string preset plus typed `legend_options`, `axis_limits`, and `tick_style` controls.
- `figops.render_csv_multipanel` exposes the same controls only where panel-level semantics are implemented; otherwise the unsupported scope is explicitly deferred.
- Normalization rejects unsupported nested keys and conflicting `legend_layout`/`legend_options` combinations.
- Renderer tests prove controls affect matplotlib calls or visible diagnostics.
- Existing string `legend_layout` callers remain backward-compatible.
- Generated `docs/tools.md` includes the public contract.
- `git diff --check` passes.
- Ruff passes for touched Python files.
- A real render smoke produces an artifact with at least legend title/order/ncol or tick formatting applied.

## Deferral triggers

Defer or split the wave if implementation reveals:

- multipanel semantics require broad layout refactoring;
- outside legend placement cannot be made geometry-safe with existing `legend_layout` presets;
- tick formatting requires a new dependency;
- axis/tick controls conflict with journal compliance diagnostics;
- categorical-axis or log-axis validation cannot be made fail-fast.

## Recommended PR title

`feat(mcp): expose bounded legend and axis polish controls`
