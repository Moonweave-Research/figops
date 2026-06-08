# Log Scale and Error-Bar Calculation Checks Spec

- Date: 2026-06-08
- Scope: Graph Hub `data_contract.csv_checks[].semantic_checks`
- Status: implementation spec for Phase B calculation-check expansion

## Goal

Add three graph-specific calculation checks:

- `log_scale_positive`: fail when a declared log-scale target contains non-positive values.
- `error_bar_source`: fail when a declared error-bar column is missing, non-numeric, negative, or null.
- `mean_sem`: fail when summary data declares SEM but `sem != std / sqrt(n)` within tolerance.

These are Graph Hub responsibilities because log axes and error bars directly affect whether a rendered scientific graph is valid.

## Config Contract

```yaml
data_contract:
  csv_checks:
    - path: "results/data/summary.csv"
      required_columns: ["condition", "mean", "std", "sem", "n"]
      semantic_checks:
        mean:
          log_scale_positive: true
          error_bar_source:
            column: "sem"
            source: "sem"
          mean_sem:
            sem_column: "sem"
            std_column: "std"
            n_column: "n"
            tolerance: 1.0e-6
```

## Runtime Contract

### `log_scale_positive`

- Value must be boolean.
- When `true`, the surrounding target column must be numeric and every non-null value must be strictly greater than 0.
- Null handling remains owned by `allow_null`.
- Failure blocks the data contract.

### `error_bar_source`

Required keys:

- `column`: non-empty string naming the error-bar column.

Optional keys:

- `source`: non-empty string; default `custom`.

Runtime behavior:

- The error-bar column must exist, be numeric, contain no nulls, and contain no negative values.
- Zero is allowed.
- Failure blocks the data contract.

### `mean_sem`

Required keys:

- `sem_column`: non-empty string.
- `std_column`: non-empty string.
- `n_column`: non-empty string.

Optional keys:

- `tolerance`: non-negative number; default `1.0e-6`.

Runtime behavior:

- `sem_column`, `std_column`, and `n_column` must exist and be numeric.
- `n_column` values must be positive.
- `sem_column` and `std_column` values must be non-negative and non-null.
- For every row, `abs(sem - std / sqrt(n)) <= tolerance`.
- Failure blocks the data contract.

## Diagnostics Contract

Each check appends the existing `calculation_checks` result shape:

```json
{
  "csv_path": "results/data/summary.csv",
  "name": "mean_sem",
  "target": "mean",
  "group_by": [],
  "source_config_path": "project_config.yaml",
  "status": "failed",
  "manual_review_needed": false,
  "message": "Column 'mean': 1 SEM value(s) inconsistent with std/sqrt(n)",
  "violations": [
    {"row": "2", "sem": 0.3, "expected": 0.25, "tolerance": 1e-6}
  ]
}
```

`calculation_checks.json` remains latest-run aggregate state.

## Acceptance Tests

- `validate_config()` accepts valid `log_scale_positive`, `error_bar_source`, and `mean_sem`.
- `validate_config()` rejects malformed values for all three checks.
- `log_scale_positive` fails on zero or negative target values.
- `error_bar_source` fails on negative error values.
- `mean_sem` passes when SEM equals `std / sqrt(n)`.
- `mean_sem` fails when SEM differs by more than tolerance.
- `calculation_checks.json` records failed check name, target, message, and row-level violation.

## Non-Goals

- Do not infer whether a plot uses log axes.
- Do not compute means, standard deviations, or SEM from raw replicate tables in this slice.
- Do not validate confidence intervals in this slice.
