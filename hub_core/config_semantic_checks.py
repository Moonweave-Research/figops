from __future__ import annotations

import math

ALLOWED_MONOTONIC_MODES = {"increasing", "decreasing", "nondecreasing", "nonincreasing"}


def validate_grouped_check_config(errors, *, column: str, check_name: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic {check_name} for '{column}' must be a mapping.")
        return

    group_by = raw_check.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append(f"Semantic {check_name}.group_by for '{column}' must be a non-empty list of column names.")
    elif any(not isinstance(item, str) or not item.strip() for item in group_by):
        errors.append(f"Semantic {check_name}.group_by for '{column}' must contain only non-empty strings.")

    if check_name == "min_replicates":
        min_count = raw_check.get("min_count")
        if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count <= 0:
            errors.append(f"Semantic min_replicates.min_count for '{column}' must be a positive integer.")
        return

    threshold = raw_check.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold <= 0:
        errors.append(f"Semantic grouped_cv.threshold for '{column}' must be a positive number.")

    min_count = raw_check.get("min_count", 2)
    if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count <= 0:
        errors.append(f"Semantic grouped_cv.min_count for '{column}' must be a positive integer when provided.")

    warn_only = raw_check.get("warn_only", True)
    if not isinstance(warn_only, bool):
        errors.append(f"Semantic grouped_cv.warn_only for '{column}' must be a boolean.")


def validate_errorbar_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic error_bar_source for '{column}' must be a mapping.")
        return
    error_column = raw_check.get("column")
    if not isinstance(error_column, str) or not error_column.strip():
        errors.append(f"Semantic error_bar_source.column for '{column}' must be a non-empty string.")
    source = raw_check.get("source", "custom")
    if not isinstance(source, str) or not source.strip():
        errors.append(f"Semantic error_bar_source.source for '{column}' must be a non-empty string.")


def validate_mean_sem_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic mean_sem for '{column}' must be a mapping.")
        return
    for key in ("sem_column", "std_column", "n_column"):
        value = raw_check.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Semantic mean_sem.{key} for '{column}' must be a non-empty string.")
    tolerance = raw_check.get("tolerance", 1.0e-6)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0:
        errors.append(f"Semantic mean_sem.tolerance for '{column}' must be a non-negative number.")


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def validate_linear_fit_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic linear_fit for '{column}' must be a mapping.")
        return
    x_column = raw_check.get("x_column")
    if not isinstance(x_column, str) or not x_column.strip():
        errors.append(f"Semantic linear_fit.x_column for '{column}' must be a non-empty string.")
    for key in ("slope", "intercept"):
        if not is_finite_number(raw_check.get(key)):
            errors.append(f"Semantic linear_fit.{key} for '{column}' must be a finite number.")
    if "r2_min" in raw_check:
        r2_min = raw_check.get("r2_min")
        if not is_finite_number(r2_min) or not 0 <= float(r2_min) <= 1:
            errors.append(f"Semantic linear_fit.r2_min for '{column}' must be a finite number between 0 and 1.")
    tolerance = raw_check.get("tolerance", 1.0e-6)
    if not is_finite_number(tolerance) or float(tolerance) < 0:
        errors.append(f"Semantic linear_fit.tolerance for '{column}' must be a non-negative finite number.")


def is_scalar_flag_value(value: object) -> bool:
    return isinstance(value, (str, bool, int, float)) and not (isinstance(value, float) and math.isnan(value))


def validate_outlier_flag_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic outlier_flag for '{column}' must be a mapping.")
        return
    flag_column = raw_check.get("column")
    if not isinstance(flag_column, str) or not flag_column.strip():
        errors.append(f"Semantic outlier_flag.column for '{column}' must be a non-empty string.")
    if "allowed" in raw_check:
        allowed = raw_check.get("allowed")
        if not isinstance(allowed, list) or not allowed:
            errors.append(f"Semantic outlier_flag.allowed for '{column}' must be a non-empty list.")
        elif any(not is_scalar_flag_value(item) for item in allowed):
            errors.append(
                f"Semantic outlier_flag.allowed for '{column}' must contain only scalar strings, numbers, or booleans."
            )
    if "max_fraction" in raw_check:
        max_fraction = raw_check.get("max_fraction")
        if not is_finite_number(max_fraction) or not 0 <= float(max_fraction) <= 1:
            errors.append(f"Semantic outlier_flag.max_fraction for '{column}' must be a finite number between 0 and 1.")


def validate_axis_unit_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic axis_unit for '{column}' must be a mapping.")
        return
    for key in ("data_unit", "display_unit"):
        value = raw_check.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Semantic axis_unit.{key} for '{column}' must be a non-empty string.")


def validate_monotonic_within_group_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic monotonic_within_group for '{column}' must be a mapping.")
        return
    group_by = raw_check.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append(f"Semantic monotonic_within_group.group_by for '{column}' must be a non-empty list.")
    elif any(not isinstance(item, str) or not item.strip() for item in group_by):
        errors.append(f"Semantic monotonic_within_group.group_by for '{column}' must contain only non-empty strings.")
    mode = raw_check.get("mode")
    if not isinstance(mode, str) or mode not in ALLOWED_MONOTONIC_MODES:
        allowed = ", ".join(sorted(ALLOWED_MONOTONIC_MODES))
        errors.append(f"Semantic monotonic_within_group.mode for '{column}' must be one of: {allowed}.")


def validate_expected_sample_count_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic expected_sample_count for '{column}' must be a mapping.")
        return
    group_by = raw_check.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append(f"Semantic expected_sample_count.group_by for '{column}' must be a non-empty list.")
    elif any(not isinstance(item, str) or not item.strip() for item in group_by):
        errors.append(f"Semantic expected_sample_count.group_by for '{column}' must contain only non-empty strings.")
    has_count = "count" in raw_check
    has_range = "range" in raw_check
    if has_count == has_range:
        errors.append(f"Semantic expected_sample_count for '{column}' must specify exactly one of count or range.")
    if has_count:
        count = raw_check.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            errors.append(f"Semantic expected_sample_count.count for '{column}' must be a positive integer.")
    if has_range:
        count_range = raw_check.get("range")
        if (
            not isinstance(count_range, list)
            or len(count_range) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in count_range)
        ):
            errors.append(
                f"Semantic expected_sample_count.range for '{column}' must be [min_count, max_count] positive integers."
            )
        elif count_range[0] > count_range[1]:
            errors.append(f"Semantic expected_sample_count.range for '{column}' must have min_count <= max_count.")


def validate_unit_coherence_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic unit_coherence for '{column}' must be a mapping.")
        return
    expected_unit = raw_check.get("expected_unit")
    if not isinstance(expected_unit, str) or not expected_unit.strip():
        errors.append(f"Semantic unit_coherence.expected_unit for '{column}' must be a non-empty string.")
    terms = raw_check.get("terms")
    if not isinstance(terms, list) or not terms:
        errors.append(f"Semantic unit_coherence.terms for '{column}' must be a non-empty list.")
        return
    for idx, term in enumerate(terms, 1):
        if not isinstance(term, dict):
            errors.append(f"Semantic unit_coherence.terms[{idx}] for '{column}' must be a mapping.")
            continue
        for key in ("column", "unit"):
            value = term.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Semantic unit_coherence.terms[{idx}].{key} for '{column}' must be a non-empty string.")
        exponent = term.get("exponent", 1)
        if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent == 0:
            errors.append(f"Semantic unit_coherence.terms[{idx}].exponent for '{column}' must be a non-zero integer.")


def validate_csv_semantic_checks(errors: list[str], semantic_checks: object, *, check_index: int) -> None:
    if semantic_checks is not None and not isinstance(semantic_checks, dict):
        errors.append(f"data_contract.csv_checks[{check_index}].semantic_checks must be a mapping.")
        return
    if not semantic_checks:
        return

    for col, constraints in semantic_checks.items():
        if not isinstance(constraints, dict):
            errors.append(f"Semantic constraints for '{col}' must be a mapping.")
            continue
        if "range" in constraints:
            range_check = constraints["range"]
            if not isinstance(range_check, list) or len(range_check) != 2:
                errors.append(f"Semantic range for '{col}' must be a list of 2 numbers.")
            elif any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in range_check):
                errors.append(f"Semantic range for '{col}' must contain only numeric bounds.")
            elif range_check[0] > range_check[1]:
                errors.append(f"Semantic range for '{col}' min must be <= max.")
        if "allow_null" in constraints and not isinstance(constraints["allow_null"], bool):
            errors.append(f"Semantic allow_null for '{col}' must be a boolean.")
        if "unique" in constraints and not isinstance(constraints["unique"], bool):
            errors.append(f"Semantic unique for '{col}' must be a boolean.")
        if "monotonic" in constraints:
            monotonic_mode = constraints["monotonic"]
            if not isinstance(monotonic_mode, str) or monotonic_mode not in ALLOWED_MONOTONIC_MODES:
                allowed = ", ".join(sorted(ALLOWED_MONOTONIC_MODES))
                errors.append(f"Semantic monotonic for '{col}' must be one of: {allowed}. Got '{monotonic_mode}'.")
        if "monotonic_within_group" in constraints:
            validate_monotonic_within_group_config(
                errors,
                column=str(col),
                raw_check=constraints["monotonic_within_group"],
            )
        if "min_replicates" in constraints:
            validate_grouped_check_config(
                errors,
                column=str(col),
                check_name="min_replicates",
                raw_check=constraints["min_replicates"],
            )
        if "expected_sample_count" in constraints:
            validate_expected_sample_count_config(
                errors,
                column=str(col),
                raw_check=constraints["expected_sample_count"],
            )
        if "grouped_cv" in constraints:
            validate_grouped_check_config(
                errors,
                column=str(col),
                check_name="grouped_cv",
                raw_check=constraints["grouped_cv"],
            )
        if "log_scale_positive" in constraints and not isinstance(constraints["log_scale_positive"], bool):
            errors.append(f"Semantic log_scale_positive for '{col}' must be a boolean.")
        if "error_bar_source" in constraints:
            validate_errorbar_check_config(
                errors,
                column=str(col),
                raw_check=constraints["error_bar_source"],
            )
        if "mean_sem" in constraints:
            validate_mean_sem_check_config(
                errors,
                column=str(col),
                raw_check=constraints["mean_sem"],
            )
        if "linear_fit" in constraints:
            validate_linear_fit_check_config(
                errors,
                column=str(col),
                raw_check=constraints["linear_fit"],
            )
        if "outlier_flag" in constraints:
            validate_outlier_flag_check_config(
                errors,
                column=str(col),
                raw_check=constraints["outlier_flag"],
            )
        if "axis_unit" in constraints:
            validate_axis_unit_check_config(
                errors,
                column=str(col),
                raw_check=constraints["axis_unit"],
            )
        if "unit_coherence" in constraints:
            validate_unit_coherence_config(
                errors,
                column=str(col),
                raw_check=constraints["unit_coherence"],
            )
