# FigOps Polish Layer Adversarial Roadmap

Status: source-of-truth roadmap for the next polish-layer waves after PRs #196-#198.
Scope: roadmap and acceptance criteria only; no renderer or MCP implementation in this document.

## 1. Baseline

Completed polish-layer capabilities:

1. Typed complex MCP schemas for `series_styles`, `annotations`, `guide_curves`, and `fill_between`.
2. Series visual hierarchy controls: color, alpha, marker size, linewidth, z-order, and legend label override.
3. Smart Callout v1: explicit point offsets, placement presets, deterministic fanout, and legacy annotation compatibility.

Therefore, future polish work must not treat schema discoverability, basic visual hierarchy, or deterministic callout offsets as open gaps unless a regression is proven.

## 2. Adversarial decision gates

A candidate slice is rejected or deferred if any of these claims is true:

- It weakens journal-theme constraints or creates arbitrary rcParams escape hatches.
- It creates a second plotting DSL instead of extending the existing MCP/render bridge.
- It only improves subjective appearance without schema, renderer, pixel, or diagnostics evidence.
- It silently accepts keys that the renderer ignores.
- It implies scientific model interpretation without explicit user-selected model semantics.
- It requires a new dependency before deterministic low-dependency alternatives are exhausted.
- It cannot be delivered as one reviewable PR with targeted tests and generated docs.

A candidate slice is promoted if all of these claims are true:

- It solves a recurring fallback-to-matplotlib reason.
- It stays bounded, typed, and journal-safe.
- It has at least one fixture in `polish-fixture-manifest.json`.
- Its acceptance path can prove MCP schema -> normalization -> renderer/diagnostics -> docs.

## 3. Priority stack

### P0. Roadmap and fixture refresh

Purpose: keep roadmap truth aligned with shipped capabilities.

Acceptance criteria:

- Completed waves are marked as completed.
- Stale expected failures for typed schemas, series hierarchy, and Smart Callout v1 are removed or narrowed to residual gaps.
- Next implementation slice is named explicitly.
- JSON fixture manifest validates.

### P1. Legend and Axis Polish v1

Purpose: expose the highest-value remaining layout controls without weakening journal formats.

Candidate controls:

- preserve existing `legend_layout` string presets for macro placement
- add `legend_options.title`
- add `legend_options.order` using raw series keys
- add `legend_options.ncol`
- defer `legend_options.location` unless a safe manual layout mode is specified
- defer `legend_options.show=false` until multi-series suppression diagnostics are designed
- `axis_limits.x` / `axis_limits.y` with log-axis and categorical-axis validation
- `tick_style.rotation`
- `tick_style.format` for `plain`, `scientific`, or `compact`
- defer `tick_style.max_label_chars` to avoid conflicting with existing label compression behavior

Acceptance criteria:

- MCP schema documents each accepted key.
- Normalizers reject unsupported legend/axis keys rather than dropping them silently.
- Renderer tests prove legend title/order/ncol and tick/axis controls reach matplotlib or diagnostics.
- At least one render smoke exercises legend-data-collision and one exercises log-axis-tick-readability.
- Existing calls without the new keys produce the same default behavior.
- Existing `legend_layout` string-preset callers remain backward-compatible; new legend details live under `legend_options`.

Rejected scope:

- Arbitrary rcParams.
- Free-form tick formatter callbacks.
- Global palette changes.
- Full layout solver.

### P2. Dense Point-Label Polish v1

Purpose: reduce label clutter for dense scatter labels with deterministic behavior.

Candidate controls:

- per-label offset column or static offset
- label priority column
- max labels
- deterministic fanout presets
- diagnostic warning when label collision remains high

Acceptance criteria:

- No new repel/force-layout dependency.
- Behavior is deterministic across runs.
- Diagnostics report skipped or high-risk labels.
- Existing `label_column` behavior remains unchanged unless new controls are passed.

### P3. Contrast Diagnostics v1

Purpose: detect unreadable text on dark overlays before adding automatic restyling.

Candidate checks:

- text annotation vs region/hspan/vspan/fill_between contrast
- warning severity based on luminance contrast threshold
- diagnostics payload that identifies the affected annotation and overlay

Acceptance criteria:

- Diagnostics-only first pass; no automatic color mutation.
- False positives are bounded by only checking overlapping annotation/overlay extents when available.
- Existing geometry diagnostics schema remains backward-compatible.

### P4. Tick Readability v1

Purpose: improve long categorical labels and log-axis readability.

Candidate controls:

- opt-in categorical label compression
- tick rotation presets
- log tick label format presets
- crowding diagnostics tied to recommended controls

Acceptance criteria:

- Original labels are preserved in data/config; compression is visual-only and opt-in.
- Log formatting does not change data scale semantics.
- Diagnostics explain whether rotation/compression was applied or recommended.

### P5. Multipanel Layout v1

Purpose: improve cramped multipanel figures without jumping directly to a mosaic DSL.

Candidate controls:

- panel spacing presets
- width and height ratios
- shared legend placement
- panel-specific legend visibility

Deferred:

- arbitrary panel spanning
- nested mosaic grammars
- publication-template auto-layout solver

### P6. Fit / Trend Overlay Expansion

Purpose: style or model fit overlays only when a concrete project requires it.

Default decision: defer.

Reason: model choice can imply scientific interpretation. Existing `guide_curves` should cover semantic hand-guide curves unless explicit model semantics are requested.

## 4. Recommended next PR sequence

1. Docs-only roadmap refresh.
2. Legend and Axis Polish v1.
3. Dense Point-Label Polish v1.
4. Contrast Diagnostics v1.
5. Tick Readability v1, if not fully absorbed by P1.
6. Multipanel Layout v1.
7. Architecture/data-contract debt as a separate maintenance track.

## 5. Completion definition

A wave is complete only when:

- schema and docs expose the controls;
- runtime normalization accepts and rejects the same contract;
- renderer or diagnostics behavior is directly tested;
- a render or diagnostics smoke proves the path is not merely schema-only;
- final review finds no correctness, journal-safety, or silent-drop regression.
