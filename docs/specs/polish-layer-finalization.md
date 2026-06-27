# FigOps Polish Layer Finalization Workflow

Status: current execution spec after completed polish waves 1-7.
Scope: FigOps journal-compliant figure polish, not a replacement plotting engine.

## 1. Research and prior art

Current FigOps already has a strong compliance foundation: journal themes, style profiles, MCP render paths, geometry diagnostics, and recent overlay support. The gap is not that Nature, ACS, or other journal tracks are too restrictive. The gap is that the system lacks a thin semantic polish layer that helps an agent or user make a compliant figure look finished.

Observed prior art inside the repo:

- Journal profile and compliance clamp live in `themes/journal_theme.py`.
- Static style tokens live in `themes/style_profiles.py`.
- MCP graph schemas live in `hub_core/mcp/schemas.py`.
- MCP argument normalization lives in `hub_core/mcp/tools/render_csv.py`.
- Renderer capability and annotation drawing live in `plotting/bridge_renderer.py`.
- Geometry diagnostics live in `hub_core/geometry_diagnostics.py`.

Working interpretation: FigOps should preserve deterministic journal-safe rendering while exposing more explicit, typed, and testable polish controls. As of PRs #196-#201 and the tick readability slice staged on this branch, typed complex MCP schemas, series visual hierarchy controls, Smart Callout v1, Legend/Axis Polish v1, Dense Point-Label Polish v1, Contrast Diagnostics v1, and Tick Readability v1 are shipped or staged; the next roadmap must therefore focus on remaining multipanel polish rather than re-solving completed slices.

## 2. Product position and non-goals

### Product position

FigOps should be the reliable journal figure layer for research projects: strict enough to prevent silent formatting drift, but expressive enough to produce publication-ready figures without falling back to bespoke matplotlib for every polished composite.

The polish layer should provide:

1. Better MCP affordances: agents can discover valid style keys instead of guessing object shapes.
2. Better visual hierarchy controls: this-work/reference emphasis, marker/line/alpha/size/z-order tuning.
3. Better callout behavior: safe annotation presets, collision-aware label placement, and panel targeting.
4. Better layout polish: legend, axis, multipanel, and spacing controls that remain journal-safe.
5. Better falsification: visual or diagnostic evidence that style controls reach rendered artifacts.

### Non-goals

- Do not create a second plotting DSL beside the existing MCP/render bridge.
- Do not weaken journal format constraints to make arbitrary aesthetics easier.
- Do not add dependencies without explicit approval.
- Do not implement scientific model fitting that implies interpretation unless the user explicitly chooses the model.
- Do not touch release publication until implementation, review, verification, and final review pass.

## 3. Workflow architecture

The workflow uses a documentation-first sequential spine with two adversarial review gates.

1. Scope lock and current-state inventory.
2. Documentation-first spec and machine-readable workflow plan.
3. Fixture and current-gap audit.
4. Small implementation wave.
5. First independent review.
6. Verification with commands and artifacts.
7. Final adversarial review.
8. Release-readiness handoff.

The machine-readable source of truth is:

- `docs/specs/polish-layer-workflow.plan.json`

This markdown file is the rendered human blueprint.

## 4. Execution model

### Wave 1: documentation

Output:

- `docs/specs/polish-layer-finalization.md`
- `docs/specs/polish-layer-workflow.plan.json`

Exit gate:

- JSON validates with `python -m json.tool`.
- This file contains research, product position, workflow architecture, execution model, safety gates, evaluation fixtures, and release plan.
- No source or test implementation edits are mixed into the documentation slice.

### Wave 2: audit and fixtures

Output:

- `polish-gap-audit-report.md`
- `fixture-manifest.json`

Required fixture classes:

1. Dense point labels.
2. Many series with weak visual hierarchy.
3. Long categorical labels.
4. Cramped multipanel layout.
5. Dark fill with text contrast risk.
6. Log axis with poor tick readability.
7. Annotation near high-density data.
8. Legend/data collision.

Exit gate:

- Each fixture states the currently expected weakness.
- The first implementation slice is chosen by value, risk, and file-touch size.

### Wave 3: implementation status and next slices

Completed slices:

1. Typed MCP style schemas for `series_styles`, `annotations`, `guide_curves`, and `fill_between` shipped in PR #196.
2. Series style extension for color, alpha, marker size, linewidth, z-order, and label override shipped in PR #197.
3. Smart Callout v1 with deterministic offsets and presets shipped in PR #198.
4. Legend and axis polish v1 shipped in PR #199.
5. Dense point-label polish v1 shipped in PR #200: MCP `label_column`, `point_label_options.max_labels/priority_column/skip_column/offset/fanout`, and `point_label_skips` diagnostics.
6. Contrast Diagnostics v1 shipped in PR #201: tagged annotation region/hspan/vspan and manual fill_between overlays are checked against overlapping annotation text with contrast-ratio diagnostics.
7. Tick Readability v1 is staged on this branch: `tick_style.max_label_chars` opt-in truncates long visible x tick labels while preserving original labels on formatter metadata.

Current priority order for remaining slices:

1. Multipanel layout v1: spacing, ratios, and shared legend placement before mosaic/span DSL.
2. Fit/trend overlay expansion: defer until a project explicitly needs model semantics.

Implementation rule: pick one bounded slice, write or extend tests first where feasible, and prove the field reaches either MCP output, renderer behavior, diagnostics, or pixels.

### Wave 4: first review and verification

Review asks:

- Did the patch alter public behavior outside the selected slice?
- Are tests proving the visible or MCP-user-facing behavior?
- Are journal constraints still enforced?
- Are docs and generated tool references consistent?

Verification asks:

- Run targeted tests for changed behavior.
- Run `git diff --check`.
- Run the smallest relevant rendering or diagnostics smoke.
- Record exact commands and exit codes.

### Wave 5: final review and release readiness

Final review must attempt to refute:

- The feature is exposed through MCP.
- The feature is documented enough for an agent to use.
- The feature reaches rendered output or diagnostics.
- The implementation is journal-safe.
- No high-severity regression remains.

Release readiness output:

- Changelog note draft.
- PR body draft.
- Merge checklist.
- Explicit release gate for PyPI/GitHub publication.

## 5. Safety and verification gates

Risk gates:

- Write actions: allowed for this workflow, but keep diffs scoped and reversible.
- Shell commands: allowed for local tests and validation.
- New dependencies: stop and ask before adding.
- Public release: stop and ask before publishing.
- History rewrite or force push: forbidden without explicit approval.

Verification requirements:

- Documentation slice: JSON validation and section checks.
- Implementation slice: targeted tests plus source-level review.
- Visual slice: render or diagnostics evidence, not just object-level tests.
- Completion: independent final review with no unresolved high-severity findings.

## 6. Evaluation fixtures

The fixture manifest in Wave 2 should define each fixture with:

- Fixture id.
- Input CSV or generated data recipe.
- Plot type.
- Current expected weakness.
- Desired polish behavior.
- Acceptance command.
- Artifact path.
- Whether the fixture is automated, semi-automated, or human-reviewed.

Minimum next fixture recommendation: log-axis-tick-readability plus long-categorical-labels, because they exercise remaining axis readability without introducing a new plotting DSL.

## 7. Release or implementation plan

Implementation should advance one PR-sized wave at a time.

Completed PRs:

1. PR #196: documentation and typed MCP polish schema planning.
2. PR #197: series visual hierarchy controls.
3. PR #198: Smart Callout v1.
4. PR #199: Legend and Axis Polish v1.
5. PR #200: Dense Point-Label Polish v1.
6. PR #201: Contrast Diagnostics v1.

Recommended next PR:

1. Tick Readability v1.
2. Opt-in `tick_style.max_label_chars` for long visible x tick labels.
3. Renderer and MCP tests proving schema -> normalization -> rendered tick labels.
4. Generated tool-reference update.

Recommended follow-up PRs:

1. Multipanel layout v1.
2. Fit/trend overlay expansion only with explicit project semantics.

Stop condition for this workflow: final review cannot refute the selected slice's exposure, tests, docs, and journal-safety claims, and release readiness is documented.
