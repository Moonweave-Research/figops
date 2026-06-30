"""Scalar semantic checks for data-contract validation."""

from __future__ import annotations

from typing import Any


def check_allow_null_constraint(series: Any, col: str, max_row_detail: int) -> tuple[list[str], list[dict[str, str]]]:
    if not series.isnull().any():
        return [], []

    null_count = int(series.isnull().sum())
    errors = [f"Column '{col}': found {null_count} null value(s) (allow_null=false)"]
    row_violations = []
    null_rows = series[series.isnull()].index[:max_row_detail]
    for idx in null_rows:
        row_violations.append(
            {
                "row": str(idx),
                "column": col,
                "value": "NaN",
                "expected": "non-null",
                "violation_type": "null_found",
            }
        )
    return errors, row_violations


def check_range_constraint(
    series: Any,
    col: str,
    val_range: Any,
    max_row_detail: int,
) -> tuple[list[str], list[dict[str, str]]]:
    try:
        from pandas.api.types import is_numeric_dtype
    except Exception:
        is_numeric_dtype = None

    min_val, max_val = val_range
    if not (isinstance(min_val, (int, float)) and isinstance(max_val, (int, float))):
        return [f"Column '{col}': range bounds must be numeric, got {val_range}"], []
    if min_val > max_val:
        return [f"Column '{col}': range min must be <= max (got [{min_val}, {max_val}])"], []
    if is_numeric_dtype is not None and not is_numeric_dtype(series):
        return [
            f"Column '{col}': range target column must be numeric (possible locale/decimal parsing issue)"
        ], []

    mask = (series < min_val) | (series > max_val)
    if not mask.any():
        return [], []

    violation_count = int(mask.sum())
    observed_min = series.min()
    observed_max = series.max()
    errors = [
        f"Column '{col}': {violation_count} value(s) out of range "
        f"[{min_val}, {max_val}]. "
        f"(Observed: {observed_min} to {observed_max})"
    ]
    row_violations = []
    bad_rows = series[mask].index[:max_row_detail]
    for idx in bad_rows:
        row_violations.append(
            {
                "row": str(idx),
                "column": col,
                "value": str(series.loc[idx]),
                "expected": f"range [{min_val}, {max_val}]",
                "violation_type": "out_of_range",
            }
        )
    return errors, row_violations


def check_unique_constraint(series: Any, col: str, max_row_detail: int) -> tuple[list[str], list[dict[str, str]]]:
    if series.is_unique:
        return [], []

    dup_count = int(series.duplicated().sum())
    errors = [f"Column '{col}': found {dup_count} duplicate value(s) (unique=true)"]
    row_violations = []
    dup_rows = series[series.duplicated(keep=False)].index[:max_row_detail]
    for idx in dup_rows:
        row_violations.append(
            {
                "row": str(idx),
                "column": col,
                "value": str(series.loc[idx]),
                "expected": "unique",
                "violation_type": "duplicate",
            }
        )
    return errors, row_violations
