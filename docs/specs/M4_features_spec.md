# M4 — Feature breadth — implementer spec

> Goal (`docs/ROADMAP.md`): the user-facing capabilities that were limited or refused, each shipped
> via the M3.2 plot-type registry. **Depends on M3.2** (registry). Specified at design/acceptance
> level; exact arg schemas land with each feature. Final priority is driven by real paper/figure
> needs — pull from `task.md` when starting.

## M4.1 — Multi-series broken-axis — M

**Context:** PR #56 (P1c) made `bridge_renderer`'s `y_break_range` path **refuse** when combined with
`series_column` / `yerr_column` / `label_column` / `overlay_baselines` (it would otherwise silently
collapse all series into one undifferentiated blob with no legend/error bars). M4.1 implements the
real thing and removes the guard.

**Design:** in the broken-axis renderer, iterate `_group_points(points, spec)` and draw each series
on both `ax_top` and `ax_bot` with its `get_series_style(idx)`; pass per-series `_yerr_values`; build
the legend and draw `overlay_baselines` on the top axes; apply labels. Implement as/through the
registry's broken-axis capability.

**Acceptance:** a multi-series broken-axis figure renders per-series styling + legend + error bars +
overlays; the P1c refusal guard is removed; the P1c witness tests are updated from "raises" to
"renders correctly"; a visual-regression baseline is added (now meaningful — renders are
byte-reproducible since PR #60).

## M4.2 — New plot types & layouts — M

Via the registry (M3.2), no dispatch-core edits:
- **Faceting / small-multiples** (a grid of subplots keyed by a column).
- **Box / violin parity** in the bridge renderer (the `plotting/common_plots.py` helpers exist with
  Nature small-n guidance; expose them as registered plot types with the same data-contract path).
- **Statistical overlays**: CI bands, regression/fit lines, significance markers (build on
  `scientific-visualization` conventions).
- **Grouped-bar replicate aggregation**: the single-series bar currently warns on duplicate
  categories (PR #56); add an opt-in `aggregate: mean|median` for grouped replicates.

**Acceptance:** each new type is a registry entry with its `arg_schema` + `capabilities`, a render
test, a docs example, and (where deterministic) a visual-regression baseline.

## M4.3 — Domain analysis helpers (materials/polymer) — M

**Context:** `analysis_helpers/{general,physics}/*.R` exist but are loosely integrated; the R input
contract was fixed in PR #63 (`GRAPH_HUB_INPUTS` → `raw/`).

**Design:** promote common materials/polymer analyses (e.g. signal processing, material-physics
transforms) to first-class, documented analysis steps that flow through the data-contract framework
(declared inputs → validated outputs → figure). Keep them behind the contract so outputs are
schema-checked. Mirror equivalents for Python-side analysis where useful.

**Acceptance:** a documented project recipe runs a domain analysis end-to-end (validated by the data
contract) and renders a figure; the analysis is reusable across projects via config, not copy-paste.

## M4.4 — Richer data contracts — S

Extend the semantic-check vocabulary in `hub_core/contracts/` (post-M1) with the checks researchers
actually need (e.g. monotonic-within-group, expected sample counts, unit-coherence across columns),
and surface the available checks + plot types via the M5 discovery API / an enriched `list_styles`.

**Acceptance:** new checks have witness tests (valid passes, violation fails loudly — never silently
narrows); the contract vocabulary is discoverable via the API.

## Definition of done (M4)

- Multi-series broken-axis works (guard removed, tests flipped to "renders").
- New plot types/layouts are registry entries with tests + docs examples + (deterministic) baselines.
- A domain analysis recipe runs through the contract end-to-end.
- All new capabilities are discoverable via the API and never reintroduce a silent fallback.
