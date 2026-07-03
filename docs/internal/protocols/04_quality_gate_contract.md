# HKS 04 Quality Gate Contract

FigOps quality gates separate rendered output from publication-ready output.

## Required Result Fields

Every write-capable FigOps MCP result must preserve:

- `status`
- `operation_id`
- `job_id` when job-based
- `failure_stage`
- `resolution_hint`
- `created_paths`
- `modified_paths`
- `skipped_paths`
- `artifact_resources`
- `manual_review_needed`
- `manifest_path`
- `status_path`
- `latest_alias`

## Render Quality Fields

Render results must include:

- `style_summary`
- `visual_preflight_status`
- `artifact_status`
- `baseline_comparison`
- `geometry_diagnostics`
- `layout_report` when geometry diagnostics are collected

## Failure Stages

Allowed render-stage values:

```text
CONFIG
CONTRACT
EXPORT
TIMEOUT
PLOT
```

Clients may add adapter-side `HUB_PATH` when FigOps cannot be reached.

## Manual Review

`manual_review_needed=true` means the artifact may exist but cannot be treated as final. Agents must report this state.

Agents must inspect render results in this order:

1. `status`, `failure_stage`, and `resolution_hint`.
2. `manual_review_needed`.
3. `visual_preflight_status`.
4. `geometry_diagnostics.schema_version`.
5. `geometry_diagnostics.checks[]`.
6. `layout_report`, when present.
7. `baseline_comparison`, when a baseline was configured or requested. Claim a
   match or mismatch only when comparison actually ran.
8. Provenance and traceability fields.

Agents must not call an artifact publication-ready while
`manual_review_needed=true`. The correct state is `revise` or `blocked`
according to `docs/specs/2026-06-30-figure-quality-rubric.md`.

`manual_review_needed=false` does not by itself prove publication readiness. It
only means FigOps did not escalate an automated manual-review flag. Agents still
must cite hard-gate evidence and map advisory findings to the figure quality
rubric before using a `publishable`, `revise`, or `blocked` verdict.

## Geometry Diagnostics Consumption

Agents must treat `geometry_diagnostics` as objective diagnostic evidence, not
as a layout optimizer or subjective aesthetic score.

- Read `schema_version` before branching on check names. The current schema is
  `geometry_diagnostics/1`.
- Treat `passed is False` as a real finding.
- Treat `passed is None` as unmeasured. Do not count it as a pass.
- Treat missing diagnostics for a hard gate as `blocked` unless the result gives
  a valid format, runtime, dry-run, timeout, or engine-error reason.
- Branch on each check's `name`, `passed`, and `detail`. The check `data`
  payload is supporting evidence and may evolve.
- Diagnostics can trigger warnings and `manual_review_needed`, but they do not
  prove automatic geometry repair.
- `layout_report` is a summary aid. If it disagrees with
  `geometry_diagnostics.checks[]`, prefer the check-level diagnostics and report
  the inconsistency.

Agents must map diagnostic names to the rubric in
`docs/specs/2026-06-30-figure-quality-rubric.md` before assigning final impact:

- `FQ-H2`: required artists outside the figure, journal token failures, or font
  floor violations.
- `FQ-H3`: blocking label, title, legend, colorbar, annotation, or data-artist
  collisions.
- `FQ-H4`: hidden, clipped, or materially overplotted data.
- `FQ-A1` through `FQ-A4`: hierarchy, density, contrast, edge-proximity, and
  panel-balance polish unless the finding blocks interpretation.
- `informational`: context-only diagnostics such as the current
  `legend_data_collision` approximation.

## Journal Token Claims

Journal compliance claims are limited to the encoded FigOps token set unless an
agent cites a dated external publisher-guideline verification. The encoded set
includes selected `target_format`, style profile, minimum font size, minimum
line width, maximum encoded figure height, and applicable preflight checks.

Allowed wording:

- "The selected encoded FigOps target/profile was applied" when config parsing
  selected it.
- "Encoded font, line, height, and preflight checks passed or failed" when those
  checks actually ran.
- "The artifact is publication-oriented and still needs manual review when
  flagged."

Disallowed wording without extra evidence:

- "The output matches the latest publisher instructions."
- "All labels are optimally placed."
- "The graph is publication-ready" when `manual_review_needed=true`, a hard gate
  failed, or a hard gate is unmeasured without a valid reason.
- "`publishable` means the graph is ready without checking the cited hard-gate
  evidence."

See `docs/specs/2026-07-03-graph-tool-qa-review.md` for the graph-tool
qualification matrix and agent response template.

## Path Safety

Diagnostics must sanitize local absolute paths. Explicit artifact paths and `file://` resources may be returned for generated outputs.
