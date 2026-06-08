# Linear Fit, Outlier Flag, and Axis Unit Checks Spec

- Date: 2026-06-08
- Scope: Graph Hub `data_contract.csv_checks[].semantic_checks`
- Status: implementation spec for final Phase B calculation-check expansion

## Goal

Add the remaining graph-specific calculation checks:

- `linear_fit`: validate declared linear-fit metadata against `y = slope * x + intercept`.
- `outlier_flag`: validate an outlier/anomaly flag column used by plotting.
- `axis_unit`: validate declared display axis units against data units.

These checks belong in Graph Hub because fit annotations, excluded/outlier marks, and axis units directly affect whether a rendered figure is scientifically interpretable.

## Config Contract

```yaml
data_contract:
  csv_checks:
    - path: "results/data/fit_summary.csv"
      required_columns: ["x", "y", "outlier", "unit"]
      semantic_checks:
        y:
          linear_fit:
            x_column: "x"
            slope: 2.0
            intercept: 1.0
            r2_min: 0.98
            tolerance: 1.0e-6
          outlier_flag:
            column: "outlier"
            allowed: [0, 1]
            max_fraction: 0.2
          axis_unit:
            data_unit: "mA"
            display_unit: "A"
```

## Runtime Contract

### `linear_fit`

Required keys:

- `x_column`: non-empty string.
- `slope`: finite number.
- `intercept`: finite number.

Optional keys:

- `r2_min`: number in `[0, 1]`; default omitted.
- `tolerance`: non-negative number; default `1.0e-6`.

Runtime behavior:

- The surrounding target column and `x_column` must exist and be numeric.
- Only finite, non-null x/y rows participate in fit validation.
- Rows where exactly one of x/y is null or non-finite fail; paired null x/y rows are ignored.
- At least two participating rows are required for any `linear_fit` check.
- Every participating row must satisfy `abs(y - (slope * x + intercept)) <= tolerance`.
- If `r2_min` is declared, compute R² from participating rows and fail when `R² < r2_min`.
- If total y variance is zero and `r2_min` is declared, R² is treated as `1.0` only when all residuals are within tolerance; otherwise it fails.
- Row-level tolerance violations and R² violations are recorded in one `linear_fit` calculation-check entry.
- Failure blocks the data contract and appends a `calculation_checks` entry.

### `outlier_flag`

Required keys:

- `column`: non-empty string.

Optional keys:

- `allowed`: list of allowed scalar values; default `[0, 1, true, false, "0", "1", "true", "false"]`.
- `max_fraction`: number in `[0, 1]`; default omitted.

Runtime behavior:

- The flag column must exist and contain no null values.
- Every value must be in `allowed` after canonicalization.
- Canonicalization trims string values and lowercases them. Boolean and integer values stay type-aware: `true`, `1`, and `"1"` are all outlier-positive; `false`, `0`, and `"0"` are not.
- If `max_fraction` is declared, outlier fraction is computed as outlier-positive values divided by total non-null flag rows.
- Fail when outlier fraction is greater than `max_fraction`; equality passes.
- Failure blocks the data contract and appends a `calculation_checks` entry.

### `axis_unit`

Required keys:

- `data_unit`: non-empty string.
- `display_unit`: non-empty string.

Runtime behavior:

- Uses Pint compatibility checks but does not mutate dataframe values.
- `data_unit` is the unit of numeric data already present in the CSV.
- `display_unit` is the intended axis/display unit.
- Compatible but non-identical units pass and record a conversion factor for downstream consumers.
- If Pint is available, incompatible units fail.
- If Pint is unavailable or unit parsing is unavailable, the check is `skipped` with `manual_review_needed=true`.
- A skipped `axis_unit` check does not block `validate_data_contract()`, but records `quality_passed=false` and `manual_review_needed=true` in `calculation_checks.json`.
- MCP render must propagate skipped `axis_unit` into the render envelope `warnings`, `manifest.json`, and `status.json` through top-level `calculation_checks`.

## Validation Rules

`validate_config()` and direct runtime validation must reject malformed values without crashing:

- `linear_fit` must be a mapping.
- `linear_fit.x_column` must be a non-empty string.
- `linear_fit.slope` and `linear_fit.intercept` must be finite numbers.
- Optional `linear_fit.r2_min` must be a number in `[0, 1]`.
- Optional `linear_fit.tolerance` must be a non-negative finite number.
- `outlier_flag` must be a mapping.
- `outlier_flag.column` must be a non-empty string.
- Optional `outlier_flag.allowed` must be a non-empty list of scalar string/number/boolean values.
- Optional `outlier_flag.max_fraction` must be a number in `[0, 1]`.
- `axis_unit` must be a mapping.
- `axis_unit.data_unit` and `axis_unit.display_unit` must be non-empty strings.

## Diagnostics Contract

Each check appends the existing `calculation_checks` result shape:

```json
{
  "csv_path": "results/data/fit_summary.csv",
  "name": "linear_fit",
  "target": "y",
  "group_by": [],
  "source_config_path": "project_config.yaml",
  "status": "failed",
  "manual_review_needed": false,
  "message": "Column 'y': 1 value(s) inconsistent with declared linear fit",
  "violations": [
    {"row": "2", "observed": 7.2, "expected": 7.0, "tolerance": 1e-6}
  ]
}
```

Status values remain `passed`, `warning`, `failed`, or `skipped`.

Lifecycle and propagation:

- Passed, failed, warning, and skipped entries are appended to the current run aggregate.
- Re-running validation rewrites current state and removes stale sidecars when no calculation checks run.
- MCP render must include top-level `calculation_checks` in the tool response, dry-run response, `manifest.json`, and `status.json`.
- MCP render warnings must include skipped `axis_unit` messages.
- MCP `csv_path` may be runtime-local; agents must use it as metadata and not as a citation source path.

## Acceptance Tests

- `validate_config()` accepts valid `linear_fit`, `outlier_flag`, and `axis_unit`.
- `validate_config()` rejects malformed values for all three checks.
- `linear_fit` passes exact linear data and fails inconsistent rows.
- `linear_fit` fails when declared `r2_min` is not met.
- `linear_fit` fails on fewer than two participating rows, paired finite/non-finite row mismatch, non-finite values, and malformed tolerance without crashing.
- `outlier_flag` fails values outside `allowed`.
- `outlier_flag` fails only when fraction is greater than `max_fraction`.
- `outlier_flag` canonicalizes string boolean/integer values consistently.
- `axis_unit` records passed/failed/skipped calculation check status according to unit compatibility availability.
- `axis_unit` does not mutate dataframe values.
- MCP render propagates skipped `axis_unit` into response, `manifest.json`, and `status.json`.
- `calculation_checks.json` preserves latest-run aggregate/stale cleanup behavior.
- `calculation_checks.json` records failed/skipped check name, target, message, and violations.

## Non-Goals

- Do not fit or infer slope/intercept from data in this slice.
- Do not support nonlinear regression in this slice.
- Do not infer axis units from labels or plot scripts.
- Do not define a general outlier detection algorithm.
