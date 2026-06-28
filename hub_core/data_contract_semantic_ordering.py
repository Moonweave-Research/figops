"""Ordering validators for semantic data-contract checks."""

from __future__ import annotations

from .data_contract_semantic_registry import _MONOTONIC_MODES


def check_monotonic_constraint(series, col, mode: str, max_row_detail: int):
    if mode not in _MONOTONIC_MODES:
        allowed = ", ".join(sorted(_MONOTONIC_MODES))
        return f"Column '{col}': unsupported monotonic mode '{mode}'. Allowed: {allowed}", []

    observed = series.dropna()
    if len(observed) < 2:
        return None, []

    try:
        values = list(observed)
        indexes = list(observed.index)
        bad_rows = []
        for offset in range(1, len(values)):
            previous = values[offset - 1]
            current = values[offset]
            violates = (
                (mode == "increasing" and current <= previous)
                or (mode == "nondecreasing" and current < previous)
                or (mode == "decreasing" and current >= previous)
                or (mode == "nonincreasing" and current > previous)
            )
            if violates:
                bad_rows.append((indexes[offset], previous, current))
    except TypeError as exc:
        return f"Column '{col}': monotonic check failed because values are not comparable ({exc})", []

    if not bad_rows:
        return None, []

    row_violations = []
    for idx, previous, current in bad_rows[:max_row_detail]:
        row_violations.append(
            {
                "row": str(idx),
                "column": col,
                "value": str(current),
                "expected": f"monotonic {mode}; previous value {previous}",
                "violation_type": "monotonic_violation",
            }
        )

    return (
        f"Column '{col}': {len(bad_rows)} monotonic violation(s) "
        f"(expected {mode}; first violation at row {bad_rows[0][0]})",
        row_violations,
    )


def check_monotonic_within_group_constraint(
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
    resolve_group_columns,
    group_dict,
    append_calculation_check,
    append_failed_calculation_check,
    check_monotonic_constraint_func=check_monotonic_constraint,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': monotonic_within_group must be a mapping"
        return [message], []

    group_by, actual_group_by, missing = resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': monotonic_within_group group column(s) not found: {missing}"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="monotonic_within_group",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    mode = raw_check.get("mode")
    if not isinstance(mode, str) or mode not in _MONOTONIC_MODES:
        allowed = ", ".join(sorted(_MONOTONIC_MODES))
        message = f"Column '{col}': monotonic_within_group.mode must be one of: {allowed}"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="monotonic_within_group",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    violations = []
    row_violations = []
    grouped = df.groupby(actual_group_by, dropna=False, sort=False)
    for group_key, group_df in grouped:
        group_payload = group_dict(group_by, group_key)
        group_series = series.loc[group_df.index]
        group_error, group_rows = check_monotonic_constraint_func(group_series, col, mode, max_row_detail)
        if not group_error:
            continue
        violations.append({"group": group_payload, "message": group_error})
        for row in group_rows:
            row_with_group = dict(row)
            row_with_group["expected"] = f"{row['expected']} within group {group_payload}"
            row_with_group["violation_type"] = "monotonic_within_group"
            row_violations.append(row_with_group)

    if not violations:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="monotonic_within_group",
            target=col,
            group_by=group_by,
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"All groups are monotonic {mode}",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': {len(violations)} group(s) failed monotonic_within_group={mode}"
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="monotonic_within_group",
        target=col,
        group_by=group_by,
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [message], row_violations[:max_row_detail]
