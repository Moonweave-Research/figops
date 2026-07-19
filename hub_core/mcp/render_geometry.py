from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hub_core.geometry_raw_contract import RawGeometryContractError, normalize_geometry_payload

GEOMETRY_DIAGNOSTICS_SCHEMA_VERSION = "geometry_diagnostics/2"
LAYOUT_REPORT_SCHEMA_VERSION = "layout_report/1"
SCRIPT_OUTPUT_TAIL_LINES = 40


def _geometry_stub(reason: str) -> dict[str, Any]:
    return {
        "schema_version": GEOMETRY_DIAGNOSTICS_SCHEMA_VERSION,
        "measurements": [
            {
                "metric_id": "geometry_diagnostics",
                "unit": "structured",
                "scope": "figure",
                "availability": "unavailable",
                "reason": reason,
            }
        ],
        "warnings": [reason],
    }

def _read_geometry_sidecar(job_root: Path) -> dict[str, Any]:
    sidecar = job_root / "geometry_diagnostics.json"
    try:
        text = sidecar.read_text(encoding="utf-8")
    except OSError:
        return _geometry_stub(
            "geometry_diagnostics_unavailable: no sidecar emitted",
        )
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return _geometry_stub(
            "geometry_diagnostics_unavailable: unreadable sidecar",
        )
    if not isinstance(loaded, dict):
        return _geometry_stub(
            "geometry_diagnostics_unavailable: malformed sidecar",
        )
    try:
        return normalize_geometry_payload(loaded)
    except RawGeometryContractError as exc:
        return _geometry_stub(f"geometry_diagnostics_unavailable: invalid sidecar ({exc})")

def _geometry_warnings(diagnostics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    raw_warnings = diagnostics.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(warning) for warning in raw_warnings)
    return warnings

def _layout_report_from_geometry(
    diagnostics: dict[str, Any],
    *,
    failure_stage: str = "",
    script_output: list[str] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": LAYOUT_REPORT_SCHEMA_VERSION,
        "passed": None,
        "overlaps": [],
        "clipped": [],
        "font_roles": {},
        "placement_consistency": [],
        "density": {},
        "render_errors": [],
        "warnings": [],
    }
    if failure_stage:
        report["passed"] = False
        tail = [str(line) for line in (script_output or [])][-SCRIPT_OUTPUT_TAIL_LINES:]
        report["render_errors"].append({"stage": failure_stage, "script_output_tail": tail})

    raw_warnings = diagnostics.get("warnings") if isinstance(diagnostics, dict) else None
    if isinstance(raw_warnings, list):
        report["warnings"].extend(str(warning) for warning in raw_warnings)

    measurements = diagnostics.get("measurements") if isinstance(diagnostics, dict) else None
    if not isinstance(measurements, list):
        return report

    legacy_checks: list[dict[str, Any]] = []
    for measurement in measurements:
        if not isinstance(measurement, dict) or measurement.get("availability") != "available":
            continue
        name = str(measurement.get("metric_id") or "").split("[", 1)[0]
        data = measurement.get("value") if isinstance(measurement.get("value"), dict) else {}
        check = {"name": name, "data": data, "detail": data.get("summary", "")}
        legacy_checks.append(check)
        if name in {"artist_overlaps", "legend_internal_overlaps", "marker_marker_overlaps"}:
            report["overlaps"].extend(_layout_overlap_items(name, data))
        elif name == "text_axis_edge_proximity":
            report["clipped"].extend(_layout_clipped_items(data))
        elif name == "label_offset_consistency":
            report["placement_consistency"].extend(_layout_placement_items(data))
        elif name == "font_size_token_drift":
            report["font_roles"] = _layout_font_roles(data, check)

    density = _layout_density(legacy_checks)
    if density:
        report["density"] = density
    return report

def _layout_overlap_items(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_overlaps = data.get("overlaps")
    if not isinstance(raw_overlaps, list):
        return []
    items: list[dict[str, Any]] = []
    for overlap in raw_overlaps:
        if not isinstance(overlap, dict):
            continue
        a = str(overlap.get("a", ""))
        b = str(overlap.get("b", ""))
        kind = str(overlap.get("kind") or _layout_overlap_kind(name, a, b))
        items.append(
            {
                "axes": int(overlap.get("axes", data.get("axis_index", 0))),
                "a": a,
                "b": b,
                "kind": kind,
                "iou": float(overlap.get("iou", 0.0)),
                "severity": str(overlap.get("severity") or _layout_overlap_severity(float(overlap.get("iou", 0.0)))),
            }
        )
    return items

def _layout_overlap_kind(name: str, a: str, b: str) -> str:
    if name == "legend_internal_overlaps":
        return "legend-internal"
    if name == "marker_marker_overlaps":
        return "marker-marker"
    labels = (a, b)
    if any(label.startswith("marker:") for label in labels) and any(
        label.startswith(("text:", "annotation:", "title:")) for label in labels
    ):
        return "text-marker"
    if all(label.startswith(("text:", "annotation:", "title:")) for label in labels):
        return "text-text"
    if any(label == "legend" or label.startswith("legend") for label in labels):
        return "legend-data"
    return "artist-artist"

def _layout_overlap_severity(iou: float) -> str:
    if iou >= 0.50:
        return "high"
    if iou >= 0.20:
        return "medium"
    if iou > 0:
        return "low"
    return "none"

def _layout_clipped_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list):
        return []
    items: list[dict[str, Any]] = []
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        edges = finding.get("edges") if isinstance(finding.get("edges"), list) else []
        items.append(
            {
                "axes": int(finding.get("axes", data.get("axis_index", 0))),
                "artist": str(finding.get("artist", "")),
                "edge": str(edges[0]) if edges else "",
                "edges": [str(edge) for edge in edges],
                "clipped": bool(finding.get("clipped")),
                "min_distance_px": float(finding.get("min_distance_px", 0.0)),
            }
        )
    return items

def _layout_placement_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("inconsistencies")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        placements = item.get("placements") if isinstance(item.get("placements"), list) else []
        panels = {
            str(placement.get("axis_index")): str(placement.get("direction"))
            for placement in placements
            if isinstance(placement, dict)
        }
        items.append(
            {
                "entity": str(item.get("label", "")),
                "directions": [str(direction) for direction in item.get("directions", [])],
                "panels": panels,
                "placements": placements,
            }
        )
    return items

def _layout_font_roles(data: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_sizes": data.get("token_sizes", []),
        "offenders": data.get("offenders", []),
        "role_size_counts": data.get("role_size_counts", {}),
        "note": str(check.get("detail", "")),
    }

def _layout_density(checks: list[Any]) -> dict[str, Any]:
    text_counts: dict[int, int] = {}
    repeated_labels = 0
    for check in checks:
        if not isinstance(check, dict) or check.get("name") != "label_offset_consistency":
            continue
        data = check.get("data") if isinstance(check.get("data"), dict) else {}
        raw_items = data.get("inconsistencies")
        if isinstance(raw_items, list):
            repeated_labels = len(raw_items)
    if repeated_labels:
        return {
            "repeated_label_inconsistency_count": int(repeated_labels),
            "warn": "repeated labels across sibling axes may be reducible with label-once/dedup placement",
        }
    return text_counts
