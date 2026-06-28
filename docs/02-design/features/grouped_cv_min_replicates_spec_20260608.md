# Grouped CV and Replicate Count Data Contract Spec

- Date: 2026-06-08
- Scope: FigOps `data_contract.csv_checks[].semantic_checks`
- Status: implementation spec for Phase B calculation-check expansion

## Goal

Add two graph-specific calculation checks to FigOps:

- `min_replicates`: block rendering when each declared group does not contain enough repeated observations.
- `grouped_cv`: mark data as quality-failed when a numeric measurement has excessive coefficient of variation inside declared groups.

These checks belong in FigOps because insufficient repeats and group-level noise directly determine whether a plotted trend, bar, error bar, or replicate summary is scientifically defensible.

## Non-Goals

- Do not make FigOps a general statistics engine.
- Do not infer grouping columns automatically.
- Do not compute or validate full regression models in this slice.
- Do not change the global CV warning behavior yet; keep it backward compatible.
- Do not make grouped CV a hard blocker by default unless explicitly requested later.

## Config Contract

The checks live under existing `semantic_checks` so agents can keep one data-contract vocabulary.

```yaml
data_contract:
  cv_threshold: 0.10
  csv_checks:
    - path: "results/data/summary.csv"
      required_columns: ["sample", "condition", "value"]
      semantic_checks:
        value:
          min_replicates:
            group_by: ["condition"]
            min_count: 3
          grouped_cv:
            group_by: ["condition"]
            threshold: 0.15
```

### `min_replicates`

Required keys:

- `group_by`: non-empty list of column names.
- `min_count`: positive integer.

Runtime behavior:

- Strip-normalize group column names using the same column map as other data-contract checks.
- Count valid observations of the surrounding target column, not raw rows.
- A valid observation is target non-null and numeric when the target dtype is numeric. Non-numeric target columns fail before count evaluation.
- Rows with null group keys are counted as their own null-containing group by Pandas groupby with `dropna=False`.
- Fail the data contract when any group has fewer than `min_count` valid target observations.
- Emit group-level calculation-check violations and row-level diagnostic entries for up to 50 rows belonging to failing groups.

### `grouped_cv`

Required keys:

- `group_by`: non-empty list of column names.
- `threshold`: positive number.

Optional keys:

- `min_count`: positive integer; default `2`. Groups smaller than this are skipped by grouped CV and should be handled by `min_replicates` when replicate count matters.
- `warn_only`: boolean; default `true`.

Runtime behavior:

- Evaluate the target column named by the surrounding `semantic_checks` key.
- The target column must be numeric dtype. Object, string, or mixed target columns fail instead of being coerced or silently filtered.
- Null target values are excluded from the CV sample; `min_count` applies after null removal.
- For each group with at least `min_count` non-null numeric target values:
  - compute sample standard deviation divided by absolute mean,
  - skip groups whose absolute mean is below `1e-9`,
  - warn/fail only when CV is greater than `threshold`; CV exactly equal to threshold passes.
- With `warn_only: true`, `validate_data_contract()` still returns `True`, but a diagnostics sidecar records `quality_passed=false`.
- With `warn_only: false`, grouped CV violations fail the data contract.
- Missing `min_count` is allowed for `grouped_cv` and defaults to `2`.

## Diagnostics Contract

Grouped calculation checks should emit a common result shape before any file writing:

```json
{
  "name": "grouped_cv",
  "target": "value",
  "group_by": ["condition"],
  "source_config_path": "project_config.yaml",
  "status": "warning",
  "manual_review_needed": true,
  "message": "1 group(s) exceeded CV threshold 0.15",
  "violations": [
    {"group": {"condition": "B"}, "cv": 0.42, "threshold": 0.15, "count": 4}
  ]
}
```

Status values:

- `passed`
- `warning`
- `failed`
- `skipped`

Warning semantics:

- `grouped_cv` with `warn_only: true` returns `status: warning` and `manual_review_needed: true`.
- Warning-level checks must propagate into MCP render `status.json` and `manifest.json` so agents do not miss non-blocking scientific risk.
- Hard-failed checks must also map into existing row-level `row_violations` for report generation.

MCP render propagation:

- `manifest.json` must include top-level `calculation_checks`.
- `status.json` must include top-level `calculation_checks`.
- `calculation_checks` is an object with:

```json
{
  "checks": [],
  "quality_passed": true,
  "manual_review_needed": false
}
```

- The `checks` array uses the common result shape above, with `csv_path` added for each check.
- Any `status: warning` check sets `calculation_checks.manual_review_needed=true`.
- Any `status: warning` or `status: failed` check sets `calculation_checks.quality_passed=false`.
- Render envelope `warnings` should include calculation-check warning messages in addition to visual preflight and baseline warnings.

Grouped calculation checks should also create or update:

```text
results/diagnostics/calculation_checks.json
```

Payload shape:

```json
{
  "schema_version": "1.0",
  "checks": [
    {
      "csv_path": "results/data/summary.csv",
      "name": "min_replicates",
      "target": "value",
      "group_by": ["condition"],
      "source_config_path": "project_config.yaml",
      "status": "failed",
      "manual_review_needed": false,
      "message": "1 group(s) below min_count=3",
      "violations": [
        {"group": {"condition": "A"}, "count": 2, "expected": ">= 3"}
      ]
    },
    {
      "csv_path": "results/data/summary.csv",
      "name": "grouped_cv",
      "target": "value",
      "group_by": ["condition"],
      "source_config_path": "project_config.yaml",
      "status": "warning",
      "manual_review_needed": true,
      "message": "1 group(s) exceeded CV threshold 0.15",
      "violations": [
        {"group": {"condition": "B"}, "cv": 0.42, "threshold": 0.15, "count": 4}
      ]
    }
  ],
  "quality_passed": false,
  "manual_review_needed": true
}
```

This file is additive to the existing `quality_metrics.json`. The old sidecar remains backward compatible; `calculation_checks.json` is the richer agent-facing artifact.

Multi-check behavior:

- `calculation_checks.json` is aggregate latest-run state, not per-check overwrite.
- Every `csv_checks[]` entry and every grouped calculation check appends one entry to `checks`.
- Re-running `validate_data_contract()` rewrites the file for the current run.
- Null group keys are serialized as JSON `null`, never as `NaN`.

## Validation Rules

`validate_config()` must reject:

- `min_replicates` or `grouped_cv` values that are not mappings,
- missing or empty `group_by`,
- non-string `group_by` entries,
- missing or invalid `min_replicates.min_count`,
- invalid optional `grouped_cv.min_count`,
- missing or invalid `grouped_cv.threshold`,
- non-boolean `grouped_cv.warn_only`.

Runtime must reject:

- missing target column,
- missing group column,
- non-numeric target column for `grouped_cv`,
- non-numeric target column for `min_replicates` when valid observations are needed.

## Acceptance Tests

Focused tests:

- config accepts valid `min_replicates` and `grouped_cv`,
- config rejects malformed group checks,
- `min_replicates` passes when all groups meet count,
- `min_replicates` fails when any group is short,
- `min_replicates` counts valid non-null target observations, not raw rows,
- `grouped_cv` warns and writes `calculation_checks.json` when `warn_only` is default,
- `grouped_cv` fails when `warn_only: false`,
- grouped CV default `min_count=2` works when omitted,
- grouped CV threshold equality passes and strictly greater-than threshold warns/fails,
- grouped CV skips near-zero mean groups without crashing,
- grouped CV rejects non-numeric target columns,
- null group keys serialize as JSON `null`,
- multiple `csv_checks[]` entries aggregate into one latest-run `calculation_checks.json`.

Regression tests:

- existing global CV behavior remains unchanged,
- existing `monotonic` tests still pass,
- MCP render data-contract errors still set `manual_review_needed=true`,
- MCP render `grouped_cv warn_only=true` sets top-level `manual_review_needed=true`,
- MCP render `grouped_cv warn_only=true` records `calculation_checks` in `manifest.json` and `status.json`,
- MCP render envelope `warnings` includes grouped calculation warning messages.

## Implementation Plan

1. Add config parser validation tests and implementation for the new semantic vocabulary.
2. Add a small internal calculation-check result helper in `hub_core/data_contract.py`.
3. Add `min_replicates` runtime tests and implementation in `hub_core/data_contract.py`.
4. Add `grouped_cv` runtime tests, diagnostics sidecar, and implementation.
5. Propagate grouped warning results into MCP render `manifest.json`, `status.json`, and `manual_review_needed`.
6. Update `project_config_template.yaml` and `docs/internal/protocols/03_calculation_check_contract.md`.
7. Run:

```bash
python hub_uv.py run python -m pytest tests/test_data_contract_new.py tests/test_data_contract_quality.py tests/test_mcp_rendering.py -q
python hub_uv.py run --with ruff python -m ruff check hub_core/data_contract.py hub_core/config_parser.py tests/test_data_contract_new.py tests/test_data_contract_quality.py
```

## Open Risks

- `validate_data_contract()` currently returns a boolean, so warning-level grouped checks need an internal result collector plus sidecar/MCP propagation.
- Manifest propagation must be scoped narrowly to MCP render's temporary data-contract path first, then generalized later if needed.
- Group keys may include null values. This spec keeps them visible as explicit groups instead of dropping them silently.
