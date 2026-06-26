# Polish Layer Wave: Smart Callout v1

Status: implementation wave for the third polish-layer PR.

## Objective

Expose a small deterministic callout-placement layer for annotations so polished figures can use readable callouts without hand-editing matplotlib coordinates.

## Scope

Supported annotation keys:

- `xytext_offset`: explicit text offset in points, shaped as `{dx, dy}`.
- `placement_preset`: deterministic preset offset for common callout positions: `above`, `below`, `left`, `right`, `upper_left`, `upper_right`, `lower_left`, `lower_right`.
- `avoid_overlap`: when true and no explicit offset/preset is provided, cycle through deterministic preset offsets by annotation index.

Existing annotation keys remain supported:

- `x`, `y`, `text`
- `arrow_to`
- `arrowstyle`
- `connectionstyle`
- `region`, `hspan`, `vspan`
- `color`, `alpha`

## Non-goals

- No dependency-based force-directed label layout.
- No arbitrary callback or Python expression support.
- No change to existing annotations that do not pass the new keys.
- No scientific fitting or semantic interpretation.

## Execution workflow

1. RED tests assert offset/preset/avoid-overlap keys are not yet normalized or rendered.
2. Extend MCP normalization and typed schemas for the bounded callout keys.
3. Extend renderer normalization and drawing:
   - explicit `xytext_offset` wins;
   - then `placement_preset`;
   - then `avoid_overlap` deterministic fanout;
   - otherwise preserve legacy data-coordinate placement.
4. Regenerate `docs/tools.md` from live schemas.
5. Verify with renderer, MCP forwarding, schema, docs, lint, and a real render smoke.
6. Review for backward compatibility and matplotlib coordinate-mode regressions.

## Acceptance evidence

- Renderer tests prove `xytext_offset` uses `textcoords="offset points"` and keeps legacy behavior when absent.
- Renderer tests prove `placement_preset` and `avoid_overlap` produce deterministic non-identical offsets.
- MCP tests prove the new annotation keys are forwarded to `BridgeFigureSpec`.
- Schema tests prove the keys are discoverable in `figops.render_csv_graph` and multipanel panel schemas.

## Journal-safety rationale

Offsets and presets are bounded typographic layout controls. They do not bypass journal themes, alter data, or allow arbitrary plotting code. They make callout placement reproducible and schema-visible.
