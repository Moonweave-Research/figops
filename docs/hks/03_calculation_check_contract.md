# HKS 03 Calculation Check Contract

Graph Hub owns graph-specific calculation checks.

## Scope

Graph Hub validates calculations that affect figure correctness. It does not replace general physics derivation, literature interpretation, or broad multi-tool reasoning.

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

## Required Future Vocabulary

Future calculation checks should use stable names:

- `monotonic`
- `min_replicates`
- `grouped_cv`
- `mean_sem`
- `error_bar_source`
- `linear_fit`
- `log_scale_positive`
- `outlier_flag`
- `axis_unit`

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
