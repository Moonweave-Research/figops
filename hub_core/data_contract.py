import logging
import os

from . import data_contract_io as _data_contract_io
from . import data_contract_semantics as _data_contract_semantics
from .logging import get_logger
from .project_paths import (
    ProjectPathError,
    resolve_project_input,
    revalidate_project_input,
    snapshot_project_input,
)

logger = get_logger(__name__)


def _log(message: str) -> None:
    if "❌" in message:
        level = logging.ERROR
    elif "⚠️" in message or "🟠" in message:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(level, message)


_OPTIONAL_IO_DEPENDENCIES = _data_contract_io.OPTIONAL_IO_DEPENDENCIES
_SUPPORTED_DATA_CONTRACT_SUFFIXES = _data_contract_io.SUPPORTED_DATA_CONTRACT_SUFFIXES
get_data_contract_paths = _data_contract_io.get_data_contract_paths


def _module_available(module_name: str) -> bool:
    return _data_contract_io.module_available(module_name)


def _read_csv_safe(csv_path, pd, **read_kwargs):
    return _data_contract_io.read_csv_safe(csv_path, pd, log_func=_log, **read_kwargs)


def _read_data_safe(data_path, pd, hdf_key: str = "/data"):
    suffix = os.path.splitext(data_path)[1].lower()

    if suffix in {".csv", ".tsv", ".txt"}:
        read_kwargs = {}
        if suffix == ".tsv":
            read_kwargs["sep"] = "\t"
        elif suffix == ".txt":
            read_kwargs["sep"] = None
            read_kwargs["engine"] = "python"
        return _read_csv_safe(data_path, pd, **read_kwargs)

    return _data_contract_io.read_data_safe(data_path, pd, hdf_key=hdf_key)


def _resolve_prefetcher(config, prefetcher=None):
    return _data_contract_io.resolve_prefetcher(config, prefetcher=prefetcher)


def _read_project_data_safe(project_dir, declared_path, pd, *, expected_snapshot, hdf_key: str = "/data"):
    return _data_contract_io.read_project_data_safe(
        project_dir,
        declared_path,
        pd,
        expected_snapshot=expected_snapshot,
        hdf_key=hdf_key,
    )


_MONOTONIC_MODES = _data_contract_semantics._MONOTONIC_MODES
SEMANTIC_CHECK_DEFINITIONS = _data_contract_semantics.SEMANTIC_CHECK_DEFINITIONS
_PINT_AVAILABLE = _data_contract_semantics._PINT_AVAILABLE
_ureg = _data_contract_semantics._ureg


def _validate_semantic_constraints(
    df,
    semantic_checks,
    stripped_to_actual,
    *,
    calculation_checks=None,
    csv_rel_path: str = "",
    source_config_path: str = "project_config.yaml",
):
    return _data_contract_semantics._validate_semantic_constraints(
        df,
        semantic_checks,
        stripped_to_actual,
        calculation_checks=calculation_checks,
        csv_rel_path=csv_rel_path,
        source_config_path=source_config_path,
        unit_checker=_check_unit_compatibility,
    )


def _check_unit_compatibility(col_name, actual_unit_str, expected_unit_str):
    return _data_contract_semantics._check_unit_compatibility(
        col_name,
        actual_unit_str,
        expected_unit_str,
        pint_available=_PINT_AVAILABLE,
        ureg=_ureg,
        log_func=_log,
    )


_calculation_summary = _data_contract_semantics._calculation_summary
_write_calculation_checks_sidecar = _data_contract_semantics._write_calculation_checks_sidecar
_append_calculation_check = _data_contract_semantics._append_calculation_check
_resolve_group_columns = _data_contract_semantics._resolve_group_columns
_json_safe_value = _data_contract_semantics._json_safe_value
_is_nullish = _data_contract_semantics._is_nullish
_append_failed_calculation_check = _data_contract_semantics._append_failed_calculation_check
_group_dict = _data_contract_semantics._group_dict
_check_monotonic_within_group_constraint = _data_contract_semantics._check_monotonic_within_group_constraint
_check_min_replicates_constraint = _data_contract_semantics._check_min_replicates_constraint
_check_expected_sample_count_constraint = _data_contract_semantics._check_expected_sample_count_constraint
_check_grouped_cv_constraint = _data_contract_semantics._check_grouped_cv_constraint
_check_allow_null_constraint = _data_contract_semantics._check_allow_null_constraint
_check_range_constraint = _data_contract_semantics._check_range_constraint
_check_unique_constraint = _data_contract_semantics._check_unique_constraint
_numeric_series_or_error = _data_contract_semantics._numeric_series_or_error
_check_log_scale_positive_constraint = _data_contract_semantics._check_log_scale_positive_constraint
_check_error_bar_source_constraint = _data_contract_semantics._check_error_bar_source_constraint
_check_mean_sem_constraint = _data_contract_semantics._check_mean_sem_constraint
_finite_float = _data_contract_semantics._finite_float
_check_linear_fit_constraint = _data_contract_semantics._check_linear_fit_constraint
_canonical_flag_value = _data_contract_semantics._canonical_flag_value
_check_outlier_flag_constraint = _data_contract_semantics._check_outlier_flag_constraint
_parse_unit_signature = _data_contract_semantics._parse_unit_signature
_format_unit_signature = _data_contract_semantics._format_unit_signature
_check_unit_coherence_constraint = _data_contract_semantics._check_unit_coherence_constraint


def _check_axis_unit_constraint(
    col,
    raw_check,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
):
    return _data_contract_semantics._check_axis_unit_constraint(
        col,
        raw_check,
        calculation_checks=calculation_checks,
        csv_rel_path=csv_rel_path,
        source_config_path=source_config_path,
        unit_checker=_check_unit_compatibility,
    )


_check_monotonic_constraint = _data_contract_semantics._check_monotonic_constraint
def _check_statistical_quality(df, csv_rel_path, cv_threshold, project_dir, *, write_diagnostics: bool = True):
    return _data_contract_semantics._check_statistical_quality(
        df,
        csv_rel_path,
        cv_threshold,
        project_dir,
        write_diagnostics=write_diagnostics,
        log_func=_log,
    )


def _dtype_matches(series, expected, pd):
    exp = str(expected).strip().lower()

    if exp in {"int", "integer", "int64", "int32"}:
        return pd.api.types.is_integer_dtype(series)
    if exp in {"float", "float64", "float32"}:
        return pd.api.types.is_float_dtype(series)
    if exp in {"number", "numeric"}:
        return pd.api.types.is_numeric_dtype(series)
    if exp in {"str", "string", "object"}:
        return pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
    if exp in {"bool", "boolean"}:
        return pd.api.types.is_bool_dtype(series)
    if exp in {"datetime", "datetime64"}:
        return pd.api.types.is_datetime64_any_dtype(series)

    # Unknown alias is a config error, not a silently-failing dtype check.
    raise ValueError(
        f"unknown dtype alias: '{expected}'. Supported aliases: "
        "int/integer/int64/int32, float/float64/float32, number/numeric, "
        "str/string/object, bool/boolean, datetime/datetime64."
    )


def validate_data_contract_preflight(
    project_dir,
    config,
    require_existing: bool = False,
    prefetcher=None,
    *,
    raise_path_contract_errors: bool = False,
):
    prefetcher = _resolve_prefetcher(config, prefetcher)
    contract = config.get("data_contract", {})
    checks = contract.get("csv_checks", []) if isinstance(contract, dict) else []

    if not checks:
        return True

    _log("\n🧪 [Data Contract Preflight]")
    for i, check in enumerate(checks, 1):
        rel_path = check.get("path")
        if not isinstance(rel_path, str) or not rel_path.strip():
            _log(f"   ❌ Check {i}: data_contract.csv_checks[{i - 1}].path is missing.")
            return False

        rel_path = rel_path.strip()
        purpose = f"data_contract.csv_checks[{i}].path"
        try:
            resolved_path = resolve_project_input(
                project_dir,
                rel_path,
                must_exist=require_existing,
                purpose=purpose,
            )
        except FileNotFoundError as exc:
            _log(f"      ❌ {exc}")
            return False
        except ProjectPathError as exc:
            _log(f"      ❌ {exc}")
            if raise_path_contract_errors:
                raise
            return False
        suffix = os.path.splitext(resolved_path)[1].lower()
        _log(f"   ➤ Check {i}: {rel_path}")

        if suffix not in _SUPPORTED_DATA_CONTRACT_SUFFIXES:
            supported = ", ".join(sorted(_SUPPORTED_DATA_CONTRACT_SUFFIXES))
            _log(f"      ❌ Unsupported data_contract format '{suffix or '<none>'}'. Supported: {supported}")
            return False

        dependency = _OPTIONAL_IO_DEPENDENCIES.get(suffix)
        if dependency is not None:
            module_name, display_name = dependency
            if not _module_available(module_name):
                _log(f"      ❌ {display_name} is required for '{suffix}' files. Install with: uv sync --extra io")
                return False

        if require_existing:
            prefetcher.ensure_local([str(resolved_path)])
            try:
                snapshot = snapshot_project_input(project_dir, rel_path, purpose=purpose)
                revalidate_project_input(
                    project_dir,
                    rel_path,
                    expected_snapshot=snapshot,
                    purpose=purpose,
                )
            except FileNotFoundError as exc:
                _log(f"      ❌ {exc}")
                return False
            except ProjectPathError as exc:
                _log(f"      ❌ {exc}")
                if raise_path_contract_errors:
                    raise
                return False

        _log("      ✅ Preflight passed")

    _log("   ✅ Data contract preflight completed.")
    return True


def validate_data_contract(project_dir, config, prefetcher=None, *, write_sidecar: bool = True):
    prefetcher = _resolve_prefetcher(config, prefetcher)
    contract = config.get("data_contract", {})
    checks = contract.get("csv_checks", []) if isinstance(contract, dict) else []

    if not checks:
        if write_sidecar:
            _write_calculation_checks_sidecar(project_dir, [])
        return True

    try:
        import pandas as pd
    except ImportError:
        _log("❌ Error: data_contract requires pandas, but pandas is not installed.")
        return False

    _log("\n🔍 [Data Contract Step]")
    if write_sidecar:
        _write_calculation_checks_sidecar(project_dir, [])
    calculation_checks = []
    contract_failed = False
    for i, check in enumerate(checks, 1):
        declared_path = check["path"]
        purpose = f"data_contract.csv_checks[{i}].path"
        required_cols = check.get("required_columns", []) or []
        dtypes = check.get("dtypes", {}) or {}
        min_rows = check.get("min_rows", None)

        _log(f"   ➤ Check {i}: {check['path']}")
        try:
            csv_path = resolve_project_input(project_dir, declared_path, purpose=purpose)
        except (FileNotFoundError, ProjectPathError) as exc:
            _log(f"      ❌ {exc}")
            return False

        prefetcher.ensure_local([str(csv_path)])

        try:
            snapshot = snapshot_project_input(project_dir, declared_path, purpose=purpose)
            df = _read_project_data_safe(
                project_dir,
                declared_path,
                pd,
                expected_snapshot=snapshot,
            )
        except FileNotFoundError:
            _log(f"      ❌ data_contract input does not exist: {declared_path!r}.")
            return False
        except ProjectPathError as exc:
            _log(f"      ❌ {exc}")
            return False
        except PermissionError:
            _log(f"      ❌ Permission denied: Cannot read {declared_path!r}. Check file locks.")
            return False
        except Exception as e:
            _log(f"      ❌ Failed to read data_contract input {declared_path!r}: {type(e).__name__}: {e}")
            return False

        if min_rows is not None and len(df) < min_rows:
            _log(f"      ❌ Row count check failed: expected >= {min_rows}, got {len(df)}")
            return False

        stripped_to_actual = {}
        for actual_col in df.columns:
            stripped_col = str(actual_col).strip()
            if stripped_col in stripped_to_actual and stripped_to_actual[stripped_col] != actual_col:
                _log(
                    "      ❌ Ambiguous columns after strip normalization: "
                    f"'{stripped_to_actual[stripped_col]}' and '{actual_col}'"
                )
                return False
            stripped_to_actual[stripped_col] = actual_col

        missing = [col for col in required_cols if str(col).strip() not in stripped_to_actual]
        if missing:
            _log(f"      ❌ Missing required columns: {missing}")
            return False

        for col, expected in dtypes.items():
            normalized_col = str(col).strip()
            actual_col = stripped_to_actual.get(normalized_col)
            if actual_col is None:
                _log(f"      ❌ Dtype check failed: column '{col}' not found.")
                return False
            try:
                dtype_ok = _dtype_matches(df[actual_col], expected, pd)
            except ValueError as e:
                _log(f"      ❌ Dtype check failed for '{col}': {e}")
                return False
            if not dtype_ok:
                _log(f"      ❌ Dtype mismatch for '{col}': expected '{expected}', got '{df[actual_col].dtype}'.")
                return False

        # --- Semantic Validation Layer ---
        semantic_checks = check.get("semantic_checks", {})
        if semantic_checks:
            semantic_errors, row_violations = _validate_semantic_constraints(
                df,
                semantic_checks,
                stripped_to_actual,
                calculation_checks=calculation_checks,
                csv_rel_path=check["path"],
                source_config_path="project_config.yaml",
            )
            if semantic_errors:
                if write_sidecar:
                    _write_calculation_checks_sidecar(project_dir, calculation_checks)
                _log(f"      ❌ Semantic validation failed for '{check['path']}':")
                for s_err in semantic_errors:
                    _log(f"         - {s_err}")
                # Generate Markdown diagnostic report
                if write_sidecar and row_violations:
                    try:
                        from .error_dumper import dump_contract_report

                        rpt = dump_contract_report(
                            project_dir,
                            check["path"],
                            row_violations,
                        )
                        if rpt:
                            _log(f"      📄 Report: {rpt}")
                    except Exception:
                        pass
                contract_failed = True
                continue

        # --- Opt-in Statistical Quality Score ---
        # Generic numeric columns may be identifiers, time, or concentrations;
        # do not assign a measurement/noise meaning unless the project declares
        # this legacy CV policy explicitly.
        cv_columns = contract.get("cv_columns")
        if "cv_threshold" in contract and isinstance(cv_columns, list) and cv_columns:
            cv_threshold = contract["cv_threshold"]
            missing_cv_columns = [str(column) for column in cv_columns if str(column) not in df.columns]
            if missing_cv_columns:
                _log(
                    f"      ❌ CV measurement column(s) missing for '{check['path']}': "
                    f"{', '.join(missing_cv_columns)}"
                )
                contract_failed = True
                continue
            declared_columns = [str(column) for column in cv_columns]
            quality_result = _check_statistical_quality(
                df[declared_columns],
                check["path"],
                cv_threshold,
                project_dir,
                write_diagnostics=write_sidecar,
            )
            if not quality_result["quality_passed"]:
                _log(f"      🟠 quality_passed=False for '{check['path']}' (CV threshold: {cv_threshold:.0%})")

        _log(f"      ✅ Passed ({len(df)} rows)")

    if write_sidecar:
        _write_calculation_checks_sidecar(project_dir, calculation_checks)
    if contract_failed:
        return False
    _log("   ✅ Data contract checks completed.")
    return True
