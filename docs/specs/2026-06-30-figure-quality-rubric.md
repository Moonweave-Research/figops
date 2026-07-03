# Figure Quality Rubric

Source of truth: `docs/specs/2026-06-30-figure-quality-rubric.plan.json`

## Objective

Define a compact, repeatable definition of "publication-ready" rendered
figures for FigOps reviews. The rubric separates objective hard gates from
advisory polish so humans and agents can review figures consistently without
turning subjective taste into pipeline failure.

## Scope

- Applies after a figure has rendered through the project config contract.
- Covers single-panel, multi-panel, raster, and vector outputs.
- Maps each quality item to existing FigOps checks where a check already
  exists.
- Leaves future diagnostic names stable by requiring new checks to map to a
  rubric item first.

## Non-Goals

- No code changes in this slice.
- No automated aesthetic scoring.
- No LLM-only visual judgment as a hard gate.
- No journal-specific policy beyond the existing style and preflight contracts.

## Review Status

Use three review outcomes:

- `publishable`: cited hard gates pass, `manual_review_needed` is not true, and
  no advisory issue materially obscures the result.
- `revise`: hard gates pass, but advisory issues should be polished before
  submission or public release.
- `blocked`: at least one hard gate fails, is unverified where the output
  format should support it, or unresolved `manual_review_needed=true` prevents a
  publication-readiness claim.

Skipped diagnostics are not automatic failures, but reviewers must record why
the skip is acceptable. A skipped hard-gate check with no format/runtime reason
keeps the figure in `blocked`.

## Hard Gates

Hard gates are blocking review requirements. A figure with a failed hard gate is
not publication-ready until the issue is fixed or the check is explicitly
inapplicable for the output format/runtime.

| ID | Gate | Existing FigOps mapping | Pass condition |
| --- | --- | --- | --- |
| `FQ-H1` | Artifact integrity | `validate_figure_preflight` checks: `format`, `dpi`, `dimensions`, `font_settings`, `file_size`, `color_mode`; QA file-quality gates | Output exists, is non-empty, has an accepted extension/header, and all error-enforced preflight checks pass for the target format. |
| `FQ-H2` | Journal-safe geometry | `geometry_diagnostics` checks: `artists_outside_figure`, `journal_compliance`, `font_size_token_drift`; `visual_preflight_status` | Required text, marks, and panel chrome are not clipped; font sizes and line weights respect the selected style/journal floor. |
| `FQ-H3` | Readability collisions | `geometry_diagnostics` checks: `tick_label_overlaps`, `axis_label_title_overlap`, `figure_title_panel_title_overlap`, `colorbar_overlap`, `legend_internal_overlaps`, `artist_overlaps`, `point_annotation_overlaps` | Labels, ticks, legends, colorbars, annotations, and data marks do not overlap in a way that prevents reading values or labels. |
| `FQ-H4` | Data visibility | `geometry_diagnostics` checks: `artists_outside_axes`, `marker_marker_overlaps`, `blank_area_ratio`; data contract and semantic checks | Plotted data are visible inside the intended axes, severe overplotting is handled, and the rendered view matches the validated data contract. |
| `FQ-H5` | Traceability | provenance fingerprint, project config figure declaration, `figure_traceability_matrix`, regression state where configured | The figure can be traced to project config, script, input data, style target/profile, environment/provenance hash, and baseline comparison when a baseline is declared. |

## Advisory Polish

Advisory polish items do not automatically block publication, but they define
the review standard for a figure that looks finished rather than merely valid.

| ID | Advisory | Existing FigOps mapping | Review prompt |
| --- | --- | --- | --- |
| `FQ-A1` | Visual hierarchy | style profile, series styles, `legend_marker_consistency`, `font_size_token_drift` | Is the primary result visually dominant without hiding controls, uncertainty, or comparisons? |
| `FQ-A2` | Label density | `tick_label_crowding`, `point_label_skips`, `text_axis_edge_proximity` | Are labels sparse enough to scan, with dense categories abbreviated, rotated, faceted, or moved to a table when needed? |
| `FQ-A3` | Contrast and accessibility | `annotation_overlay_contrast`, style palette/profile checks where available | Are text, overlays, data series, confidence bands, and reference lines distinguishable in grayscale and color-vision-deficiency-safe review? |
| `FQ-A4` | Panel balance | multipanel layout options, `blank_area_ratio`, `shared_legend` output, panel labels | Do panels have consistent scale, margins, label placement, and legend strategy unless an intentional asymmetry is documented? |
| `FQ-A5` | Narrative clarity | project figure metadata, axis titles, legend labels, callouts, captions | Can a reviewer identify the measured quantity, units, groups, uncertainty, and takeaway without inspecting the plotting script? |

Advisory items can be accepted with a note when the target venue, figure type, or
data density justifies the tradeoff. Repeated advisory misses should become a
future diagnostic only after they can be measured deterministically.

## Diagnostic Mapping Policy

New geometry, preflight, or visual-regression diagnostics should declare one of:

- a hard-gate mapping: `FQ-H1` through `FQ-H5`;
- an advisory mapping: `FQ-A1` through `FQ-A5`;
- `informational`, when the metric is context for reviewers and must not affect
  status directly.

Do not add one-off warning names without a rubric mapping. The mapping should be
documented before the warning becomes part of generated tool output.

## Existing Diagnostic Name Map

Use these names exactly when translating FigOps render output into the rubric.
The current geometry diagnostics schema is `geometry_diagnostics/1`; MCP render
tools also summarize selected findings into `visual_preflight_status` and
`layout_report/1`.

| FigOps surface | Existing diagnostic names | Rubric mapping | Review effect |
| --- | --- | --- | --- |
| `validate_figure_preflight` | `format`, `dpi`, `dimensions`, `font_settings`, `file_size`, `color_mode` | `FQ-H1` | Blocking when an error-enforced check fails; skipped vector/raster-specific checks need a format reason. |
| `geometry_diagnostics/1` | `artists_outside_figure`, `journal_compliance`, `font_size_token_drift` | `FQ-H2` | Blocking when required artists clip or style/journal floors are violated. |
| `geometry_diagnostics/1` | `tick_label_overlaps`, `axis_label_title_overlap`, `figure_title_panel_title_overlap`, `colorbar_overlap`, `legend_internal_overlaps`, `artist_overlaps`, `point_annotation_overlaps` | `FQ-H3` | Blocking when collisions prevent reading labels, marks, legends, titles, or colorbars. |
| `geometry_diagnostics/1` | `artists_outside_axes`, `marker_marker_overlaps`, `blank_area_ratio` | `FQ-H4` | Blocking when data marks are hidden, clipped, or materially overplotted. |
| Data/provenance surfaces | `data_contract semantic checks`, `provenance`, project config figure declaration, `figure_traceability_matrix`, visual-regression baseline state | `FQ-H5` | Blocking when a reviewer cannot trace the output to inputs, code, config, style, environment, or declared baseline. |
| `geometry_diagnostics/1` | `legend_marker_consistency`, `font_size_token_drift` | `FQ-A1` | Advisory unless it also violates `FQ-H2`; use for hierarchy and style-role consistency. |
| `geometry_diagnostics/1` | `tick_label_crowding`, `point_label_skips`, `text_axis_edge_proximity` | `FQ-A2` | Advisory unless density or edge proximity makes labels unreadable enough to trigger `FQ-H3`. |
| `geometry_diagnostics/1` | `annotation_overlay_contrast` | `FQ-A3` | Advisory contrast/accessibility finding unless it prevents reading required text or data. |
| `geometry_diagnostics/1` | `blank_area_ratio`, `label_offset_consistency` | `FQ-A4` | Advisory panel-balance and placement-consistency finding unless data visibility is impaired. |
| Metadata/caption surfaces | project figure metadata, axis titles, legend labels, callouts, captions | `FQ-A5` | Advisory narrative review; no current hard diagnostic name. |
| `geometry_diagnostics/1` | `legend_data_collision` | `informational` | Context only: current implementation reports bbox-union overlap as non-blocking approximation. |

If a diagnostic appears in both hard-gate and advisory rows, apply the hard-gate
interpretation first, then record any remaining polish note under the advisory
item. Example: `font_size_token_drift` blocks only when the selected style or
journal floor is violated; smaller role-hierarchy drift can still be an `FQ-A1`
polish note.

## Acceptance Criteria

- Rubric markdown defines hard gates and advisory polish separately.
- Every hard gate maps to an existing FigOps check or documented QA/provenance
  surface.
- The rubric includes a compact mapping table for current
  `validate_figure_preflight` checks and `geometry_diagnostics/1` metric names.
- Advisory polish covers visual hierarchy, contrast, label density, panel
  balance, narrative clarity, and traceability context.
- The matching plan JSON parses and lists the same rubric IDs.
- `docs/QA.md` links this rubric and summarizes how to use it in release or
  figure review.

## Verification Commands

```bash
python3 -m json.tool docs/specs/2026-06-30-figure-quality-rubric.plan.json >/dev/null
python3 - <<'PY'
from pathlib import Path
md = Path("docs/specs/2026-06-30-figure-quality-rubric.md").read_text(encoding="utf-8")
required = ["FQ-H1", "FQ-H2", "FQ-H3", "FQ-H4", "FQ-H5", "FQ-A1", "FQ-A2", "FQ-A3", "FQ-A4", "FQ-A5"]
missing = [item for item in required if item not in md]
if missing:
    raise SystemExit(f"missing rubric ids: {missing}")
for phrase in ["Hard Gates", "Advisory Polish", "Diagnostic Mapping Policy"]:
    if phrase not in md:
        raise SystemExit(f"missing section: {phrase}")
for name in ["legend_data_collision", "label_offset_consistency", "geometry_diagnostics/1"]:
    if name not in md:
        raise SystemExit(f"missing diagnostic mapping: {name}")
PY
python3 - <<'PY'
from pathlib import Path
qa = Path("docs/QA.md").read_text(encoding="utf-8")
if "2026-06-30-figure-quality-rubric.md" not in qa:
    raise SystemExit("QA guide does not link the figure quality rubric")
PY
```
