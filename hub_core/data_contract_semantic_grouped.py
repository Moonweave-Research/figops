from __future__ import annotations

from .data_contract_calculation_checks import (
    append_calculation_check,
    append_failed_calculation_check,
    group_dict,
    resolve_group_columns,
)


def check_min_replicates_constraint(
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
    try:
        from pandas.api.types import is_numeric_dtype
    except Exception:
        is_numeric_dtype = None

    if not isinstance(raw_check, dict):
        message = f"Column '{col}': min_replicates must be a mapping"
        return [message], []

    group_by, actual_group_by, missing = resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': min_replicates group column(s) not found: {missing}"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="min_replicates",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[],
        )
        return [message], []

    if is_numeric_dtype is not None and not is_numeric_dtype(series):
        message = f"Column '{col}': min_replicates target column must be numeric"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="min_replicates",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[],
        )
        return [message], []

    try:
        min_count = int(raw_check.get("min_count"))
    except (TypeError, ValueError):
        message = f"Column '{col}': min_replicates.min_count must be a positive integer"
        return [message], []
    if min_count <= 0:
        message = f"Column '{col}': min_replicates.min_count must be a positive integer"
        return [message], []
    grouped = df.groupby(actual_group_by, dropna=False, sort=False)
    violations = []
    row_violations = []
    for group_key, group_df in grouped:
        count = int(series.loc[group_df.index].notna().sum())
        if count >= min_count:
            continue
        group_payload = group_dict(group_by, group_key)
        violations.append({"group": group_payload, "count": count, "expected": f">= {min_count}"})
        for idx in group_df.index[:max_row_detail]:
            row_violations.append(
                {
                    "row": str(idx),
                    "column": col,
                    "value": str(series.loc[idx]),
                    "expected": f"min_replicates >= {min_count} for group {group_payload}",
                    "violation_type": "min_replicates",
                }
            )

    if not violations:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="min_replicates",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"All groups meet min_count={min_count}",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': {len(violations)} group(s) below min_count={min_count}"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="min_replicates",
        target=col,
        group_by=group_by,
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations


def check_expected_sample_count_constraint(
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
        message = f"Column '{col}': expected_sample_count must be a mapping"
        return [message], []

    group_by, actual_group_by, missing = resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': expected_sample_count group column(s) not found: {missing}"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="expected_sample_count",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    has_count = "count" in raw_check
    has_range = "range" in raw_check
    if has_count == has_range:
        message = f"Column '{col}': expected_sample_count must specify exactly one of count or range"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="expected_sample_count",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    if has_count:
        count = raw_check.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            message = f"Column '{col}': expected_sample_count.count must be a positive integer"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="expected_sample_count",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        min_count = count
        max_count = count
        expected_label = str(count)
        expected_message = f"exactly count={count}"
    else:
        count_range = raw_check.get("range")
        if (
            not isinstance(count_range, list)
            or len(count_range) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in count_range)
        ):
            message = f"Column '{col}': expected_sample_count.range must be [min_count, max_count] positive integers"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="expected_sample_count",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        min_count, max_count = count_range
        if min_count > max_count:
            message = f"Column '{col}': expected_sample_count.range must have min_count <= max_count"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="expected_sample_count",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        expected_label = f"{min_count}..{max_count}"
        expected_message = f"count between {min_count} and {max_count}"

    violations = []
    row_violations = []
    grouped = df.groupby(actual_group_by, dropna=False, sort=False)
    for group_key, group_df in grouped:
        observed_count = int(series.loc[group_df.index].notna().sum())
        if min_count <= observed_count <= max_count:
            continue
        group_payload = group_dict(group_by, group_key)
        violations.append({"group": group_payload, "count": observed_count, "expected": expected_label})
        for idx in group_df.index[:max_row_detail]:
            row_violations.append(
                {
                    "row": str(idx),
                    "column": col,
                    "value": str(series.loc[idx]),
                    "expected": f"expected_sample_count={expected_label} for group {group_payload}",
                    "violation_type": "expected_sample_count",
                }
            )

    if not violations:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="expected_sample_count",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"All groups have {expected_message}",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': {len(violations)} group(s) failed expected_sample_count={expected_label}"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="expected_sample_count",
        target=col,
        group_by=group_by,
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations[:max_row_detail]


def check_grouped_cv_constraint(
    df,
    series,
    col,
    raw_check,
    stripped_to_actual,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    try:
        from pandas.api.types import is_numeric_dtype
    except Exception:
        is_numeric_dtype = None

    if not isinstance(raw_check, dict):
        message = f"Column '{col}': grouped_cv must be a mapping"
        return [message]

    group_by, actual_group_by, missing = resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': grouped_cv group column(s) not found: {missing}"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="grouped_cv",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[],
        )
        return [message]

    if is_numeric_dtype is not None and not is_numeric_dtype(series):
        message = f"Column '{col}': grouped_cv target column must be numeric"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="grouped_cv",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[],
        )
        return [message]

    try:
        threshold = float(raw_check.get("threshold"))
    except (TypeError, ValueError):
        message = f"Column '{col}': grouped_cv.threshold must be a positive number"
        return [message]
    if threshold <= 0:
        message = f"Column '{col}': grouped_cv.threshold must be a positive number"
        return [message]
    try:
        min_count = int(raw_check.get("min_count", 2))
    except (TypeError, ValueError):
        message = f"Column '{col}': grouped_cv.min_count must be a positive integer"
        return [message]
    if min_count <= 0:
        message = f"Column '{col}': grouped_cv.min_count must be a positive integer"
        return [message]
    warn_only = bool(raw_check.get("warn_only", True))
    valid_df = df.loc[series.notna()]
    grouped = valid_df.groupby(actual_group_by, dropna=False, sort=False)
    violations = []
    for group_key, group_df in grouped:
        group_series = series.loc[group_df.index].dropna()
        if len(group_series) < min_count:
            continue
        mean_val = group_series.mean()
        if abs(mean_val) < 1e-9:
            continue
        cv = group_series.std() / abs(mean_val)
        if cv > threshold:
            violations.append(
                {
                    "group": group_dict(group_by, group_key),
                    "cv": round(float(cv), 4),
                    "threshold": threshold,
                    "count": int(len(group_series)),
                }
            )

    if not violations:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="grouped_cv",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"All groups are within CV threshold {threshold}",
            violations=[],
        )
        return []

    status = "warning" if warn_only else "failed"
    message = f"Column '{col}': {len(violations)} group(s) exceeded grouped_cv threshold {threshold}"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="grouped_cv",
        target=col,
        group_by=group_by,
        source_config_path=source_config_path,
        status=status,
        manual_review_needed=warn_only,
        message=message,
        violations=violations,
    )
    return [] if warn_only else [message]
