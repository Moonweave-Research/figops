# Graph Tool QA Review for Agents

Source of truth: `docs/specs/2026-07-03-graph-tool-qa-review.plan.json`

Review date: 2026-07-03

## Objective

Define the current quality claim FigOps agents may make about rendered graphs
before public-facing documentation says "publication-ready". This review is a
qualification gate, not a feature announcement. It records what is guaranteed,
what is best-effort, what is diagnostic-only, and what still requires manual
review.

## Scope

- FigOps graph renderers under `plotting/`.
- Journal and style tokens under `themes/`.
- Geometry diagnostics, layout reports, preflight, and MCP render result
  envelopes under `hub_core/`.
- QA and agent-facing documentation under `docs/`.

Out of scope:

- Fresh verification against the latest external publisher web pages.
- Automated aesthetic scoring.
- Claims that every crowded graph can be optimally relaid out without human
  review.

## Research and Prior Art

This review builds on:

- `docs/specs/2026-06-30-figure-quality-rubric.md`, which defines hard gates
  `FQ-H1` through `FQ-H5` and advisory polish `FQ-A1` through `FQ-A5`.
- `docs/QA.md`, which maps current diagnostics to the rubric.
- Existing geometry diagnostics and MCP result fields:
  `geometry_diagnostics/1`, `layout_report/1`, `visual_preflight_status`, and
  `manual_review_needed`.

Key code evidence:

- Point labels in the bridge renderer use static offsets and optional compass
  fanout, not a global optimizer:
  `plotting/renderers/labels.py`.
- A stronger `adjustText` helper exists in `plotting/utils.py`, but it is not
  the default bridge label path.
- Smart legends test a small set of placements and fall back to top-outside
  placement:
  `plotting/renderers/legend.py`.
- Annotation `avoid_overlap` uses preset offsets from the same fanout table:
  `plotting/renderers/overlays.py`.
- Geometry failures are converted into warnings, layout reports, and
  `manual_review_needed`:
  `hub_core/mcp/render_geometry.py` and `hub_core/mcp/tools/render_csv.py`.
- Journal compliance checks current encoded minimum font size, line width, and
  height tokens:
  `hub_core/geometry_style_checks.py`.
- Journal target tokens include several documented tool defaults or Graph Hub
  assumptions:
  `themes/style_profiles.py`.

## Product Position and Non-Goals

Approved agent wording:

> FigOps is a publication-oriented graph rendering and QA tool. It applies
> journal/style tokens, runs artifact preflight, reports geometry diagnostics,
> tracks provenance, and escalates questionable outputs to manual review.

Disallowed agent wording unless future implementation changes:

- "All labels are optimally placed."
- "Every graph is automatically publication-ready."
- "The selected journal format is guaranteed to match the latest publisher
  instructions."
- "manual_review_needed=false is a substitute for human scientific review."
- "`publishable` means the graph is ready for public or submission use without
  checking the cited hard-gate evidence."

Non-goals for the current tool qualification:

- No subjective beauty score as a hard gate.
- No LLM-only visual judgment as a pass/fail criterion.
- No claim of current external journal policy compliance without dated source
  verification.

## Current Qualification Matrix

| Capability | Current status | Agent claim policy | Evidence |
| --- | --- | --- | --- |
| Output existence, headers, file size, basic format | Guaranteed when preflight passes | May say artifact integrity passed | `hub_core/figure_preflight.py` |
| Raster DPI metadata | Conditional | May say checked when metadata exists; skipped metadata remains a warning | `hub_core/figure_preflight.py` |
| PDF font Type3 detection | Conditional | May say PDF font safety was inspected for PDF outputs | `hub_core/figure_preflight.py` |
| Journal target enum and style tokens | Available for encoded targets | May say selected encoded target/profile was applied when config parsing selected it | `hub_core/config_parser.py`, `themes/style_profiles.py` |
| Journal minimum font, line, height check | Available for encoded tokens | May say encoded minimum floors passed or failed when the check ran | `hub_core/geometry_style_checks.py` |
| Current official publisher compliance | Not guaranteed by this review | Must not claim without dated external verification | `themes/style_profiles.py` comments include tool defaults and assumptions |
| Point label placement | Best-effort | May say labels were placed with configured offsets/fanout and diagnostics checked | `plotting/renderers/labels.py` |
| Point label optimality | Unsupported | Must not claim | Static offset/fanout implementation |
| Annotation overlap avoidance | Best-effort | May say preset callout offset was used when requested | `plotting/renderers/overlays.py` |
| Legend placement | Best-effort | May say smart placement attempted candidate positions | `plotting/renderers/legend.py` |
| Geometry overlap detection | Diagnostic | May say diagnostics reported no blocking findings only for measured checks whose `passed` value is true | `hub_core/geometry_diagnostics.py` |
| Geometry auto-repair | Limited | Must not imply full repair loop | diagnostics feed warnings/manual review |
| Visual regression | Conditional on baseline policy and runtime support | May say baseline matched or mismatched only when a baseline comparison actually ran | `hub_core/visual_regression.py` |
| Aesthetic polish | Manual/advisory | Must use rubric status: publishable, revise, or blocked | `docs/specs/2026-06-30-figure-quality-rubric.md` |

## Workflow Architecture

Agents should treat figure QA as a team-mode review with five independent
voices, even when a single agent executes it:

1. Contract reviewer: validates data contract, semantic checks, and provenance.
2. Layout reviewer: inspects `geometry_diagnostics`, `layout_report`, label
   density, overlap, clipping, and legend placement.
3. Style reviewer: checks selected target/profile, encoded journal floors,
   palette/profile consistency, and font-role drift.
4. Regression reviewer: checks baseline comparison, dependency/runtime notes,
   and artifact determinism.
5. Documentation reviewer: ensures the final claim does not exceed the evidence.

The reviewers fan in to a single verdict:

- `publishable`: cited hard gates pass, `manual_review_needed` is not true, and
  advisory issues do not obscure the result.
- `revise`: hard gates pass, but polish or documentation caveats remain.
- `blocked`: any hard gate fails, is unmeasured without a valid format/runtime
  reason, or `manual_review_needed=true` is unresolved.

## Execution Model

For render tool outputs, agents must process fields in this order:

1. Check `status`, `failure_stage`, and `resolution_hint`.
2. If `manual_review_needed=true`, do not claim publication readiness.
3. Inspect `visual_preflight_status` for artifact, format, DPI, dimensions,
   font, color, and overlap warnings.
4. Inspect `geometry_diagnostics.schema_version` before using check names.
5. Treat `passed is False` as a real finding and `passed is None` as unmeasured.
6. Inspect `layout_report.overlaps`, `layout_report.clipped`,
   `layout_report.placement_consistency`, and `layout_report.warnings`.
7. Inspect `baseline_comparison` when a baseline path or baseline policy is in
   force.
8. Map findings to `FQ-H*` or `FQ-A*` using
   `docs/specs/2026-06-30-figure-quality-rubric.md`.
9. Produce one verdict with evidence and caveats.

## Safety and Verification Gates

Hard safety gates:

- A result with `manual_review_needed=true` cannot be described as final or
  publication-ready.
- A result with `manual_review_needed=false` is eligible for a rubric verdict,
  but still needs cited hard-gate evidence before agents call it `publishable`.
- A journal target can only be described as compliant with the encoded FigOps
  token set unless dated external publisher guidance was separately checked.
- A diagnostic with `passed is None` cannot be treated as a pass.
- A dense label, annotation, or legend result cannot be called optimal unless a
  future optimizer proves that claim with a deterministic acceptance test.

Recommended verification commands for this document:

```bash
python -m json.tool docs/specs/2026-07-03-graph-tool-qa-review.plan.json >nul
python - <<'PY'
from pathlib import Path
doc = Path("docs/specs/2026-07-03-graph-tool-qa-review.md").read_text(encoding="utf-8")
for phrase in [
    "Current Qualification Matrix",
    "manual_review_needed=true",
    "Point label optimality",
    "publication-oriented",
    "Execution Model",
]:
    if phrase not in doc:
        raise SystemExit(f"missing phrase: {phrase}")
PY
```

## Evaluation Fixtures

Before promoting the graph tool as more than publication-oriented, add or keep
fixtures that cover:

- Crowded point labels with identical or near-identical coordinates.
- Dense legends over data, legends inside axes, and forced outside legends.
- Long category labels in bar, box, violin, and facet plots.
- Multipanel figures with shared legends, panel labels, mixed scales, and
  unequal text density.
- Annotation overlays with low contrast, leader lines, and callout offsets.
- Journal target snapshots for Nature, Science, ACS, RSC, Elsevier, Wiley, and
  Cell encoded token floors.
- Visual regression fixtures tied to the locked Matplotlib/Pillow stack.

## Release and Documentation Plan

Documentation must land in this order:

1. Publish this qualification review as the claim boundary.
2. Link it from `docs/QA.md`.
3. Add the agent consumption rules to `docs/internal/protocols/04_quality_gate_contract.md`.
4. Keep README wording broad unless the claim is backed by a hard gate:
   "publication-oriented" is safe; unconditional "publication-ready" needs the
   rubric verdict and manual review state.
5. If external journal compliance is marketed, add a dated publisher-guideline
   matrix with source URLs, checked dates, encoded token values, and fixture
   coverage.

## Agent Response Template

Use this compact template after a render or QA review:

```text
Verdict: publishable | revise | blocked

Hard gates:
- FQ-H1 artifact integrity: pass/fail/unmeasured
- FQ-H2 journal-safe geometry: pass/fail/unmeasured
- FQ-H3 readability collisions: pass/fail/unmeasured
- FQ-H4 data visibility: pass/fail/unmeasured
- FQ-H5 traceability: pass/fail/unmeasured

Advisory polish:
- FQ-A1 visual hierarchy:
- FQ-A2 label density:
- FQ-A3 contrast/accessibility:
- FQ-A4 panel balance:
- FQ-A5 narrative clarity:

Claim boundary:
- Journal compliance means encoded FigOps token compliance unless dated
  external publisher verification is cited.
- If manual_review_needed=true, this is not publication-ready yet.
- If manual_review_needed=false, cite the hard-gate evidence before saying
  publishable.
```
