"""Repeated-label offset consistency checks for geometry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from matplotlib.transforms import Bbox

from .geometry_primitives import GEOM_EPS_PX, _box_area, _extent

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


MarkerFootprintProvider = Callable[[Any, Any], list[tuple[str, Bbox]]]
PaintablePredicate = Callable[[Any], bool]


def _box_center(box: Bbox) -> tuple[float, float]:
    return (float((box.x0 + box.x1) / 2), float((box.y0 + box.y1) / 2))


def _nearest_marker_direction(
    ax: Axes,
    text: Any,
    renderer: Any,
    *,
    marker_footprint_box_entries: MarkerFootprintProvider,
) -> str | None:
    text_bb = _extent(text, renderer)
    if text_bb is None:
        return None
    tx, ty = _box_center(text_bb)
    marker_boxes = marker_footprint_box_entries(ax, ax.figure)
    if not marker_boxes:
        return None
    nearest_box = min(
        marker_boxes, key=lambda item: (tx - _box_center(item[1])[0]) ** 2 + (ty - _box_center(item[1])[1]) ** 2
    )[1]
    mx, my = _box_center(nearest_box)
    dx = tx - mx
    dy = ty - my
    if abs(dx) < GEOM_EPS_PX and abs(dy) < GEOM_EPS_PX:
        return "center"
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "above" if dy > 0 else "below"


def _label_offset_consistency(
    fig: Figure,
    data_axes: list[Axes],
    renderer: Any,
    *,
    marker_footprint_box_entries: MarkerFootprintProvider,
    is_paintable: PaintablePredicate,
    max_reported_pairs: int,
) -> dict[str, Any]:
    name = "label_offset_consistency"
    labels: dict[str, list[dict[str, Any]]] = {}
    for axis_index, ax in enumerate(data_axes):
        for text in ax.texts:
            if not text.get_text() or not is_paintable(text):
                continue
            direction = _nearest_marker_direction(
                ax,
                text,
                renderer,
                marker_footprint_box_entries=marker_footprint_box_entries,
            )
            if direction is None:
                continue
            labels.setdefault(text.get_text(), []).append({"axis_index": int(axis_index), "direction": direction})

    inconsistencies: list[dict[str, Any]] = []
    for label, placements in labels.items():
        if len(placements) < 2:
            continue
        directions = sorted({str(item["direction"]) for item in placements})
        if len(directions) <= 1:
            continue
        inconsistencies.append(
            {
                "label": label,
                "directions": directions,
                "placements": placements,
            }
        )
    if len(inconsistencies) > max_reported_pairs:
        inconsistencies = inconsistencies[:max_reported_pairs]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(inconsistencies) == 0,
        "detail": f"{len(inconsistencies)} repeated-label offset inconsistencies",
        "data": {
            "inconsistencies": inconsistencies,
            "inconsistencies_truncated": bool(truncated),
        },
    }


def _point_label_skips(ax: Axes, axis_index: int) -> dict[str, Any]:
    name = "point_label_skips"
    raw = getattr(ax, "_graph_hub_point_label_skips", None)
    if not isinstance(raw, dict):
        return {
            "name": name,
            "passed": True,
            "detail": f"0 skipped point labels (axis {axis_index})",
            "data": {"axis_index": int(axis_index), "skipped_labels": 0},
        }
    skipped = int(raw.get("skipped_labels", 0) or 0)
    reasons = raw.get("reasons")
    examples = raw.get("examples")
    return {
        "name": name,
        "passed": skipped == 0,
        "detail": f"{skipped} skipped point labels (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "total_labels": int(raw.get("total_labels", 0) or 0),
            "shown_labels": int(raw.get("shown_labels", 0) or 0),
            "skipped_labels": skipped,
            "reasons": reasons if isinstance(reasons, dict) else {},
            "examples": examples if isinstance(examples, list) else [],
        },
    }


def _text_axis_edge_proximity(
    ax: Axes,
    renderer: Any,
    axis_index: int,
    *,
    is_paintable: PaintablePredicate,
    threshold_px: float,
    max_reported_pairs: int,
) -> dict[str, Any]:
    name = "text_axis_edge_proximity"
    axes_bb = ax.get_window_extent(renderer)
    findings: list[dict[str, Any]] = []
    for text in ax.texts:
        if not text.get_text() or not is_paintable(text):
            continue
        bb = _extent(text, renderer)
        if bb is None or _box_area(bb) <= 0:
            continue
        distances = {
            "left": float(bb.x0 - axes_bb.x0),
            "right": float(axes_bb.x1 - bb.x1),
            "bottom": float(bb.y0 - axes_bb.y0),
            "top": float(axes_bb.y1 - bb.y1),
        }
        clipped_edges = [edge for edge, distance in distances.items() if distance < 0]
        near_edges = [
            edge
            for edge, distance in distances.items()
            if 0 <= distance <= threshold_px and edge not in clipped_edges
        ]
        if not clipped_edges and not near_edges:
            continue
        findings.append(
            {
                "axes": int(axis_index),
                "artist": f"text:{text.get_text()!r}",
                "edges": clipped_edges or near_edges,
                "clipped": bool(clipped_edges),
                "min_distance_px": round(min(distances.values()), 3),
            }
        )
    if len(findings) > max_reported_pairs:
        findings = findings[:max_reported_pairs]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(findings) == 0,
        "detail": f"{len(findings)} text artists clipped or near axes edge (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "findings": findings,
            "findings_truncated": bool(truncated),
            "threshold_px": float(threshold_px),
        },
    }
