import importlib.util
import os

from .utils import ensure_local_files, resolve_path

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

    print(f"      ℹ️  Large file ({file_size // 1024 // 1024} MB) — using chunked read")
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
                "pyarrow is required to read Parquet files. "
                "Install with: uv pip install 'graph-making-hub[io]'"
            ) from exc
        return pd.read_parquet(data_path)

    if suffix in {".h5", ".hdf5"}:
        try:
            import tables  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "PyTables (tables) is required to read HDF5 files. "
                "Install with: uv pip install 'graph-making-hub[io]'"
            ) from exc
        try:
            return pd.read_hdf(data_path, key=hdf_key)
        except KeyError:
            # hdf_key 미존재 시 첫 번째 키로 재시도
            import h5py
            with h5py.File(data_path, "r") as hf:
                first_key = next(iter(hf.keys()), None)
            if first_key is None:
                raise KeyError(f"HDF5 file has no datasets: {data_path}")
            from pathlib import Path
            print(
                f"      ⚠️  HDF5 key '{hdf_key}' not found in {Path(data_path).name}"
                f" — using first available key '/{first_key}'."
                " Verify this is the correct dataset."
            )
            return pd.read_hdf(data_path, key=first_key)

    if suffix == ".feather":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pyarrow is required to read Feather files. "
                "Install with: uv pip install 'graph-making-hub[io]'"
            ) from exc
        return pd.read_feather(data_path)

    raise ValueError(
        f"Unsupported file format '{suffix}' for: {data_path}. "
        "Supported: .csv, .tsv, .txt, .parquet, .h5, .hdf5, .feather"
    )


def _dtype_matches(series, expected, pd):
    exp = str(expected).strip().lower()

    if exp in {'int', 'integer', 'int64', 'int32'}:
        return pd.api.types.is_integer_dtype(series)
    if exp in {'float', 'float64', 'float32'}:
        return pd.api.types.is_float_dtype(series)
    if exp in {'number', 'numeric'}:
        return pd.api.types.is_numeric_dtype(series)
    if exp in {'str', 'string', 'object'}:
        return pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
    if exp in {'bool', 'boolean'}:
        return pd.api.types.is_bool_dtype(series)
    if exp in {'datetime', 'datetime64'}:
        return pd.api.types.is_datetime64_any_dtype(series)

    # Unknown alias: strict compare with dtype name
    return str(series.dtype).lower() == exp

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


def validate_data_contract_preflight(project_dir, config, require_existing: bool = False):
    contract = config.get("data_contract", {})
    checks = contract.get("csv_checks", []) if isinstance(contract, dict) else []

    if not checks:
        return True

    print("\n🧪 [Data Contract Preflight]")
    for i, check in enumerate(checks, 1):
        rel_path = check.get("path")
        if not isinstance(rel_path, str) or not rel_path.strip():
            print(f"   ❌ Check {i}: data_contract.csv_checks[{i - 1}].path is missing.")
            return False

        rel_path = rel_path.strip()
        resolved_path = resolve_path(project_dir, rel_path)
        suffix = os.path.splitext(resolved_path)[1].lower()
        print(f"   ➤ Check {i}: {rel_path}")

        if suffix not in _SUPPORTED_DATA_CONTRACT_SUFFIXES:
            supported = ", ".join(sorted(_SUPPORTED_DATA_CONTRACT_SUFFIXES))
            print(
                f"      ❌ Unsupported data_contract format '{suffix or '<none>'}'. "
                f"Supported: {supported}"
            )
            return False

        dependency = _OPTIONAL_IO_DEPENDENCIES.get(suffix)
        if dependency is not None:
            module_name, display_name = dependency
            if not _module_available(module_name):
                print(
                    f"      ❌ {display_name} is required for '{suffix}' files. "
                    "Install with: uv sync --extra io"
                )
                return False

        if require_existing:
            if not os.path.exists(resolved_path):
                print(f"      ❌ Required data_contract file not found: {resolved_path}")
                return False
            ensure_local_files([resolved_path])

        print("      ✅ Preflight passed")

    print("   ✅ Data contract preflight completed.")
    return True

def validate_data_contract(project_dir, config):
    contract = config.get('data_contract', {})
    checks = contract.get('csv_checks', []) if isinstance(contract, dict) else []

    if not checks:
        return True

    try:
        import pandas as pd
    except ImportError:
        print("❌ Error: data_contract requires pandas, but pandas is not installed.")
        return False

    print("\n🔍 [Data Contract Step]")
    for i, check in enumerate(checks, 1):
        csv_path = resolve_path(project_dir, check['path'])
        required_cols = check.get('required_columns', []) or []
        dtypes = check.get('dtypes', {}) or {}
        min_rows = check.get('min_rows', None)

        print(f"   ➤ Check {i}: {check['path']}")
        if not os.path.exists(csv_path):
            print(f"      ❌ Required CSV not found: {csv_path}")
            return False

        ensure_local_files([csv_path])

        try:
            df = _read_data_safe(csv_path, pd)
        except FileNotFoundError:
            print(f"      ❌ CSV file not found: {csv_path}")
            return False
        except PermissionError:
            print(f"      ❌ Permission denied: Cannot read {csv_path}. Check file locks.")
            return False
        except Exception as e:
            print(f"      ❌ Failed to read CSV: {csv_path}\n      └─ Detail: {type(e).__name__}: {e}")
            return False

        if min_rows is not None and len(df) < min_rows:
            print(f"      ❌ Row count check failed: expected >= {min_rows}, got {len(df)}")
            return False

        stripped_to_actual = {}
        for actual_col in df.columns:
            stripped_col = str(actual_col).strip()
            if stripped_col in stripped_to_actual and stripped_to_actual[stripped_col] != actual_col:
                print(
                    "      ❌ Ambiguous columns after strip normalization: "
                    f"'{stripped_to_actual[stripped_col]}' and '{actual_col}'"
                )
                return False
            stripped_to_actual[stripped_col] = actual_col

        missing = [col for col in required_cols if str(col).strip() not in stripped_to_actual]
        if missing:
            print(f"      ❌ Missing required columns: {missing}")
            return False

        for col, expected in dtypes.items():
            normalized_col = str(col).strip()
            actual_col = stripped_to_actual.get(normalized_col)
            if actual_col is None:
                print(f"      ❌ Dtype check failed: column '{col}' not found.")
                return False
            if not _dtype_matches(df[actual_col], expected, pd):
                print(
                    f"      ❌ Dtype mismatch for '{col}': expected '{expected}', "
                    f"got '{df[actual_col].dtype}'."
                )
                return False

        # --- Semantic Validation Layer ---
        semantic_checks = check.get('semantic_checks', {})
        if semantic_checks:
            semantic_errors, row_violations = _validate_semantic_constraints(
                df, semantic_checks, stripped_to_actual,
            )
            if semantic_errors:
                print(f"      ❌ Semantic validation failed for '{check['path']}':")
                for s_err in semantic_errors:
                    print(f"         - {s_err}")
                # Generate Markdown diagnostic report
                if row_violations:
                    try:
                        from .error_dumper import dump_contract_report
                        rpt = dump_contract_report(
                            project_dir, check['path'], row_violations,
                        )
                        if rpt:
                            print(f"      📄 Report: {rpt}")
                    except Exception:
                        pass
                return False

        # --- Statistical Quality Score ---
        cv_threshold = contract.get('cv_threshold', 0.10)
        quality_result = _check_statistical_quality(df, check['path'], cv_threshold, project_dir)
        if not quality_result["quality_passed"]:
            print(f"      🟠 quality_passed=False for '{check['path']}' (CV threshold: {cv_threshold:.0%})")

        print(f"      ✅ Passed ({len(df)} rows)")

    print("   ✅ Data contract checks completed.")
    return True

def _validate_semantic_constraints(df, semantic_checks, stripped_to_actual):
    """
    데이터프레임의 논리적 제약 조건(range, allow_null, unique, unit, monotonic)을 검증합니다.

    Returns:
        (errors, row_violations) -- errors는 요약 문자열 리스트,
        row_violations는 행 단위 dict 리스트 (error_dumper용).
    """
    errors = []
    row_violations = []
    conversions = []
    max_row_detail = 50  # 리포트에 포함할 최대 행 수

    for col, constraints in semantic_checks.items():
        norm_col = str(col).strip()
        actual_col = stripped_to_actual.get(norm_col)

        if not actual_col:
            continue  # Already handled by required_columns check

        series = df[actual_col]

        # 1. Null check
        allow_null = constraints.get('allow_null', True)
        if not allow_null and series.isnull().any():
            null_count = int(series.isnull().sum())
            errors.append(
                f"Column '{col}': found {null_count} null value(s) (allow_null=false)"
            )
            null_rows = series[series.isnull()].index[:max_row_detail]
            for idx in null_rows:
                row_violations.append({
                    "row": str(idx),
                    "column": col,
                    "value": "NaN",
                    "expected": "non-null",
                    "violation_type": "null_found",
                })

        # 2. Range check
        val_range = constraints.get('range')
        if val_range and len(val_range) == 2:
            min_val, max_val = val_range
            if not (isinstance(min_val, (int, float)) and isinstance(max_val, (int, float))):
                errors.append(f"Column '{col}': range bounds must be numeric, got {val_range}")
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
                    row_violations.append({
                        "row": str(idx),
                        "column": col,
                        "value": str(series.iloc[idx]),
                        "expected": f"range [{min_val}, {max_val}]",
                        "violation_type": "out_of_range",
                    })

        # 3. Unique check
        is_unique_req = constraints.get('unique', False)
        if is_unique_req and not series.is_unique:
            dup_count = int(series.duplicated().sum())
            errors.append(
                f"Column '{col}': found {dup_count} duplicate value(s) (unique=true)"
            )
            dup_rows = series[series.duplicated(keep=False)].index[:max_row_detail]
            for idx in dup_rows:
                row_violations.append({
                    "row": str(idx),
                    "column": col,
                    "value": str(series.iloc[idx]),
                    "expected": "unique",
                    "violation_type": "duplicate",
                })

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

        # 5. Unit check (requires pint)
        expected_unit = constraints.get('unit')
        actual_unit = constraints.get('actual_unit')
        if expected_unit and actual_unit:
            result = _check_unit_compatibility(col, actual_unit, expected_unit)
            if result == "incompatible":
                errors.append(
                    f"Column '{col}': unit '{actual_unit}' is incompatible "
                    f"with expected '{expected_unit}'"
                )
                row_violations.append({
                    "row": "*",
                    "column": col,
                    "value": actual_unit,
                    "expected": expected_unit,
                    "violation_type": "unit_incompatible",
                })
            elif isinstance(result, tuple):
                conversions.append((col, actual_col, result))

    # Apply auto-conversions after all checks pass
    if not errors and conversions:
        for col, actual_col, (factor, from_u, to_u) in conversions:
            df[actual_col] = df[actual_col] * factor
            print(
                f"      ⚠️  Column '{col}': auto-converted "
                f"{from_u} -> {to_u} (x{factor})"
            )

    return errors, row_violations


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

    print(f"      🟠 [Quality Score] High noise detected in '{csv_rel_path}':")
    for w in warnings:
        print(f"         - '{w['column']}': CV = {w['cv']:.1%} (threshold: {cv_threshold:.0%})")

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
        print(f"      📄 Quality report: {rpt}")
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
        print(f"      ⚠️  Column '{col_name}': unit check skipped (pint not installed)")
        return "skip"

    try:
        expected = _ureg.parse_expression(expected_unit_str)
        actual = _ureg.parse_expression(actual_unit_str)
    except Exception:
        print(
            f"      ⚠️  Column '{col_name}': could not parse units "
            f"('{actual_unit_str}' or '{expected_unit_str}')"
        )
        return "skip"

    if actual.units == expected.units:
        return "ok"

    try:
        factor = actual.to(expected.units).magnitude
        return (factor, actual_unit_str, expected_unit_str)
    except _pint.DimensionalityError:
        return "incompatible"
