from __future__ import annotations

import math

from .data_contract_calculation_checks import (
    append_calculation_check,
    append_failed_calculation_check,
    is_nullish,
    json_safe_value,
)


def numeric_series_or_error(df, stripped_to_actual, column_name: str, check_name: str):
    try:
        from pandas.api.types import is_numeric_dtype
    except Exception:
        is_numeric_dtype = None

    normalized = str(column_name).strip()
    actual = stripped_to_actual.get(normalized)
    if actual is None:
        return None, f"{check_name} column '{column_name}' not found"
    series = df[actual]
    if is_numeric_dtype is not None and not is_numeric_dtype(series):
        return None, f"{check_name} column '{column_name}' must be numeric"
    return series, None


def check_log_scale_positive_constraint(
    series,
    col,
    max_row_detail: int,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    try:
        from pandas.api.types import is_numeric_dtype
    except Exception:
        is_numeric_dtype = None

    if is_numeric_dtype is not None and not is_numeric_dtype(series):
        message = f"Column '{col}': log_scale_positive target column must be numeric"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="log_scale_positive",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[],
        )
        return [message], []

    finite_mask = series.map(lambda value: math.isfinite(float(value)) if not is_nullish(value) else True)
    mask = series.notna() & (~finite_mask | (series <= 0))
    if not mask.any():
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="log_scale_positive",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"Column '{col}' contains only positive non-null values for log scale",
            violations=[],
        )
        return [], []

    bad_rows = series[mask].index[:max_row_detail]
    violations = [
        {"row": str(idx), "value": json_safe_value(series.loc[idx]), "expected": "> 0 and finite"}
        for idx in bad_rows
    ]
    row_violations = [
        {
            "row": str(idx),
            "column": col,
            "value": str(series.loc[idx]),
            "expected": "> 0 and finite for log scale",
            "violation_type": "log_scale_non_positive",
        }
        for idx in bad_rows
    ]
    message = f"Column '{col}': {int(mask.sum())} non-positive or non-finite value(s) invalid for log scale"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="log_scale_positive",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations


def check_error_bar_source_constraint(
    df,
    col,
    raw_check,
    stripped_to_actual,
    max_row_detail: int,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': error_bar_source must be a mapping"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="error_bar_source",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    error_column = raw_check.get("column")
    error_series, error = numeric_series_or_error(df, stripped_to_actual, str(error_column), "error_bar_source")
    if error:
        message = f"Column '{col}': {error}"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="error_bar_source",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    mask = error_series.isna() | (error_series < 0)
    if not mask.any():
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="error_bar_source",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"Error bar column '{error_column}' is valid",
            violations=[],
        )
        return [], []

    bad_rows = error_series[mask].index[:max_row_detail]
    violations = [
        {
            "row": str(idx),
            "column": str(error_column),
            "value": json_safe_value(error_series.loc[idx]),
            "expected": ">= 0",
        }
        for idx in bad_rows
    ]
    row_violations = [
        {
            "row": str(idx),
            "column": str(error_column),
            "value": str(error_series.loc[idx]),
            "expected": "non-null and >= 0",
            "violation_type": "invalid_error_bar",
        }
        for idx in bad_rows
    ]
    message = f"Column '{col}': {int(mask.sum())} invalid error-bar value(s) in '{error_column}'"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="error_bar_source",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations


def check_mean_sem_constraint(
    df,
    col,
    raw_check,
    stripped_to_actual,
    max_row_detail: int,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': mean_sem must be a mapping"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="mean_sem",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    sem_column = raw_check.get("sem_column")
    std_column = raw_check.get("std_column")
    n_column = raw_check.get("n_column")
    sem, sem_error = numeric_series_or_error(df, stripped_to_actual, str(sem_column), "mean_sem")
    std, std_error = numeric_series_or_error(df, stripped_to_actual, str(std_column), "mean_sem")
    n_values, n_error = numeric_series_or_error(df, stripped_to_actual, str(n_column), "mean_sem")
    errors = [error for error in (sem_error, std_error, n_error) if error]
    if errors:
        message = f"Column '{col}': {errors[0]}"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="mean_sem",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    try:
        tolerance = float(raw_check.get("tolerance", 1.0e-6))
    except (TypeError, ValueError):
        message = f"Column '{col}': mean_sem.tolerance must be a non-negative number"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="mean_sem",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    if tolerance < 0:
        message = f"Column '{col}': mean_sem.tolerance must be a non-negative number"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="mean_sem",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    finite_mask = sem.map(lambda value: math.isfinite(float(value)) if not is_nullish(value) else False)
    finite_mask = finite_mask & std.map(lambda value: math.isfinite(float(value)) if not is_nullish(value) else False)
    finite_mask = finite_mask & n_values.map(
        lambda value: math.isfinite(float(value)) if not is_nullish(value) else False
    )
    valid_mask = finite_mask & (sem >= 0) & (std >= 0) & (n_values > 0)
    expected = sem.copy()
    expected[:] = None
    expected.loc[valid_mask] = std.loc[valid_mask] / n_values.loc[valid_mask].map(math.sqrt)
    mask = ~valid_mask
    mask = mask | (valid_mask & ((sem - expected).abs() > tolerance))
    if not mask.any():
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="mean_sem",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"SEM column '{sem_column}' matches std/sqrt(n)",
            violations=[],
        )
        return [], []

    bad_rows = sem[mask].index[:max_row_detail]
    violations = [
        {
            "row": str(idx),
            "sem": json_safe_value(sem.loc[idx]),
            "expected": json_safe_value(expected.loc[idx]) if idx in expected.index else None,
            "tolerance": tolerance,
        }
        for idx in bad_rows
    ]
    row_violations = [
        {
            "row": str(idx),
            "column": str(sem_column),
            "value": str(sem.loc[idx]),
            "expected": f"std/sqrt(n) within tolerance {tolerance}",
            "violation_type": "mean_sem_mismatch",
        }
        for idx in bad_rows
    ]
    message = f"Column '{col}': {int(mask.sum())} SEM value(s) inconsistent with std/sqrt(n)"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="mean_sem",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations


def finite_float(value):
    if isinstance(value, bool) or is_nullish(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def check_linear_fit_constraint(
    df,
    series,
    col,
    raw_check,
    stripped_to_actual,
    max_row_detail: int,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': linear_fit must be a mapping"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    x_column = str(raw_check.get("x_column", "")).strip()
    x_series, x_error = numeric_series_or_error(df, stripped_to_actual, x_column, "linear_fit")
    y_series, y_error = numeric_series_or_error(df, stripped_to_actual, str(col), "linear_fit")
    for error in (x_error, y_error):
        if error:
            message = f"Column '{col}': {error}"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="linear_fit",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []

    slope = finite_float(raw_check.get("slope"))
    intercept = finite_float(raw_check.get("intercept"))
    tolerance = finite_float(raw_check.get("tolerance", 1.0e-6))
    r2_min = finite_float(raw_check.get("r2_min")) if "r2_min" in raw_check else None
    if slope is None or intercept is None:
        message = f"Column '{col}': linear_fit slope and intercept must be finite numbers"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    if tolerance is None or tolerance < 0:
        message = f"Column '{col}': linear_fit.tolerance must be a non-negative finite number"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    if "r2_min" in raw_check and (r2_min is None or not 0 <= r2_min <= 1):
        message = f"Column '{col}': linear_fit.r2_min must be between 0 and 1"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    paired_values = []
    violations = []
    row_violations = []
    invalid_pair_count = 0
    for idx in series.index:
        x_value = finite_float(x_series.loc[idx])
        y_value = finite_float(series.loc[idx])
        if x_value is None and y_value is None:
            continue
        if x_value is None or y_value is None:
            invalid_pair_count += 1
            if len(violations) < max_row_detail:
                violations.append(
                    {
                        "row": str(idx),
                        "x": json_safe_value(x_series.loc[idx]),
                        "y": json_safe_value(series.loc[idx]),
                        "expected": "finite x and y or paired null values",
                    }
                )
                row_violations.append(
                    {
                        "row": str(idx),
                        "column": col,
                        "value": str(series.loc[idx]),
                        "expected": "finite x/y pair",
                        "violation_type": "linear_fit_invalid_pair",
                    }
                )
            continue
        paired_values.append((idx, x_value, y_value))

    if len(paired_values) < 2:
        message = f"Column '{col}': linear_fit requires at least two finite x/y pairs"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            source_config_path=source_config_path,
            message=message,
            violations=violations,
        )
        return [message], row_violations

    residuals = []
    y_values = []
    for idx, x_value, y_value in paired_values:
        expected = slope * x_value + intercept
        residual = y_value - expected
        residuals.append(residual)
        y_values.append(y_value)
        if abs(residual) > tolerance:
            if len(violations) < max_row_detail:
                violations.append(
                    {
                        "row": str(idx),
                        "x": json_safe_value(x_value),
                        "y": json_safe_value(y_value),
                        "expected": json_safe_value(expected),
                        "residual": json_safe_value(residual),
                        "tolerance": tolerance,
                    }
                )
                row_violations.append(
                    {
                        "row": str(idx),
                        "column": col,
                        "value": str(y_value),
                        "expected": f"{slope} * {x_column} + {intercept} within tolerance {tolerance}",
                        "violation_type": "linear_fit_mismatch",
                    }
                )

    r2_value = None
    if r2_min is not None:
        y_mean = sum(y_values) / len(y_values)
        ss_tot = sum((value - y_mean) ** 2 for value in y_values)
        ss_res = sum(residual**2 for residual in residuals)
        if ss_tot == 0:
            r2_value = 1.0 if not violations and invalid_pair_count == 0 else 0.0
        else:
            r2_value = 1.0 - (ss_res / ss_tot)
        if r2_value < r2_min:
            violations.append({"r2": json_safe_value(r2_value), "expected": f">= {r2_min}"})

    if not violations and invalid_pair_count == 0:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"Column '{col}' matches declared linear fit",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': linear_fit found {len(violations)} violation(s)"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="linear_fit",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations


DEFAULT_OUTLIER_ALLOWED = [0, 1, True, False, "0", "1", "true", "false"]
OUTLIER_POSITIVE = {("number", 1), ("bool", True), ("string", "1"), ("string", "true")}


def canonical_flag_value(value):
    if is_nullish(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            return ("string", str(value).strip().lower())
    if isinstance(value, bool):
        return ("bool", bool(value))
    if isinstance(value, str):
        return ("string", value.strip().lower())
    number = finite_float(value)
    if number is not None:
        if number.is_integer():
            return ("number", int(number))
        return ("number", number)
    return ("string", str(value).strip().lower())


def check_outlier_flag_constraint(
    df,
    col,
    raw_check,
    stripped_to_actual,
    max_row_detail: int,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': outlier_flag must be a mapping"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    flag_column = str(raw_check.get("column", "")).strip()
    actual_flag_col = stripped_to_actual.get(flag_column)
    if actual_flag_col is None:
        message = f"Column '{col}': outlier_flag column '{flag_column}' not found"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    allowed_values = raw_check.get("allowed", DEFAULT_OUTLIER_ALLOWED)
    if not isinstance(allowed_values, list) or not allowed_values:
        message = f"Column '{col}': outlier_flag.allowed must be a non-empty list"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    allowed = {canonical_flag_value(value) for value in allowed_values}
    max_fraction = finite_float(raw_check.get("max_fraction", 1.0))
    if max_fraction is None or not 0 <= max_fraction <= 1:
        message = f"Column '{col}': outlier_flag.max_fraction must be between 0 and 1"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    flag_series = df[actual_flag_col]
    violations = []
    row_violations = []
    total_non_null = 0
    outlier_count = 0
    invalid_count = 0
    for idx, raw_value in flag_series.items():
        canonical = canonical_flag_value(raw_value)
        if canonical is None:
            invalid_count += 1
            if len(violations) < max_row_detail:
                violations.append({"row": str(idx), "column": flag_column, "value": None, "expected": "non-null flag"})
            continue
        total_non_null += 1
        if canonical not in allowed:
            invalid_count += 1
            if len(violations) < max_row_detail:
                violations.append(
                    {
                        "row": str(idx),
                        "column": flag_column,
                        "value": json_safe_value(raw_value),
                        "expected": "allowed flag value",
                    }
                )
            continue
        if canonical in OUTLIER_POSITIVE:
            outlier_count += 1

    denominator = total_non_null
    fraction = (outlier_count / denominator) if denominator else 0.0
    if fraction > max_fraction:
        violations.append(
            {
                "column": flag_column,
                "outlier_count": outlier_count,
                "denominator": denominator,
                "fraction": round(float(fraction), 6),
                "expected": f"<= {max_fraction}",
            }
        )

    for violation in violations[:max_row_detail]:
        if "row" not in violation:
            continue
        row_violations.append(
            {
                "row": violation["row"],
                "column": flag_column,
                "value": str(violation.get("value")),
                "expected": str(violation.get("expected")),
                "violation_type": "outlier_flag_invalid",
            }
        )

    if not violations and invalid_count == 0:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"Outlier flag column '{flag_column}' is valid",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': outlier_flag found {len(violations)} violation(s)"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="outlier_flag",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations
