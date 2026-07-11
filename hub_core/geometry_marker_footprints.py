"""Display-space marker footprint and overlap measurements.

The compatibility façade remains in :mod:`hub_core.geometry_diagnostics` so
existing private imports and monkeypatch surfaces continue to work.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.transforms import Bbox


def marker_footprint_entries(
    ax,
    fig,
    *,
    is_paintable,
    collection_marker_is_paintable,
    line_marker_is_paintable,
    geom_eps_px,
) -> list[tuple[str, Bbox, tuple[float, float], float]]:
    """Return paintable marker footprints as display-space circles and boxes."""
    px_per_point = fig.dpi / 72.0
    entries: list[tuple[str, Bbox, tuple[float, float], float]] = []
    for collection_index, collection in enumerate(ax.collections):
        if not is_paintable(collection) or not hasattr(collection, "get_sizes"):
            continue
        offsets = collection.get_offsets()
        if offsets is None or len(offsets) == 0:
            continue
        sizes = collection.get_sizes()
        display = ax.transData.transform(np.asarray(offsets))
        if not np.all(np.isfinite(display)):
            continue
        for point_index, (x_px, y_px) in enumerate(display):
            if not collection_marker_is_paintable(collection, point_index):
                continue
            if sizes is not None and len(sizes) > 0:
                size = float(sizes[min(point_index, len(sizes) - 1)])
                diameter_pt = 2.0 * float(np.sqrt(size / np.pi))
            else:
                diameter_pt = 6.0
            radius_px = max(geom_eps_px, diameter_pt / 2 * px_per_point)
            entries.append(
                (
                    f"marker:collection{collection_index}[{point_index}]",
                    Bbox.from_extents(
                        float(x_px) - radius_px,
                        float(y_px) - radius_px,
                        float(x_px) + radius_px,
                        float(y_px) + radius_px,
                    ),
                    (float(x_px), float(y_px)),
                    float(radius_px),
                )
            )
    for line_index, line in enumerate(ax.get_lines()):
        if not line_marker_is_paintable(line):
            continue
        xy = np.asarray(line.get_xydata(), dtype=float)
        if xy.size == 0:
            continue
        finite = xy[np.all(np.isfinite(xy), axis=1)]
        if len(finite) == 0:
            continue
        display = ax.transData.transform(finite)
        if not np.all(np.isfinite(display)):
            continue
        radius_px = max(geom_eps_px, float(line.get_markersize()) / 2 * px_per_point)
        for point_index, (x_px, y_px) in enumerate(display):
            entries.append(
                (
                    f"marker:line{line_index}[{point_index}]",
                    Bbox.from_extents(
                        float(x_px) - radius_px,
                        float(y_px) - radius_px,
                        float(x_px) + radius_px,
                        float(y_px) + radius_px,
                    ),
                    (float(x_px), float(y_px)),
                    float(radius_px),
                )
            )
    return entries


def alpha_from_rgba_value(value: Any, *, rgba_tuple) -> float | None:
    rgba = rgba_tuple(value)
    if rgba is None:
        return None
    return float(rgba[3])


def sequence_entry_alpha(values: Any, index: int, *, alpha_from_rgba_value) -> float | None:
    if values is None or len(values) == 0:
        return None
    value = values[min(index, len(values) - 1)]
    return alpha_from_rgba_value(value)


def collection_marker_is_paintable(
    collection: Any,
    point_index: int,
    *,
    sequence_entry_alpha,
    alpha_eps,
) -> bool:
    face_alpha = sequence_entry_alpha(collection.get_facecolors(), point_index)
    edge_alpha = sequence_entry_alpha(collection.get_edgecolors(), point_index)
    if face_alpha is None and edge_alpha is None:
        return True
    return max(face_alpha or 0.0, edge_alpha or 0.0) > alpha_eps


def line_marker_is_paintable(
    line: Any,
    *,
    alpha_from_rgba_value,
    alpha_eps,
    errorbar_cap_markers,
) -> bool:
    marker = line.get_marker()
    if marker in {None, "", "None", "none", " "}:
        return False
    if marker in errorbar_cap_markers:
        return False
    if float(line.get_markersize()) <= 0:
        return False
    face_alpha = alpha_from_rgba_value(line.get_markerfacecolor())
    edge_alpha = alpha_from_rgba_value(line.get_markeredgecolor())
    if face_alpha is None and edge_alpha is None:
        return True
    return max(face_alpha or 0.0, edge_alpha or 0.0) > alpha_eps


def marker_marker_overlaps(
    ax,
    renderer,
    axis_index: int,
    *,
    marker_footprint_entries,
    max_text_artists,
    marker_marker_overlap_warn,
    circle_overlap_fraction,
    overlap_severity,
    max_reported_pairs,
) -> dict[str, Any]:
    """Report only severe circle-overlap pairs among paintable markers."""
    del renderer
    name = "marker_marker_overlaps"
    markers = marker_footprint_entries(ax, ax.figure)
    if len(markers) > max_text_artists:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: marker count {len(markers)} exceeds cap {max_text_artists}",
            "data": {"axis_index": int(axis_index)},
        }
    overlaps: list[dict[str, Any]] = []
    total_pairs = len(markers) * (len(markers) - 1) // 2
    for index_a in range(len(markers)):
        label_a, _box_a, center_a, radius_a = markers[index_a]
        for index_b in range(index_a + 1, len(markers)):
            label_b, _box_b, center_b, radius_b = markers[index_b]
            overlap = circle_overlap_fraction(center_a, radius_a, center_b, radius_b)
            if overlap <= marker_marker_overlap_warn:
                continue
            overlaps.append(
                {
                    "axes": int(axis_index),
                    "a": label_a,
                    "b": label_b,
                    "iou": round(overlap, 4),
                    "severity": overlap_severity(overlap),
                }
            )
    if len(overlaps) > max_reported_pairs:
        overlaps = overlaps[:max_reported_pairs]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(overlaps) == 0,
        "detail": f"{len(overlaps)} severe marker-marker overlaps (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "overlaps": overlaps,
            "overlaps_truncated": bool(truncated),
            "threshold": float(marker_marker_overlap_warn),
            "overlap_fraction": float(len(overlaps) / total_pairs) if total_pairs else 0.0,
            "total_pairs": int(total_pairs),
        },
    }
