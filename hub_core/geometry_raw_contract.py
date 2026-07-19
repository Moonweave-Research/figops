"""Frozen raw geometry contract and legacy compatibility projection."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

RAW_GEOMETRY_SCHEMA_VERSION = "geometry_diagnostics/2"
LEGACY_GEOMETRY_SCHEMA_VERSION = "geometry_diagnostics/1"

_TOP_LEVEL_FIELDS = frozenset({"schema_version", "measurements", "warnings"})
_MEASUREMENT_FIELDS = frozenset(
    {"metric_id", "availability", "value", "unit", "scope", "reason"}
)
_POLICY_FIELDS = frozenset(
    {
        "advisory",
        "aggregate",
        "aggregated",
        "aggregation",
        "blocked",
        "compliant",
        "divergent_roles",
        "fail",
        "failed",
        "font_offenders",
        "hard",
        "height_offender",
        "line_offenders",
        "near_boundary",
        "offender",
        "offenders",
        "offenders_truncated",
        "outcome",
        "pass",
        "passed",
        "policy",
        "policy_id",
        "policy_version",
        "severity",
        "threshold",
        "verdict",
        "violation",
        "violations",
    }
)
_POLICY_KEY_TOKENS = frozenset(
    {
        "advisory",
        "aggregate",
        "aggregated",
        "aggregation",
        "blocked",
        "compliant",
        "fail",
        "failed",
        "hard",
        "limit",
        "max",
        "maximum",
        "min",
        "minimum",
        "offender",
        "offenders",
        "outcome",
        "pass",
        "passed",
        "policy",
        "severity",
        "threshold",
        "verdict",
        "violation",
        "violations",
    }
)


class RawGeometryContractError(ValueError):
    """Raised when geometry evidence violates the frozen raw contract."""


def _normalized_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def _is_policy_field(key: object) -> bool:
    normalized = _normalized_key(key)
    tokens = set(normalized.split("_"))
    return normalized in _POLICY_FIELDS or bool(tokens & _POLICY_KEY_TOKENS)


def _contract_error(path: str, message: str) -> RawGeometryContractError:
    return RawGeometryContractError(f"{path}: {message}")


def _json_fact(value: Any, path: str) -> Any:
    """Return a JSON fact, rejecting policy fields and non-finite/custom values."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _contract_error(path, "numeric facts must be finite")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            if not isinstance(raw_key, str) or not raw_key:
                raise _contract_error(path, "fact object keys must be non-empty strings")
            if _is_policy_field(raw_key):
                raise _contract_error(f"{path}.{raw_key}", "policy-owned field is forbidden")
            result[raw_key] = _json_fact(child, f"{path}.{raw_key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_fact(child, f"{path}[{index}]") for index, child in enumerate(value)]
    raise _contract_error(path, f"unsupported fact type {type(value).__name__}")


def _project_raw_fact(value: Any) -> Any:
    """Project trusted legacy check data into facts before strict validation."""
    if isinstance(value, Mapping):
        return {
            str(key): _project_raw_fact(item)
            for key, item in value.items()
            if not _is_policy_field(key)
        }
    if isinstance(value, (list, tuple)):
        return [_project_raw_fact(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def threshold_neutral_geometry_measurements(
    data_axes: list[Any],
    renderer: Any,
    *,
    is_paintable: Callable[[Any], bool],
    marker_footprint_box_entries: Callable[[Any, Any], list[tuple[str, Any]]],
    candidate_cap: int,
    reported_cap: int,
) -> list[dict[str, Any]]:
    """Measure bounded raw candidates without applying publication thresholds."""
    from .geometry_artist_overlaps import (
        _artist_overlap_candidate_items,
        _is_reportable_artist_overlap,
    )
    from .geometry_overlay_contrast import (
        _artist_rgb,
        _contrast_ratio,
        _overlay_contrast_items,
    )
    from .geometry_primitives import _box_area, _boxes_overlap, _extent, _overlap_fraction

    if candidate_cap <= 0 or reported_cap <= 0:
        raise ValueError("candidate_cap and reported_cap must be positive")
    measurements: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        axes_bb = ax.get_window_extent(renderer)
        edge_facts: list[dict[str, Any]] = []
        edge_texts = [text for text in ax.texts if text.get_text() and is_paintable(text)]
        for text in edge_texts[:candidate_cap]:
            bb = _extent(text, renderer)
            if bb is None or _box_area(bb) <= 0:
                continue
            if len(edge_facts) < reported_cap:
                edge_facts.append(
                    {
                        "artist": f"text:{text.get_text()!r}",
                        "distances_px": {
                            "left": round(float(bb.x0 - axes_bb.x0), 3),
                            "right": round(float(axes_bb.x1 - bb.x1), 3),
                            "bottom": round(float(bb.y0 - axes_bb.y0), 3),
                            "top": round(float(axes_bb.y1 - bb.y1), 3),
                        },
                    }
                )
        measurements.append(
            _available_measurement(
                "text_axis_edge_distances",
                axis_index,
                "px",
                {
                    "artist_count": len(edge_texts),
                    "evaluated_artist_count": min(len(edge_texts), candidate_cap),
                    "reported_artist_count": len(edge_facts),
                    "artists": edge_facts,
                    "artists_truncated": len(edge_texts) > len(edge_facts),
                },
            )
        )

        candidates = _artist_overlap_candidate_items(
            ax,
            renderer,
            is_paintable=is_paintable,
            marker_footprint_box_entries=marker_footprint_box_entries,
        )
        candidate_count = len(candidates)
        candidates = candidates[:candidate_cap]
        pair_facts: list[dict[str, Any]] = []
        pair_count = 0
        for index_a in range(len(candidates)):
            label_a, box_a, artist_a = candidates[index_a]
            for index_b in range(index_a + 1, len(candidates)):
                label_b, box_b, artist_b = candidates[index_b]
                if not _is_reportable_artist_overlap(
                    ax, label_a, box_a, artist_a, label_b, box_b, artist_b
                ):
                    continue
                pair_count += 1
                if len(pair_facts) < reported_cap:
                    pair_facts.append(
                        {
                            "a": label_a,
                            "b": label_b,
                            "iou": round(float(_overlap_fraction(box_a, box_b)), 6),
                        }
                    )
        measurements.append(
            _available_measurement(
                "artist_pair_iou",
                axis_index,
                "ratio",
                {
                    "candidate_count": candidate_count,
                    "evaluated_candidate_count": len(candidates),
                    "candidates_truncated": candidate_count > len(candidates),
                    "pair_count": pair_count,
                    "reported_pair_count": len(pair_facts),
                    "pairs": pair_facts,
                    "pairs_truncated": pair_count > len(pair_facts),
                },
            )
        )

        texts = [
            text
            for text in ax.texts
            if text.get_text()
            and is_paintable(text)
            and getattr(text, "_graph_hub_annotation_text_role", "")
        ]
        text_count = len(texts)
        texts = texts[:candidate_cap]
        overlays = _overlay_contrast_items(ax, renderer)
        overlay_count = len(overlays)
        overlays = overlays[:candidate_cap]
        contrast_facts: list[dict[str, Any]] = []
        contrast_count = 0
        for text_index, text in enumerate(texts):
            text_bb = _extent(text, renderer)
            if text_bb is None:
                continue
            text_rgb = _artist_rgb(text.get_color(), fallback=(0.0, 0.0, 0.0))
            for overlay_index, overlay in enumerate(overlays):
                if not _boxes_overlap(text_bb, overlay["bbox"]):
                    continue
                contrast_count += 1
                if len(contrast_facts) < reported_cap:
                    contrast_facts.append(
                        {
                            "text_index": text_index,
                            "text": text.get_text(),
                            "overlay_index": overlay_index,
                            "overlay_role": overlay["role"],
                            "overlay_label": overlay["label"],
                            "contrast_ratio": round(
                                float(_contrast_ratio(text_rgb, overlay["rgb"])), 6
                            ),
                        }
                    )
        measurements.append(
            _available_measurement(
                "annotation_overlay_contrast_ratios",
                axis_index,
                "ratio",
                {
                    "annotation_count": text_count,
                    "evaluated_annotation_count": len(texts),
                    "annotations_truncated": text_count > len(texts),
                    "overlay_count": overlay_count,
                    "evaluated_overlay_count": len(overlays),
                    "overlays_truncated": overlay_count > len(overlays),
                    "pair_count": contrast_count,
                    "reported_pair_count": len(contrast_facts),
                    "pairs": contrast_facts,
                    "pairs_truncated": contrast_count > len(contrast_facts),
                },
            )
        )
    return measurements


def _available_measurement(
    metric_id: str, axis_index: int, unit: str, value: dict[str, Any]
) -> dict[str, Any]:
    return {
        "metric_id": f"{metric_id}[axis={axis_index}]",
        "availability": "available",
        "unit": unit,
        "scope": f"axis={axis_index}",
        "value": value,
    }


def validate_raw_geometry(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the frozen public ``geometry_diagnostics/2`` shape."""
    if not isinstance(payload, Mapping):
        raise _contract_error("geometry_diagnostics", "payload must be an object")
    extra = sorted(set(payload) - _TOP_LEVEL_FIELDS)
    missing = sorted(_TOP_LEVEL_FIELDS - set(payload))
    if extra:
        raise _contract_error(f"geometry_diagnostics.{extra[0]}", "unknown field")
    if missing:
        raise _contract_error("geometry_diagnostics", f"missing field {missing[0]}")
    if payload.get("schema_version") != RAW_GEOMETRY_SCHEMA_VERSION:
        raise _contract_error("geometry_diagnostics.schema_version", "unsupported raw schema")

    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise _contract_error("geometry_diagnostics.warnings", "must be a list of strings")
    measurements = payload.get("measurements")
    if not isinstance(measurements, list):
        raise _contract_error("geometry_diagnostics.measurements", "must be a list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(measurements):
        path = f"geometry_diagnostics.measurements[{index}]"
        if not isinstance(raw, Mapping):
            raise _contract_error(path, "measurement must be an object")
        unknown = sorted(set(raw) - _MEASUREMENT_FIELDS)
        if unknown:
            raise _contract_error(f"{path}.{unknown[0]}", "unknown field")
        required = {"metric_id", "availability", "unit", "scope"}
        absent = sorted(required - set(raw))
        if absent:
            raise _contract_error(path, f"missing field {absent[0]}")

        metric_id = raw.get("metric_id")
        unit = raw.get("unit")
        scope = raw.get("scope")
        availability = raw.get("availability")
        if not isinstance(metric_id, str) or not metric_id.strip():
            raise _contract_error(f"{path}.metric_id", "must be a non-empty string")
        if metric_id in seen:
            raise _contract_error(f"{path}.metric_id", "must be unique")
        seen.add(metric_id)
        if not isinstance(unit, str) or not unit.strip():
            raise _contract_error(f"{path}.unit", "must be a non-empty string")
        if not isinstance(scope, str) or not scope.strip():
            raise _contract_error(f"{path}.scope", "must be a non-empty string")
        if availability not in {"available", "unavailable"}:
            raise _contract_error(f"{path}.availability", "must be available or unavailable")

        item = {
            "metric_id": metric_id,
            "availability": availability,
            "unit": unit,
            "scope": scope,
        }
        if availability == "available":
            if "value" not in raw or "reason" in raw:
                raise _contract_error(path, "available facts require value and forbid reason")
            item["value"] = _json_fact(raw["value"], f"{path}.value")
        else:
            reason = raw.get("reason")
            if "value" in raw or not isinstance(reason, str) or not reason.strip():
                raise _contract_error(path, "unavailable facts require reason and forbid value")
            item["reason"] = reason
        normalized.append(item)

    return {
        "schema_version": RAW_GEOMETRY_SCHEMA_VERSION,
        "measurements": normalized,
        "warnings": list(warnings),
    }


def raw_measurement(check: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Lift one policy-free legacy implementation into the raw /2 shape."""
    name = str(check.get("name") or f"geometry.{index}")
    data = check.get("data") if isinstance(check.get("data"), Mapping) else {}
    scope = "figure"
    if "axis_index" in data:
        scope = f"axis={int(data['axis_index'])}"
    metric_id = f"{name}[{scope}]" if scope != "figure" else name
    detail = str(check.get("detail") or "")
    # Legacy pass/fail/None is a policy outcome, not a computability signal.
    # Only an explicit producer skip makes an otherwise valid raw fact unavailable.
    unavailable = detail.lower().startswith("skipped:")
    measurement: dict[str, Any] = {
        "metric_id": metric_id,
        "availability": "unavailable" if unavailable else "available",
        "unit": "structured",
        "scope": scope,
    }
    if unavailable:
        measurement["reason"] = detail or "measurement unavailable"
    else:
        measurement["value"] = _json_fact(data, f"geometry.checks[{index}].data")
    return measurement


def _legacy_measurement(check: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Demote a trusted /1 check by removing its compatibility-only policy fields."""
    data = check.get("data") if isinstance(check.get("data"), Mapping) else {}
    return raw_measurement({**check, "data": _project_raw_fact(data)}, index)


def adapt_legacy_geometry(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert legacy /1 diagnostics at the compatibility boundary only."""
    if payload.get("schema_version") != LEGACY_GEOMETRY_SCHEMA_VERSION:
        raise _contract_error("geometry_diagnostics.schema_version", "unsupported legacy schema")
    checks = payload.get("checks")
    warnings = payload.get("warnings", [])
    if not isinstance(checks, list) or not all(isinstance(item, Mapping) for item in checks):
        raise _contract_error("geometry_diagnostics.checks", "must be a list of objects")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise _contract_error("geometry_diagnostics.warnings", "must be a list of strings")
    raw = {
        "schema_version": RAW_GEOMETRY_SCHEMA_VERSION,
        "measurements": [_legacy_measurement(check, index) for index, check in enumerate(checks)],
        "warnings": list(warnings),
    }
    return validate_raw_geometry(raw)


def normalize_geometry_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Accept frozen raw /2 or explicitly adapt the compatibility-only /1 shape."""
    if payload.get("schema_version") == RAW_GEOMETRY_SCHEMA_VERSION:
        return validate_raw_geometry(payload)
    if payload.get("schema_version") == LEGACY_GEOMETRY_SCHEMA_VERSION:
        return adapt_legacy_geometry(payload)
    raise _contract_error("geometry_diagnostics.schema_version", "unsupported schema")
