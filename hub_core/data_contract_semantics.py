import json
import logging
import math
import re
from pathlib import Path

from .logging import get_logger

logger = get_logger(__name__)


def _log(message: str) -> None:
    if "❌" in message:
        level = logging.ERROR
    elif "⚠️" in message or "🟠" in message:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(level, message)

try:
    import pint as _pint

    _ureg = _pint.UnitRegistry()
    _PINT_AVAILABLE = True
except ImportError:
    _ureg = None
    _PINT_AVAILABLE = False

_MONOTONIC_MODES = {"increasing", "decreasing", "nondecreasing", "nonincreasing"}
SEMANTIC_CHECK_DEFINITIONS = {
    "allow_null": {
        "purpose": "Require or allow null values in the target column.",
        "schema": {"type": "boolean", "default": True},
        "example": {"y": {"allow_null": False}},
    },
    "range": {
        "purpose": "Require numeric values to fall within an inclusive [min, max] interval.",
        "schema": {
            "type": "array",
            "prefixItems": [{"type": "number"}, {"type": "number"}],
            "minItems": 2,
            "maxItems": 2,
        },
        "example": {"y": {"range": [0, 1]}},
    },
    "unique": {
        "purpose": "Require every value in the target column to be unique.",
        "schema": {"type": "boolean"},
        "example": {"sample_id": {"unique": True}},
    },
    "monotonic": {
        "purpose": "Require ordered values in the target column.",
        "schema": {"type": "string", "enum": sorted(_MONOTONIC_MODES)},
        "example": {"time": {"monotonic": "increasing"}},
    },
    "monotonic_within_group": {
        "purpose": "Require ordered values in the target column within each configured group.",
        "schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "mode": {"type": "string", "enum": sorted(_MONOTONIC_MODES)},
            },
            "required": ["group_by", "mode"],
        },
        "example": {"time": {"monotonic_within_group": {"group_by": ["sample"], "mode": "increasing"}}},
    },
    "min_replicates": {
        "purpose": "Require a minimum replicate count within groups.",
        "schema": {"type": "object"},
        "example": {"mean": {"min_replicates": {"group_by": ["condition"], "n": 3}}},
    },
    "expected_sample_count": {
        "purpose": "Require each configured group to have an exact or ranged expected count of non-null target values.",
        "schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "count": {"type": "integer", "minimum": 1},
                "range": {
                    "type": "array",
                    "prefixItems": [{"type": "integer", "minimum": 1}, {"type": "integer", "minimum": 1}],
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "required": ["group_by"],
            "oneOf": [{"required": ["count"]}, {"required": ["range"]}],
        },
        "example": {"value": {"expected_sample_count": {"group_by": ["condition"], "range": [3, 5]}}},
    },
    "grouped_cv": {
        "purpose": "Check coefficient of variation within configured groups.",
        "schema": {"type": "object"},
        "example": {"mean": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}},
    },
    "log_scale_positive": {
        "purpose": "Require positive values when the column will be plotted on a log scale.",
        "schema": {"type": "boolean"},
        "example": {"mean": {"log_scale_positive": True}},
    },
    "error_bar_source": {
        "purpose": "Declare and validate the source column used for error bars.",
        "schema": {"type": "object"},
        "example": {"mean": {"error_bar_source": {"column": "sem", "source": "sem"}}},
    },
    "mean_sem": {
        "purpose": "Validate mean and SEM relationships from grouped replicate data.",
        "schema": {"type": "object"},
        "example": {"mean": {"mean_sem": {"group_by": ["condition"], "sem_column": "sem"}}},
    },
    "linear_fit": {
        "purpose": "Validate a target column against an expected linear fit.",
        "schema": {"type": "object"},
        "example": {"y": {"linear_fit": {"x_column": "x", "slope": 2.0, "intercept": 1.0}}},
    },
    "outlier_flag": {
        "purpose": "Validate a boolean outlier flag column and maximum flagged fraction.",
        "schema": {"type": "object"},
        "example": {"y": {"outlier_flag": {"column": "outlier", "max_fraction": 0.25}}},
    },
    "axis_unit": {
        "purpose": "Validate that a configured axis unit conversion is compatible.",
        "schema": {"type": "object"},
        "example": {"current": {"axis_unit": {"data_unit": "mA", "display_unit": "A"}}},
    },
    "unit": {
        "purpose": "Validate actual_unit compatibility with an expected unit when Pint is installed.",
        "schema": {"type": "string"},
        "example": {"current": {"unit": "A", "actual_unit": "mA"}},
    },
    "unit_coherence": {
        "purpose": "Validate that declared related-column units combine to the target column's expected unit.",
        "schema": {
            "type": "object",
            "properties": {
                "expected_unit": {"type": "string"},
                "terms": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "unit": {"type": "string"},
                            "exponent": {"type": "integer", "default": 1},
                        },
                        "required": ["column", "unit"],
                    },
                    "minItems": 1,
                },
            },
            "required": ["expected_unit", "terms"],
        },
        "example": {
            "resistivity": {
                "unit_coherence": {
                    "expected_unit": "ohm*cm",
                    "terms": [
                        {"column": "resistance", "unit": "ohm"},
                        {"column": "area", "unit": "cm^2"},
                        {"column": "thickness", "unit": "cm", "exponent": -1},
                    ],
                }
            }
        },
    },
}





def _validate_semantic_constraints(
    df,
    semantic_checks,
    stripped_to_actual,
    *,
    calculation_checks=None,
    csv_rel_path: str = "",
    source_config_path: str = "project_config.yaml",
    unit_checker=None,
):
    """
    데이터프레임의 논리적 제약 조건(range, allow_null, unique, unit, monotonic)을 검증합니다.

    Returns:
        (errors, row_violations) -- errors는 요약 문자열 리스트,
        row_violations는 행 단위 dict 리스트 (error_dumper용).
    """
    errors = []
    row_violations = []
    max_row_detail = 50  # 리포트에 포함할 최대 행 수

    for col, constraints in semantic_checks.items():
        norm_col = str(col).strip()
        actual_col = stripped_to_actual.get(norm_col)

        if not actual_col:
            errors.append(f"Column '{col}': semantic check target column not found")
            continue

        series = df[actual_col]

        # 1. Null check
        allow_null = constraints.get("allow_null", True)
        if not allow_null and series.isnull().any():
            null_count = int(series.isnull().sum())
            errors.append(f"Column '{col}': found {null_count} null value(s) (allow_null=false)")
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

        # 2. Range check
        val_range = constraints.get("range")
        if val_range and len(val_range) == 2:
            try:
                from pandas.api.types import is_numeric_dtype
            except Exception:
                is_numeric_dtype = None
            min_val, max_val = val_range
            if not (isinstance(min_val, (int, float)) and isinstance(max_val, (int, float))):
                errors.append(f"Column '{col}': range bounds must be numeric, got {val_range}")
                continue
            if min_val > max_val:
                errors.append(f"Column '{col}': range min must be <= max (got [{min_val}, {max_val}])")
                continue
            if is_numeric_dtype is not None and not is_numeric_dtype(series):
                errors.append(
                    f"Column '{col}': range target column must be numeric (possible locale/decimal parsing issue)"
                )
                continue
            mask = (series < min_val) | (series > max_val)
            if mask.any():
                violation_count = int(mask.sum())
                observed_min = series.min()
                observed_max = series.max()
                errors.append(
                    f"Column '{col}': {violation_count} value(s) out of range "
                    f"[{min_val}, {max_val}]. "
                    f"(Observed: {observed_min} to {observed_max})"
                )
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

        # 3. Unique check
        is_unique_req = constraints.get("unique", False)
        if is_unique_req and not series.is_unique:
            dup_count = int(series.duplicated().sum())
            errors.append(f"Column '{col}': found {dup_count} duplicate value(s) (unique=true)")
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

        # 4. Monotonic check
        if "monotonic" in constraints:
            monotonic_mode = constraints.get("monotonic")
            monotonic_error, monotonic_rows = _check_monotonic_constraint(
                series,
                col,
                str(monotonic_mode),
                max_row_detail,
            )
            if monotonic_error:
                errors.append(monotonic_error)
                row_violations.extend(monotonic_rows)

        if "monotonic_within_group" in constraints:
            grouped_errors, grouped_rows = _check_monotonic_within_group_constraint(
                df,
                series,
                col,
                constraints["monotonic_within_group"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(grouped_errors)
            row_violations.extend(grouped_rows)

        # 5. Grouped calculation checks
        if "min_replicates" in constraints:
            grouped_errors, grouped_rows = _check_min_replicates_constraint(
                df,
                series,
                col,
                constraints["min_replicates"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(grouped_errors)
            row_violations.extend(grouped_rows)

        if "expected_sample_count" in constraints:
            grouped_errors, grouped_rows = _check_expected_sample_count_constraint(
                df,
                series,
                col,
                constraints["expected_sample_count"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(grouped_errors)
            row_violations.extend(grouped_rows)

        if "grouped_cv" in constraints:
            grouped_errors = _check_grouped_cv_constraint(
                df,
                series,
                col,
                constraints["grouped_cv"],
                stripped_to_actual,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(grouped_errors)

        if "log_scale_positive" in constraints:
            if constraints.get("log_scale_positive") is True:
                log_errors, log_rows = _check_log_scale_positive_constraint(
                    series,
                    col,
                    max_row_detail,
                    calculation_checks=calculation_checks,
                    csv_rel_path=csv_rel_path,
                    source_config_path=source_config_path,
                )
                errors.extend(log_errors)
                row_violations.extend(log_rows)
            elif constraints.get("log_scale_positive") is not False:
                message = f"Column '{col}': log_scale_positive must be a boolean"
                _append_calculation_check(
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
                errors.append(message)

        if "error_bar_source" in constraints:
            errorbar_errors, errorbar_rows = _check_error_bar_source_constraint(
                df,
                col,
                constraints["error_bar_source"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(errorbar_errors)
            row_violations.extend(errorbar_rows)

        if "mean_sem" in constraints:
            mean_sem_errors, mean_sem_rows = _check_mean_sem_constraint(
                df,
                col,
                constraints["mean_sem"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(mean_sem_errors)
            row_violations.extend(mean_sem_rows)

        if "linear_fit" in constraints:
            linear_fit_errors, linear_fit_rows = _check_linear_fit_constraint(
                df,
                series,
                col,
                constraints["linear_fit"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(linear_fit_errors)
            row_violations.extend(linear_fit_rows)

        if "outlier_flag" in constraints:
            outlier_errors, outlier_rows = _check_outlier_flag_constraint(
                df,
                col,
                constraints["outlier_flag"],
                stripped_to_actual,
                max_row_detail,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(outlier_errors)
            row_violations.extend(outlier_rows)

        if "axis_unit" in constraints:
            axis_errors, axis_rows = _check_axis_unit_constraint(
                col,
                constraints["axis_unit"],
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
                unit_checker=unit_checker,
            )
            errors.extend(axis_errors)
            row_violations.extend(axis_rows)

        if "unit_coherence" in constraints:
            unit_coherence_errors, unit_coherence_rows = _check_unit_coherence_constraint(
                col,
                constraints["unit_coherence"],
                stripped_to_actual,
                calculation_checks=calculation_checks,
                csv_rel_path=csv_rel_path,
                source_config_path=source_config_path,
            )
            errors.extend(unit_coherence_errors)
            row_violations.extend(unit_coherence_rows)

        # 6. Unit check (requires pint)
        expected_unit = constraints.get("unit")
        actual_unit = constraints.get("actual_unit")
        if expected_unit and actual_unit:
            checker = unit_checker or _check_unit_compatibility
            result = checker(col, actual_unit, expected_unit)
            if result == "incompatible":
                errors.append(f"Column '{col}': unit '{actual_unit}' is incompatible with expected '{expected_unit}'")
                row_violations.append(
                    {
                        "row": "*",
                        "column": col,
                        "value": actual_unit,
                        "expected": expected_unit,
                        "violation_type": "unit_incompatible",
                    }
                )
            elif isinstance(result, tuple):
                # Convertible but different units. The validator does not rewrite the
                # rendered data (the renderer re-reads the raw CSV), so auto-converting a
                # discarded local copy would silently render unconverted values. Fail fast.
                errors.append(
                    f"Column '{col}': data unit '{actual_unit}' differs from the expected "
                    f"'{expected_unit}'. The contract does not rewrite rendered data, so the "
                    f"figure would show unconverted values. Convert the source data to "
                    f"'{expected_unit}', or use an axis_unit (data_unit/display_unit) check for "
                    f"label-only display scaling."
                )
                row_violations.append(
                    {
                        "row": "*",
                        "column": col,
                        "value": actual_unit,
                        "expected": expected_unit,
                        "violation_type": "unit_requires_source_conversion",
                    }
                )

    return errors, row_violations


def _calculation_summary(checks: list[dict]) -> dict:
    return {
        "checks": checks,
        "quality_passed": not any(check.get("status") in {"warning", "failed"} for check in checks),
        "manual_review_needed": any(bool(check.get("manual_review_needed")) for check in checks),
    }


def _write_calculation_checks_sidecar(project_dir, checks: list[dict]) -> None:
    diag_dir = Path(project_dir).expanduser().resolve() / "results" / "diagnostics"
    sidecar = diag_dir / "calculation_checks.json"
    if not checks:
        if sidecar.exists():
            sidecar.unlink()
        return
    payload = {"schema_version": "1.0", **_calculation_summary(checks)}
    diag_dir.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def _append_calculation_check(
    calculation_checks,
    *,
    csv_rel_path: str,
    name: str,
    target: str,
    group_by: list[str],
    source_config_path: str,
    status: str,
    manual_review_needed: bool,
    message: str,
    violations: list[dict],
) -> None:
    if calculation_checks is None:
        return
    calculation_checks.append(
        {
            "csv_path": csv_rel_path,
            "name": name,
            "target": str(target),
            "group_by": group_by,
            "source_config_path": source_config_path,
            "status": status,
            "manual_review_needed": manual_review_needed,
            "message": message,
            "violations": violations,
        }
    )


def _resolve_group_columns(raw_group_by, stripped_to_actual):
    group_by = [str(item).strip() for item in raw_group_by or []]
    if not group_by:
        return [], [], ["<empty group_by>"]
    missing = [column for column in group_by if column not in stripped_to_actual]
    actual = [stripped_to_actual[column] for column in group_by if column in stripped_to_actual]
    return group_by, actual, missing


def _json_safe_value(value):
    if _is_nullish(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            return str(value)
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        try:
            if not math.isfinite(float(value)):
                return None
        except (TypeError, ValueError):
            return str(value)
    return value


def _is_nullish(value) -> bool:
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except Exception:
        pass
    return False


def _append_failed_calculation_check(
    calculation_checks,
    *,
    csv_rel_path: str,
    name: str,
    target: str,
    source_config_path: str,
    message: str,
    violations: list[dict] | None = None,
) -> None:
    _append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name=name,
        target=target,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=violations or [],
    )


def _group_dict(group_by: list[str], group_key) -> dict:
    if len(group_by) == 1:
        if isinstance(group_key, tuple) and len(group_key) == 1:
            values = group_key
        else:
            values = (group_key,)
    else:
        values = tuple(group_key)
    return {column: _json_safe_value(value) for column, value in zip(group_by, values, strict=False)}


def _check_monotonic_within_group_constraint(
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
        message = f"Column '{col}': monotonic_within_group must be a mapping"
        return [message], []

    group_by, actual_group_by, missing = _resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': monotonic_within_group group column(s) not found: {missing}"
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
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
        group_payload = _group_dict(group_by, group_key)
        group_series = series.loc[group_df.index]
        group_error, group_rows = _check_monotonic_constraint(group_series, col, mode, max_row_detail)
        if not group_error:
            continue
        violations.append({"group": group_payload, "message": group_error})
        for row in group_rows:
            row_with_group = dict(row)
            row_with_group["expected"] = f"{row['expected']} within group {group_payload}"
            row_with_group["violation_type"] = "monotonic_within_group"
            row_violations.append(row_with_group)

    if not violations:
        _append_calculation_check(
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
    _append_calculation_check(
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


def _check_min_replicates_constraint(
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

    group_by, actual_group_by, missing = _resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': min_replicates group column(s) not found: {missing}"
        _append_calculation_check(
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
        _append_calculation_check(
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
        group_payload = _group_dict(group_by, group_key)
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
        _append_calculation_check(
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
    _append_calculation_check(
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


def _check_expected_sample_count_constraint(
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

    group_by, actual_group_by, missing = _resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': expected_sample_count group column(s) not found: {missing}"
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
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
            _append_failed_calculation_check(
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
            _append_failed_calculation_check(
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
            _append_failed_calculation_check(
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
        group_payload = _group_dict(group_by, group_key)
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
        _append_calculation_check(
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
    _append_calculation_check(
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


def _check_grouped_cv_constraint(
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

    group_by, actual_group_by, missing = _resolve_group_columns(raw_check.get("group_by"), stripped_to_actual)
    if missing:
        message = f"Column '{col}': grouped_cv group column(s) not found: {missing}"
        _append_calculation_check(
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
        _append_calculation_check(
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
                    "group": _group_dict(group_by, group_key),
                    "cv": round(float(cv), 4),
                    "threshold": threshold,
                    "count": int(len(group_series)),
                }
            )

    if not violations:
        _append_calculation_check(
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
    _append_calculation_check(
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


def _numeric_series_or_error(df, stripped_to_actual, column_name: str, check_name: str):
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


def _check_log_scale_positive_constraint(
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
        _append_calculation_check(
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

    finite_mask = series.map(lambda value: math.isfinite(float(value)) if not _is_nullish(value) else True)
    mask = series.notna() & (~finite_mask | (series <= 0))
    if not mask.any():
        _append_calculation_check(
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
        {"row": str(idx), "value": _json_safe_value(series.loc[idx]), "expected": "> 0 and finite"} for idx in bad_rows
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
    _append_calculation_check(
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


def _check_error_bar_source_constraint(
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
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="error_bar_source",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    error_column = raw_check.get("column")
    error_series, error = _numeric_series_or_error(df, stripped_to_actual, str(error_column), "error_bar_source")
    if error:
        message = f"Column '{col}': {error}"
        _append_failed_calculation_check(
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
        _append_calculation_check(
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
            "value": _json_safe_value(error_series.loc[idx]),
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
    _append_calculation_check(
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


def _check_mean_sem_constraint(
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
        _append_failed_calculation_check(
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
    sem, sem_error = _numeric_series_or_error(df, stripped_to_actual, str(sem_column), "mean_sem")
    std, std_error = _numeric_series_or_error(df, stripped_to_actual, str(std_column), "mean_sem")
    n_values, n_error = _numeric_series_or_error(df, stripped_to_actual, str(n_column), "mean_sem")
    errors = [error for error in (sem_error, std_error, n_error) if error]
    if errors:
        message = f"Column '{col}': {errors[0]}"
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="mean_sem",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    finite_mask = sem.map(lambda value: math.isfinite(float(value)) if not _is_nullish(value) else False)
    finite_mask = finite_mask & std.map(lambda value: math.isfinite(float(value)) if not _is_nullish(value) else False)
    finite_mask = finite_mask & n_values.map(
        lambda value: math.isfinite(float(value)) if not _is_nullish(value) else False
    )
    valid_mask = finite_mask & (sem >= 0) & (std >= 0) & (n_values > 0)
    expected = sem.copy()
    expected[:] = None
    expected.loc[valid_mask] = std.loc[valid_mask] / n_values.loc[valid_mask].map(math.sqrt)
    mask = ~valid_mask
    mask = mask | (valid_mask & ((sem - expected).abs() > tolerance))
    if not mask.any():
        _append_calculation_check(
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
            "sem": _json_safe_value(sem.loc[idx]),
            "expected": _json_safe_value(expected.loc[idx]) if idx in expected.index else None,
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
    _append_calculation_check(
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


def _finite_float(value):
    if isinstance(value, bool) or _is_nullish(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _check_linear_fit_constraint(
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
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="linear_fit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    x_column = str(raw_check.get("x_column", "")).strip()
    x_series, x_error = _numeric_series_or_error(df, stripped_to_actual, x_column, "linear_fit")
    y_series, y_error = _numeric_series_or_error(df, stripped_to_actual, str(col), "linear_fit")
    for error in (x_error, y_error):
        if error:
            message = f"Column '{col}': {error}"
            _append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="linear_fit",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []

    slope = _finite_float(raw_check.get("slope"))
    intercept = _finite_float(raw_check.get("intercept"))
    tolerance = _finite_float(raw_check.get("tolerance", 1.0e-6))
    r2_min = _finite_float(raw_check.get("r2_min")) if "r2_min" in raw_check else None
    if slope is None or intercept is None:
        message = f"Column '{col}': linear_fit slope and intercept must be finite numbers"
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
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
        x_value = _finite_float(x_series.loc[idx])
        y_value = _finite_float(series.loc[idx])
        if x_value is None and y_value is None:
            continue
        if x_value is None or y_value is None:
            invalid_pair_count += 1
            if len(violations) < max_row_detail:
                violations.append(
                    {
                        "row": str(idx),
                        "x": _json_safe_value(x_series.loc[idx]),
                        "y": _json_safe_value(series.loc[idx]),
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
        _append_failed_calculation_check(
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
                        "x": _json_safe_value(x_value),
                        "y": _json_safe_value(y_value),
                        "expected": _json_safe_value(expected),
                        "residual": _json_safe_value(residual),
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
            violations.append({"r2": _json_safe_value(r2_value), "expected": f">= {r2_min}"})

    if not violations and invalid_pair_count == 0:
        _append_calculation_check(
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
    _append_calculation_check(
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


_DEFAULT_OUTLIER_ALLOWED = [0, 1, True, False, "0", "1", "true", "false"]
_OUTLIER_POSITIVE = {("number", 1), ("bool", True), ("string", "1"), ("string", "true")}


def _canonical_flag_value(value):
    if _is_nullish(value):
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
    number = _finite_float(value)
    if number is not None:
        if number.is_integer():
            return ("number", int(number))
        return ("number", number)
    return ("string", str(value).strip().lower())


def _check_outlier_flag_constraint(
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
        _append_failed_calculation_check(
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
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    allowed_values = raw_check.get("allowed", _DEFAULT_OUTLIER_ALLOWED)
    if not isinstance(allowed_values, list) or not allowed_values:
        message = f"Column '{col}': outlier_flag.allowed must be a non-empty list"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="outlier_flag",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    allowed = {_canonical_flag_value(value) for value in allowed_values}
    max_fraction = _finite_float(raw_check.get("max_fraction", 1.0))
    if max_fraction is None or not 0 <= max_fraction <= 1:
        message = f"Column '{col}': outlier_flag.max_fraction must be between 0 and 1"
        _append_failed_calculation_check(
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
        canonical = _canonical_flag_value(raw_value)
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
                        "value": _json_safe_value(raw_value),
                        "expected": "allowed flag value",
                    }
                )
            continue
        if canonical in _OUTLIER_POSITIVE:
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
        _append_calculation_check(
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
    _append_calculation_check(
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


_UNIT_TOKEN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\^(-?\d+))?$")


def _parse_unit_signature(unit: str) -> dict[str, int]:
    raw = str(unit).replace(" ", "")
    if not raw:
        raise ValueError("unit must be non-empty")

    signature: dict[str, int] = {}
    pending = ""
    operator = 1
    for char in raw + "*":
        if char in "*/":
            if not pending:
                raise ValueError(f"malformed unit expression '{unit}'")
            if pending != "1":
                match = _UNIT_TOKEN_RE.match(pending)
                if not match:
                    raise ValueError(f"unsupported unit token '{pending}'")
                base, exponent_text = match.groups()
                exponent = int(exponent_text or "1") * operator
                signature[base] = signature.get(base, 0) + exponent
                if signature[base] == 0:
                    del signature[base]
            pending = ""
            operator = 1 if char == "*" else -1
        else:
            pending += char
    return signature


def _format_unit_signature(signature: dict[str, int]) -> str:
    if not signature:
        return "1"
    return "*".join(
        f"{unit}^{exponent}" if exponent != 1 else unit
        for unit, exponent in sorted(signature.items())
    )


def _check_unit_coherence_constraint(
    col,
    raw_check,
    stripped_to_actual,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': unit_coherence must be a mapping"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    expected_unit = raw_check.get("expected_unit")
    terms = raw_check.get("terms")
    if not isinstance(expected_unit, str) or not expected_unit.strip():
        message = f"Column '{col}': unit_coherence.expected_unit must be a non-empty string"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    if not isinstance(terms, list) or not terms:
        message = f"Column '{col}': unit_coherence.terms must be a non-empty list"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    combined: dict[str, int] = {}
    term_payloads = []
    for idx, term in enumerate(terms, 1):
        if not isinstance(term, dict):
            message = f"Column '{col}': unit_coherence.terms[{idx}] must be a mapping"
            _append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        term_column = term.get("column")
        term_unit = term.get("unit")
        exponent = term.get("exponent", 1)
        if not isinstance(term_column, str) or not term_column.strip() or term_column.strip() not in stripped_to_actual:
            message = f"Column '{col}': unit_coherence term column not found: {term_column!r}"
            _append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        if not isinstance(term_unit, str) or not term_unit.strip():
            message = f"Column '{col}': unit_coherence term unit must be a non-empty string"
            _append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent == 0:
            message = f"Column '{col}': unit_coherence term exponent must be a non-zero integer"
            _append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        try:
            term_signature = _parse_unit_signature(term_unit)
        except ValueError as exc:
            message = f"Column '{col}': unit_coherence term unit parse failed: {exc}"
            _append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        for unit, power in term_signature.items():
            combined[unit] = combined.get(unit, 0) + power * exponent
            if combined[unit] == 0:
                del combined[unit]
        term_payloads.append({"column": term_column.strip(), "unit": term_unit.strip(), "exponent": exponent})

    try:
        expected_signature = _parse_unit_signature(expected_unit)
    except ValueError as exc:
        message = f"Column '{col}': unit_coherence expected_unit parse failed: {exc}"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    observed = _format_unit_signature(combined)
    expected = _format_unit_signature(expected_signature)
    if combined == expected_signature:
        _append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"Related units combine to expected unit '{expected}'",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': unit_coherence expected '{expected}', got '{observed}'"
    violation = {
        "column": col,
        "value": observed,
        "expected": expected,
        "terms": term_payloads,
        "violation_type": "unit_coherence",
    }
    _append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="unit_coherence",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=[violation],
    )
    return [message], [
        {
            "row": "*",
            "column": col,
            "value": observed,
            "expected": expected,
            "violation_type": "unit_coherence",
        }
    ]


def _check_axis_unit_constraint(
    col,
    raw_check,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
    unit_checker=None,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': axis_unit must be a mapping"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    data_unit = raw_check.get("data_unit")
    display_unit = raw_check.get("display_unit")
    if (
        not isinstance(data_unit, str)
        or not data_unit.strip()
        or not isinstance(display_unit, str)
        or not display_unit.strip()
    ):
        message = f"Column '{col}': axis_unit data_unit and display_unit must be non-empty strings"
        _append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    checker = unit_checker or _check_unit_compatibility
    result = checker(col, data_unit.strip(), display_unit.strip())
    if result == "incompatible":
        message = f"Column '{col}': axis_unit '{data_unit}' is incompatible with display unit '{display_unit}'"
        _append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[
                {
                    "column": col,
                    "value": data_unit,
                    "expected": display_unit,
                    "violation_type": "axis_unit_incompatible",
                }
            ],
        )
        return [message], [
            {
                "row": "*",
                "column": col,
                "value": data_unit,
                "expected": display_unit,
                "violation_type": "axis_unit_incompatible",
            }
        ]

    if result == "skip":
        message = f"Column '{col}': axis_unit check skipped; manual review required"
        _append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="skipped",
            manual_review_needed=True,
            message=message,
            violations=[],
        )
        return [], []

    if isinstance(result, tuple):
        factor, from_unit, to_unit = result
        message = f"Axis unit '{from_unit}' is compatible with '{to_unit}' (x{factor})"
        violations = [{"conversion_factor": _json_safe_value(factor), "from_unit": from_unit, "to_unit": to_unit}]
    else:
        message = f"Axis unit '{data_unit}' matches display unit '{display_unit}'"
        violations = []
    _append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="axis_unit",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="passed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [], []


def _check_monotonic_constraint(series, col, mode: str, max_row_detail: int):
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


def _check_statistical_quality(df, csv_rel_path, cv_threshold, project_dir, *, log_func=None):
    log = log_func or _log
    """
    수치 컬럼의 변동계수(CV = std/mean)를 계산하여
    cv_threshold 초과 시 주황색 경고를 출력하고 진단 리포트에 기록합니다.
    평균이 0에 가까운 컬럼(|mean| < 1e-9)은 건너뜁니다.

    Returns:
        dict with keys: cv_warnings, cv_threshold, quality_passed, report_path
    """

    numeric_cols = df.select_dtypes(include="number").columns
    warnings = []

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 2:
            continue
        mean_val = series.mean()
        if abs(mean_val) < 1e-9:
            continue
        cv = series.std() / abs(mean_val)
        if cv > cv_threshold:
            warnings.append({"column": col, "cv": round(float(cv), 4)})

    quality_result = {
        "csv_path": csv_rel_path,
        "cv_warnings": warnings,
        "cv_threshold": cv_threshold,
        "quality_passed": len(warnings) == 0,
        "report_path": None,
    }

    if not warnings:
        return quality_result

    log(f"      🟠 [Quality Score] High noise detected in '{csv_rel_path}':")
    for w in warnings:
        log(f"         - '{w['column']}': CV = {w['cv']:.1%} (threshold: {cv_threshold:.0%})")

    # 진단 리포트에 품질 경고 추가 + JSON sidecar 기록
    try:
        import json
        from datetime import datetime, timezone
        from pathlib import Path

        project_path = Path(project_dir).expanduser().resolve()
        diag_dir = project_path / "results" / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ts_iso = datetime.now(timezone.utc).isoformat()

        # Markdown report (timestamped, accumulates)
        rpt = diag_dir / f"quality_score_{ts}.md"
        lines = [
            f"## Statistical Quality Warning -- {csv_rel_path}",
            f"_Generated: {ts_iso}_\n",
            f"CV threshold: {cv_threshold:.0%}\n",
            "| Column | CV | Status |",
            "| ------ | -- | ------ |",
        ]
        for w in warnings:
            lines.append(f"| {w['column']} | {w['cv']:.1%} | ⚠️ High noise |")
        rpt.write_text("\n".join(lines), encoding="utf-8")
        log(f"      📄 Quality report: {rpt}")
        quality_result["report_path"] = str(rpt)

        # JSON sidecar (latest-wins, machine-readable for Athena bridge)
        sidecar = diag_dir / "quality_metrics.json"
        sidecar_payload = {
            "timestamp": ts_iso,
            "csv_path": csv_rel_path,
            "cv_warnings": warnings,
            "cv_threshold": cv_threshold,
            "quality_passed": False,
        }
        sidecar.write_text(json.dumps(sidecar_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return quality_result


def _check_unit_compatibility(
    col_name,
    actual_unit_str,
    expected_unit_str,
    *,
    pint_available=None,
    ureg=None,
    log_func=None,
):
    """
    Pint를 사용하여 단위 호환성을 검증합니다.

    Returns:
        "ok"            -- 동일 단위
        (factor, a, b)  -- 호환 가능, 변환 계수 반환
        "incompatible"  -- 차원 불일치
        "skip"          -- Pint 미설치
    """
    available = _PINT_AVAILABLE if pint_available is None else pint_available
    registry = _ureg if ureg is None else ureg
    log = log_func or _log
    if not available:
        log(f"      ⚠️  Column '{col_name}': unit check skipped (pint not installed)")
        return "skip"

    try:
        expected = registry.parse_expression(expected_unit_str)
        actual = registry.parse_expression(actual_unit_str)
    except Exception:
        log(f"      ⚠️  Column '{col_name}': could not parse units ('{actual_unit_str}' or '{expected_unit_str}')")
        return "skip"

    if actual.units == expected.units:
        return "ok"

    try:
        factor = actual.to(expected.units).magnitude
        return (factor, actual_unit_str, expected_unit_str)
    except _pint.DimensionalityError:
        return "incompatible"
