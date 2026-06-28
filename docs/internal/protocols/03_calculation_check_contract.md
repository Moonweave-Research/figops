# HKS 03 Calculation Check Contract

FigOps owns graph-specific calculation checks.

## Scope

FigOps validates calculations that affect figure correctness. It does not replace general physics derivation, literature interpretation, or broad multi-tool reasoning.

## Current Checks

Current `data_contract.csv_checks` supports:

- required columns,
- dtype checks,
- minimum row count,
- range,
- null allowance,
- uniqueness,
- unit compatibility when `pint` is available,
- CV quality warnings.
- monotonicity when declared,
- minimum replicate count per declared group,
- grouped CV warnings or failures per declared group.
- log-scale positivity when declared,
- error-bar source column validation,
- SEM consistency against std/sqrt(n),
- declared linear-fit consistency,
- outlier/anomaly flag validation,
- axis display unit compatibility.

## Stable Vocabulary

Calculation checks use stable names:

- `min_replicates`
- `grouped_cv`
- `log_scale_positive`
- `error_bar_source`
- `mean_sem`
- `linear_fit`
- `outlier_flag`
- `axis_unit`

`axis_unit` is compatibility-only: it records display conversion metadata and
does not mutate dataframe values. If Pint is unavailable or cannot parse a unit,
the check is recorded as `status=skipped` with `manual_review_needed=true`.

## Manifest Requirements

Calculation check results must be recorded in render or project manifests with:

- check name,
- target column or group,
- status,
- warning or error message,
- manual review requirement,
- source config path.

## Agent Rules

- Do not silently compute a graph from failed data checks.
- Use `manual_review_needed=true` when a calculation check warns but does not block render.
- Keep domain formulas in HKS methodology docs or project docs unless they are part of graph validation.
