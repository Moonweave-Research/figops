from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def check_statistical_quality(
    df: Any,
    csv_rel_path: str,
    cv_threshold: float,
    project_dir: str | Path,
    *,
    write_diagnostics: bool = True,
    log_func: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Calculate numeric column coefficient of variation and emit quality warnings.

    Returns:
        dict with keys: cv_warnings, cv_threshold, quality_passed, report_path
    """
    log = log_func or (lambda _message: None)
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
    for warning in warnings:
        log(
            f"         - '{warning['column']}': CV = {warning['cv']:.1%} "
            f"(threshold: {cv_threshold:.0%})"
        )

    if not write_diagnostics:
        return quality_result

    # Preserve historical best-effort diagnostics behavior.
    try:
        project_path = Path(project_dir).expanduser().resolve()
        diag_dir = project_path / "results" / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ts_iso = datetime.now(timezone.utc).isoformat()

        report_path = diag_dir / f"quality_score_{ts}.md"
        lines = [
            f"## Statistical Quality Warning -- {csv_rel_path}",
            f"_Generated: {ts_iso}_\n",
            f"CV threshold: {cv_threshold:.0%}\n",
            "| Column | CV | Status |",
            "| ------ | -- | ------ |",
        ]
        for warning in warnings:
            lines.append(f"| {warning['column']} | {warning['cv']:.1%} | ⚠️ High noise |")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        log(f"      📄 Quality report: {report_path}")
        quality_result["report_path"] = str(report_path)

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
