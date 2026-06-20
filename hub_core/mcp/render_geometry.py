from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GEOMETRY_DIAGNOSTICS_SCHEMA_VERSION = "geometry_diagnostics/1"
LAYOUT_REPORT_SCHEMA_VERSION = "layout_report/1"
_GEOMETRY_WARNING_ELIGIBLE = frozenset(
    {
        "tick_label_overlaps",
        "tick_label_crowding",
        "artists_outside_axes",
        "artists_outside_figure",
        "axis_label_title_overlap",
        "colorbar_overlap",
        "point_annotation_overlaps",
        "artist_overlaps",
        "legend_internal_overlaps",
        "marker_marker_overlaps",
        "text_axis_edge_proximity",
        "legend_marker_consistency",
        "label_offset_consistency",
        "font_size_token_drift",
        "journal_compliance",
    }
)
SCRIPT_OUTPUT_TAIL_LINES = 40


def _geometry_stub(reason: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    stub: dict[str, Any] = {
        "schema_version": GEOMETRY_DIAGNOSTICS_SCHEMA_VERSION,
        "passed": None,
        "checks": [],
        "warnings": [reason],
    }
    if data is not None:
        stub["data"] = data
    return stub

def _read_geometry_sidecar(job_root: Path) -> dict[str, Any]:
    sidecar = job_root / "geometry_diagnostics.json"
    try:
        text = sidecar.read_text(encoding="utf-8")
    except OSError:
        return _geometry_stub(
            "geometry_diagnostics_unavailable: no sidecar emitted",
            data={"reason": "no_sidecar"},
        )
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return _geometry_stub(
            "geometry_diagnostics_unavailable: unreadable sidecar",
            data={"reason": "no_sidecar"},
        )
    if not isinstance(loaded, dict):
        return _geometry_stub(
            "geometry_diagnostics_unavailable: malformed sidecar",
            data={"reason": "no_sidecar"},
        )
    return loaded

def _geometry_warnings(diagnostics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    raw_warnings = diagnostics.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(warning) for warning in raw_warnings)
    raw_checks = diagnostics.get("checks")
    if isinstance(raw_checks, list):
        for check in raw_checks:
            if (
                isinstance(check, dict)
                and check.get("name") in _GEOMETRY_WARNING_ELIGIBLE
                and check.get("passed") is False
            ):
                detail = check.get("detail")
                if detail:
                    warnings.append(str(detail))
    return warnings

def _layout_report_from_geometry(
    diagnostics: dict[str, Any],
    *,
    failure_stage: str = "",
    script_output: list[str] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": LAYOUT_REPORT_SCHEMA_VERSION,
        "passed": diagnostics.get("passed") if isinstance(diagnostics, dict) else None,
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

    checks = diagnostics.get("checks") if isinstance(diagnostics, dict) else None
    if not isinstance(checks, list):
        return report

    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "")
        data = check.get("data") if isinstance(check.get("data"), dict) else {}
        if name in {"artist_overlaps", "legend_internal_overlaps", "marker_marker_overlaps"}:
            report["overlaps"].extend(_layout_overlap_items(name, data))
        elif name == "text_axis_edge_proximity":
            report["clipped"].extend(_layout_clipped_items(data))
        elif name == "label_offset_consistency":
            report["placement_consistency"].extend(_layout_placement_items(data))
        elif name == "font_size_token_drift":
            report["font_roles"] = _layout_font_roles(data, check)
        elif name == "legend_marker_consistency" and check.get("passed") is False:
            detail = check.get("detail")
            if detail:
                report["warnings"].append(str(detail))
        elif name == "journal_compliance" and check.get("passed") is False:
            detail = check.get("detail")
            if detail:
                report["warnings"].append(str(detail))
        elif (
            name in {"point_annotation_overlaps", "artists_outside_axes", "artists_outside_figure"}
            and check.get("passed") is False
        ):
            detail = check.get("detail")
            if detail:
                report["warnings"].append(str(detail))

    density = _layout_density(checks)
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
        "passed": bool(check.get("passed")),
        "token_sizes": data.get("token_sizes", []),
        "offenders": data.get("offenders", []),
        "role_size_counts": data.get("role_size_counts", {}),
        "warn": str(check.get("detail", "")) if check.get("passed") is False else "",
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
