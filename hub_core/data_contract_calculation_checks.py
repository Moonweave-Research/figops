from __future__ import annotations

import json
import math
from pathlib import Path


def calculation_summary(checks: list[dict]) -> dict:
    return {
        "checks": checks,
        "quality_passed": not any(check.get("status") in {"warning", "failed"} for check in checks),
        "manual_review_needed": any(bool(check.get("manual_review_needed")) for check in checks),
    }


def write_calculation_checks_sidecar(project_dir, checks: list[dict]) -> None:
    diag_dir = Path(project_dir).expanduser().resolve() / "results" / "diagnostics"
    sidecar = diag_dir / "calculation_checks.json"
    if not checks:
        if sidecar.exists():
            sidecar.unlink()
        return
    payload = {"schema_version": "1.0", **calculation_summary(checks)}
    diag_dir.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def append_calculation_check(
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


def resolve_group_columns(raw_group_by, stripped_to_actual):
    group_by = [str(item).strip() for item in raw_group_by or []]
    if not group_by:
        return [], [], ["<empty group_by>"]
    missing = [column for column in group_by if column not in stripped_to_actual]
    actual = [stripped_to_actual[column] for column in group_by if column in stripped_to_actual]
    return group_by, actual, missing


def is_nullish(value) -> bool:
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except Exception:
        pass
    return False


def json_safe_value(value):
    if is_nullish(value):
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


def append_failed_calculation_check(
    calculation_checks,
    *,
    csv_rel_path: str,
    name: str,
    target: str,
    source_config_path: str,
    message: str,
    violations: list[dict] | None = None,
) -> None:
    append_calculation_check(
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


def group_dict(group_by: list[str], group_key) -> dict:
    if len(group_by) == 1:
        if isinstance(group_key, tuple) and len(group_key) == 1:
            values = group_key
        else:
            values = (group_key,)
    else:
        values = tuple(group_key)
    return {column: json_safe_value(value) for column, value in zip(group_by, values, strict=False)}
