import importlib.util
import json
import logging
import math
import os
from pathlib import Path

from .adapters import select_adapters
from .logging import get_logger
from .utils import resolve_path

logger = get_logger(__name__)


def _log(message: str) -> None:
    if "❌" in message:
        level = logging.ERROR
    elif "⚠️" in message or "🟠" in message:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(level, message)


# ---------------------------------------------------------------------------
# Unit-aware validation via Pint (optional dependency)
# ---------------------------------------------------------------------------
try:
    import pint as _pint

    _ureg = _pint.UnitRegistry()
    _PINT_AVAILABLE = True
except ImportError:
    _ureg = None
    _PINT_AVAILABLE = False

_CSV_CHUNK_THRESHOLD_BYTES = 256 * 1024 * 1024  # 256 MB
_CSV_CHUNK_SIZE = 50_000  # rows per chunk
_SUPPORTED_DATA_CONTRACT_SUFFIXES = {
    ".csv",
    ".tsv",
    ".txt",
    ".parquet",
    ".h5",
    ".hdf5",
    ".feather",
}
_OPTIONAL_IO_DEPENDENCIES = {
    ".parquet": ("pyarrow", "pyarrow"),
    ".feather": ("pyarrow", "pyarrow"),
    ".h5": ("tables", "PyTables (tables)"),
    ".hdf5": ("tables", "PyTables (tables)"),
}
_MONOTONIC_MODES = {"increasing", "decreasing", "nondecreasing", "nonincreasing"}


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _read_csv_safe(csv_path, pd, **read_kwargs):
    """
    CSV를 안전하게 읽습니다.
    256 MB 미만: 전체 로드 (빠름).
    256 MB 이상: 청크 단위 로드 후 concat (메모리 효율).
    """
    file_size = os.path.getsize(csv_path)
    if file_size < _CSV_CHUNK_THRESHOLD_BYTES:
        return pd.read_csv(csv_path, encoding="utf-8-sig", **read_kwargs)

    _log(f"      ℹ️  Large file ({file_size // 1024 // 1024} MB) — using chunked read")
    chunks = pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        chunksize=_CSV_CHUNK_SIZE,
        **read_kwargs,
    )
    return pd.concat(chunks, ignore_index=True)


def _read_data_safe(data_path, pd, hdf_key: str = "/data"):
    """
    포맷을 자동 감지하여 데이터를 읽습니다.
    - .csv / .tsv / .txt  → _read_csv_safe() (청크 지원)
    - .parquet            → pd.read_parquet() (pyarrow 필요)
    - .h5 / .hdf5         → pd.read_hdf()    (tables 필요, key=hdf_key)
    - .feather            → pd.read_feather() (pyarrow 필요)
    그 외 확장자는 CSV로 fallback합니다.
    """
    suffix = os.path.splitext(data_path)[1].lower()

    if suffix in {".csv", ".tsv", ".txt"}:
        read_kwargs = {}
        if suffix == ".tsv":
            read_kwargs["sep"] = "\t"
        elif suffix == ".txt":
            read_kwargs["sep"] = None
            read_kwargs["engine"] = "python"
        return _read_csv_safe(data_path, pd, **read_kwargs)

    if suffix == ".parquet":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pyarrow is required to read Parquet files. Install with: uv pip install 'graph-making-hub[io]'"
            ) from exc
        return pd.read_parquet(data_path)

    if suffix in {".h5", ".hdf5"}:
        try:
            import tables  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "PyTables (tables) is required to read HDF5 files. Install with: uv pip install 'graph-making-hub[io]'"
            ) from exc
        try:
            return pd.read_hdf(data_path, key=hdf_key)
        except KeyError:
            # Do NOT silently fall back to a different dataset: rendering the wrong
            # data with no signal is worse than failing. Report the available keys.
            import h5py

            with h5py.File(data_path, "r") as hf:
                available_keys = list(hf.keys())
            if not available_keys:
                raise KeyError(f"HDF5 file has no datasets: {data_path}")
            from pathlib import Path

            available = ", ".join(f"/{key}" for key in available_keys)
            raise KeyError(
                f"HDF5 key '{hdf_key}' not found in {Path(data_path).name}. "
                f"Available keys: {available}. Set the correct key explicitly "
                "instead of relying on a fallback (the wrong dataset would render silently)."
            )

    if suffix == ".feather":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pyarrow is required to read Feather files. Install with: uv pip install 'graph-making-hub[io]'"
            ) from exc
        return pd.read_feather(data_path)

    raise ValueError(
        f"Unsupported file format '{suffix}' for: {data_path}. "
        "Supported: .csv, .tsv, .txt, .parquet, .h5, .hdf5, .feather"
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


def get_data_contract_paths(config):
    contract = config.get("data_contract", {})
    checks = contract.get("csv_checks", []) if isinstance(contract, dict) else []
    paths = []
    for check in checks:
        if isinstance(check, dict):
            rel_path = check.get("path")
            if isinstance(rel_path, str) and rel_path.strip():
                paths.append(rel_path.strip())
    # Keep order while removing duplicates
    deduped = []
    seen = set()
    for p in paths:
        if p not in seen:
            deduped.append(p)
            seen.add(p)
    return deduped


def _resolve_prefetcher(config: dict, prefetcher=None):
    return prefetcher if prefetcher is not None else select_adapters(config).prefetcher


def validate_data_contract_preflight(project_dir, config, require_existing: bool = False, prefetcher=None):
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
        resolved_path = resolve_path(project_dir, rel_path)
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
            if not os.path.exists(resolved_path):
                _log(f"      ❌ Required data_contract file not found: {resolved_path}")
                return False
            prefetcher.ensure_local([resolved_path])

        _log("      ✅ Preflight passed")

    _log("   ✅ Data contract preflight completed.")
    return True


def validate_data_contract(project_dir, config, prefetcher=None):
    prefetcher = _resolve_prefetcher(config, prefetcher)
    contract = config.get("data_contract", {})
    checks = contract.get("csv_checks", []) if isinstance(contract, dict) else []

    if not checks:
        _write_calculation_checks_sidecar(project_dir, [])
        return True

    try:
        import pandas as pd
    except ImportError:
        _log("❌ Error: data_contract requires pandas, but pandas is not installed.")
        return False

    _log("\n🔍 [Data Contract Step]")
    _write_calculation_checks_sidecar(project_dir, [])
    calculation_checks = []
    contract_failed = False
    for i, check in enumerate(checks, 1):
        csv_path = resolve_path(project_dir, check["path"])
        required_cols = check.get("required_columns", []) or []
        dtypes = check.get("dtypes", {}) or {}
        min_rows = check.get("min_rows", None)

        _log(f"   ➤ Check {i}: {check['path']}")
        if not os.path.exists(csv_path):
            _log(f"      ❌ Required CSV not found: {csv_path}")
            return False

        prefetcher.ensure_local([csv_path])

        try:
            df = _read_data_safe(csv_path, pd)
        except FileNotFoundError:
            _log(f"      ❌ CSV file not found: {csv_path}")
            return False
        except PermissionError:
            _log(f"      ❌ Permission denied: Cannot read {csv_path}. Check file locks.")
            return False
        except Exception as e:
            _log(f"      ❌ Failed to read CSV: {csv_path}\n      └─ Detail: {type(e).__name__}: {e}")
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
                _write_calculation_checks_sidecar(project_dir, calculation_checks)
                _log(f"      ❌ Semantic validation failed for '{check['path']}':")
                for s_err in semantic_errors:
                    _log(f"         - {s_err}")
                # Generate Markdown diagnostic report
                if row_violations:
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

        # --- Statistical Quality Score ---
        cv_threshold = contract.get("cv_threshold", 0.10)
        quality_result = _check_statistical_quality(df, check["path"], cv_threshold, project_dir)
        if not quality_result["quality_passed"]:
            _log(f"      🟠 quality_passed=False for '{check['path']}' (CV threshold: {cv_threshold:.0%})")

        _log(f"      ✅ Passed ({len(df)} rows)")

    _write_calculation_checks_sidecar(project_dir, calculation_checks)
    if contract_failed:
        return False
    _log("   ✅ Data contract checks completed.")
    return True


def _validate_semantic_constraints(
    df,
    semantic_checks,
    stripped_to_actual,
    *,
    calculation_checks=None,
    csv_rel_path: str = "",
    source_config_path: str = "project_config.yaml",
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
            )
            errors.extend(axis_errors)
            row_violations.extend(axis_rows)

        # 6. Unit check (requires pint)
        expected_unit = constraints.get("unit")
        actual_unit = constraints.get("actual_unit")
        if expected_unit and actual_unit:
            result = _check_unit_compatibility(col, actual_unit, expected_unit)
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


def _check_axis_unit_constraint(
    col,
    raw_check,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
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

    result = _check_unit_compatibility(col, data_unit.strip(), display_unit.strip())
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


def _check_statistical_quality(df, csv_rel_path, cv_threshold, project_dir):
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

    _log(f"      🟠 [Quality Score] High noise detected in '{csv_rel_path}':")
    for w in warnings:
        _log(f"         - '{w['column']}': CV = {w['cv']:.1%} (threshold: {cv_threshold:.0%})")

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
        _log(f"      📄 Quality report: {rpt}")
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


def _check_unit_compatibility(col_name, actual_unit_str, expected_unit_str):
    """
    Pint를 사용하여 단위 호환성을 검증합니다.

    Returns:
        "ok"            -- 동일 단위
        (factor, a, b)  -- 호환 가능, 변환 계수 반환
        "incompatible"  -- 차원 불일치
        "skip"          -- Pint 미설치
    """
    if not _PINT_AVAILABLE:
        _log(f"      ⚠️  Column '{col_name}': unit check skipped (pint not installed)")
        return "skip"

    try:
        expected = _ureg.parse_expression(expected_unit_str)
        actual = _ureg.parse_expression(actual_unit_str)
    except Exception:
        _log(f"      ⚠️  Column '{col_name}': could not parse units ('{actual_unit_str}' or '{expected_unit_str}')")
        return "skip"

    if actual.units == expected.units:
        return "ok"

    try:
        factor = actual.to(expected.units).magnitude
        return (factor, actual_unit_str, expected_unit_str)
    except _pint.DimensionalityError:
        return "incompatible"
