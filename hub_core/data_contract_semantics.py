import logging

from .data_contract_calculation_checks import (
    append_calculation_check as _append_calculation_check,
)
from .data_contract_calculation_checks import (
    append_failed_calculation_check as _append_failed_calculation_check,
)
from .data_contract_calculation_checks import calculation_summary as _calculation_summary  # noqa: F401
from .data_contract_calculation_checks import group_dict as _group_dict
from .data_contract_calculation_checks import is_nullish as _is_nullish  # noqa: F401
from .data_contract_calculation_checks import json_safe_value as _json_safe_value
from .data_contract_calculation_checks import resolve_group_columns as _resolve_group_columns
from .data_contract_calculation_checks import (
    write_calculation_checks_sidecar as _write_calculation_checks_sidecar,  # noqa: F401
)
from .data_contract_semantic_grouped import (
    check_expected_sample_count_constraint as _check_expected_sample_count_constraint,
)
from .data_contract_semantic_grouped import (
    check_grouped_cv_constraint as _check_grouped_cv_constraint,
)
from .data_contract_semantic_grouped import (
    check_min_replicates_constraint as _check_min_replicates_constraint,
)
from .data_contract_semantic_ordering import (
    check_monotonic_constraint as _check_monotonic_constraint,
)
from .data_contract_semantic_ordering import (
    check_monotonic_within_group_constraint as _semantic_monotonic_within_group_constraint,
)
from .data_contract_semantic_quality import (
    check_statistical_quality as _quality_check_statistical_quality,
)
from .data_contract_semantic_registry import _MONOTONIC_MODES, SEMANTIC_CHECK_DEFINITIONS  # noqa: F401
from .data_contract_semantic_scalar import check_allow_null_constraint as _check_allow_null_constraint
from .data_contract_semantic_scalar import check_range_constraint as _check_range_constraint
from .data_contract_semantic_scalar import check_unique_constraint as _check_unique_constraint
from .data_contract_semantic_statistics import canonical_flag_value as _canonical_flag_value  # noqa: F401
from .data_contract_semantic_statistics import (
    check_error_bar_source_constraint as _check_error_bar_source_constraint,
)
from .data_contract_semantic_statistics import (
    check_linear_fit_constraint as _check_linear_fit_constraint,
)
from .data_contract_semantic_statistics import (
    check_log_scale_positive_constraint as _check_log_scale_positive_constraint,
)
from .data_contract_semantic_statistics import check_mean_sem_constraint as _check_mean_sem_constraint
from .data_contract_semantic_statistics import (
    check_outlier_flag_constraint as _check_outlier_flag_constraint,
)
from .data_contract_semantic_statistics import finite_float as _finite_float  # noqa: F401
from .data_contract_semantic_statistics import numeric_series_or_error as _numeric_series_or_error  # noqa: F401
from .data_contract_semantic_units import (
    check_axis_unit_constraint as _semantic_axis_unit_constraint,
)
from .data_contract_semantic_units import (
    check_unit_coherence_constraint as _semantic_unit_coherence_constraint,
)
from .data_contract_semantic_units import (
    check_unit_compatibility as _semantic_unit_compatibility,
)
from .data_contract_semantic_units import (
    format_unit_signature as _format_unit_signature,  # noqa: F401
)
from .data_contract_semantic_units import (
    parse_unit_signature as _parse_unit_signature,  # noqa: F401
)
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
    _pint = None
    _ureg = None
    _PINT_AVAILABLE = False

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
            scalar_errors, scalar_rows = _check_allow_null_constraint(series, col, max_row_detail)
            errors.extend(scalar_errors)
            row_violations.extend(scalar_rows)

        # 2. Range check
        val_range = constraints.get("range")
        if val_range and len(val_range) == 2:
            scalar_errors, scalar_rows = _check_range_constraint(series, col, val_range, max_row_detail)
            errors.extend(scalar_errors)
            row_violations.extend(scalar_rows)
            if scalar_errors and not scalar_rows:
                continue

        # 3. Unique check
        is_unique_req = constraints.get("unique", False)
        if is_unique_req and not series.is_unique:
            scalar_errors, scalar_rows = _check_unique_constraint(series, col, max_row_detail)
            errors.extend(scalar_errors)
            row_violations.extend(scalar_rows)

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
    return _semantic_monotonic_within_group_constraint(
        df,
        series,
        col,
        raw_check,
        stripped_to_actual,
        max_row_detail,
        calculation_checks=calculation_checks,
        csv_rel_path=csv_rel_path,
        source_config_path=source_config_path,
        resolve_group_columns=_resolve_group_columns,
        group_dict=_group_dict,
        append_calculation_check=_append_calculation_check,
        append_failed_calculation_check=_append_failed_calculation_check,
        check_monotonic_constraint_func=_check_monotonic_constraint,
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
    return _semantic_unit_coherence_constraint(
        col,
        raw_check,
        stripped_to_actual,
        calculation_checks=calculation_checks,
        csv_rel_path=csv_rel_path,
        source_config_path=source_config_path,
        append_calculation_check=_append_calculation_check,
        append_failed_calculation_check=_append_failed_calculation_check,
    )


def _check_axis_unit_constraint(
    col,
    raw_check,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
    unit_checker=None,
):
    checker = unit_checker or _check_unit_compatibility
    return _semantic_axis_unit_constraint(
        col,
        raw_check,
        calculation_checks=calculation_checks,
        csv_rel_path=csv_rel_path,
        source_config_path=source_config_path,
        unit_checker=checker,
        append_calculation_check=_append_calculation_check,
        append_failed_calculation_check=_append_failed_calculation_check,
        json_safe_value=_json_safe_value,
    )


def _check_statistical_quality(
    df,
    csv_rel_path,
    cv_threshold,
    project_dir,
    *,
    write_diagnostics: bool = True,
    log_func=None,
):
    """
    수치 컬럼의 변동계수(CV = std/mean)를 계산하여
    cv_threshold 초과 시 주황색 경고를 출력하고 진단 리포트에 기록합니다.
    평균이 0에 가까운 컬럼(|mean| < 1e-9)은 건너뜁니다.

    Returns:
        dict with keys: cv_warnings, cv_threshold, quality_passed, report_path
    """
    return _quality_check_statistical_quality(
        df,
        csv_rel_path,
        cv_threshold,
        project_dir,
        write_diagnostics=write_diagnostics,
        log_func=log_func or _log,
    )


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
    dimensionality_error = _pint.DimensionalityError if _pint is not None else Exception
    return _semantic_unit_compatibility(
        col_name,
        actual_unit_str,
        expected_unit_str,
        pint_available=available,
        ureg=registry,
        log_func=log,
        dimensionality_error=dimensionality_error,
    )
