"""Figure and axes boundary checks for geometry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from matplotlib.transforms import Bbox

from .geometry_primitives import GEOM_EPS_PX, _box_area, _extent, _inter_area

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


PaintablePredicate = Callable[[Any], bool]


def _visible_data_artists(ax: Axes, *, is_paintable: PaintablePredicate) -> list[Any]:
    artists: list[Any] = []
    artists.extend(line for line in ax.get_lines() if is_paintable(line))
    artists.extend(coll for coll in ax.collections if is_paintable(coll))
    artists.extend(patch for patch in ax.patches if is_paintable(patch))
    return artists


def _visible_data_lim(ax: Axes, *, is_paintable: PaintablePredicate) -> Bbox | None:
    """Value-space extent over visible data artists only."""
    boxes: list[Bbox] = []
    for line in ax.get_lines():
        if not is_paintable(line):
            continue
        xy = line.get_xydata()
        if xy is None or len(xy) == 0:
            continue
        finite = xy[np.all(np.isfinite(xy), axis=1)]
        if len(finite) == 0:
            continue
        boxes.append(
            Bbox.from_extents(
                float(finite[:, 0].min()),
                float(finite[:, 1].min()),
                float(finite[:, 0].max()),
                float(finite[:, 1].max()),
            )
        )
    for collection in ax.collections:
        if not is_paintable(collection) or not hasattr(collection, "get_datalim"):
            continue
        try:
            bb = collection.get_datalim(ax.transData)
        except (ValueError, RuntimeError):
            continue
        if bb is not None and np.all(np.isfinite(bb.get_points())):
            boxes.append(bb)
    for patch in ax.patches:
        if not is_paintable(patch):
            continue
        try:
            bb = patch.get_extents().transformed(ax.transData.inverted())
        except (ValueError, RuntimeError):
            continue
        if bb is not None and np.all(np.isfinite(bb.get_points())):
            boxes.append(bb)
    if not boxes:
        return None
    return Bbox.union(boxes)


def _artists_outside_axes(
    ax: Axes,
    renderer: Any,
    axis_index: int,
    *,
    is_paintable: PaintablePredicate,
    data_outside_axes_warn: float,
) -> dict[str, Any]:
    name = "artists_outside_axes"
    visible = _visible_data_artists(ax, is_paintable=is_paintable)
    data_lim = _visible_data_lim(ax, is_paintable=is_paintable) if visible else None
    if data_lim is None or not np.all(np.isfinite(data_lim.get_points())):
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no data artists",
            "data": {"axis_index": int(axis_index)},
        }
    data_bb = ax.transData.transform_bbox(data_lim)
    axes_bb = ax.get_window_extent(renderer)
    data_area = _box_area(data_bb)
    if data_area <= 0:
        outside_frac = _degenerate_outside_fraction(data_bb, axes_bb)
    else:
        outside_frac = float(1 - _inter_area(data_bb, axes_bb) / data_area)
    if ax.get_autoscalex_on() is False or ax.get_autoscaley_on() is False:
        return {
            "name": name,
            "passed": None,
            "detail": f"informational: explicit limits crop data by {outside_frac * 100:.1f}% (axis {axis_index})",
            "data": {"axis_index": int(axis_index), "outside_fraction": outside_frac},
        }
    return {
        "name": name,
        "passed": bool(outside_frac <= data_outside_axes_warn),
        "detail": f"data extent exceeds axes by {outside_frac * 100:.1f}% (axis {axis_index})",
        "data": {"axis_index": int(axis_index), "outside_fraction": outside_frac},
    }


def _overlap_fraction_1d(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    length = max(0.0, end_a - start_a)
    if length <= 0:
        return 0.0
    overlap = max(0.0, min(end_a, end_b) - max(start_a, start_b))
    return float(overlap / length)


def _degenerate_outside_fraction(data_bb: Bbox, axes_bb: Bbox) -> float:
    width = float(abs(data_bb.width))
    height = float(abs(data_bb.height))
    if width <= GEOM_EPS_PX and height <= GEOM_EPS_PX:
        inside = (
            axes_bb.x0 - GEOM_EPS_PX <= data_bb.x0 <= axes_bb.x1 + GEOM_EPS_PX
            and axes_bb.y0 - GEOM_EPS_PX <= data_bb.y0 <= axes_bb.y1 + GEOM_EPS_PX
        )
        return 0.0 if inside else 1.0
    if width <= GEOM_EPS_PX:
        x_inside = axes_bb.x0 - GEOM_EPS_PX <= data_bb.x0 <= axes_bb.x1 + GEOM_EPS_PX
        if not x_inside:
            return 1.0
        inside_fraction = _overlap_fraction_1d(data_bb.y0, data_bb.y1, axes_bb.y0, axes_bb.y1)
        return float(1.0 - inside_fraction)
    if height <= GEOM_EPS_PX:
        y_inside = axes_bb.y0 - GEOM_EPS_PX <= data_bb.y0 <= axes_bb.y1 + GEOM_EPS_PX
        if not y_inside:
            return 1.0
        inside_fraction = _overlap_fraction_1d(data_bb.x0, data_bb.x1, axes_bb.x0, axes_bb.x1)
        return float(1.0 - inside_fraction)
    return 1.0


def _chrome_artists(ax: Axes, *, is_paintable: PaintablePredicate) -> list[Any]:
    artists: list[Any] = []
    for artist in (ax.xaxis.label, ax.yaxis.label, ax.title):
        if artist is not None and artist.get_text() and is_paintable(artist):
            artists.append(artist)
    artists.extend(label for label in ax.get_xticklabels() if label.get_text() and is_paintable(label))
    artists.extend(label for label in ax.get_yticklabels() if label.get_text() and is_paintable(label))
    legend = ax.get_legend()
    if legend is not None and is_paintable(legend):
        artists.append(legend)
    return artists


def _artists_outside_figure(
    ax: Axes,
    fig: Figure,
    renderer: Any,
    axis_index: int,
    layout_locked: bool,
    *,
    is_paintable: PaintablePredicate,
) -> dict[str, Any]:
    name = "artists_outside_figure"
    fig_bb = fig.bbox
    overflow_count = 0
    for artist in _chrome_artists(ax, is_paintable=is_paintable):
        bb = _extent(artist, renderer)
        if bb is None:
            continue
        if (
            bb.x0 < fig_bb.x0 - GEOM_EPS_PX
            or bb.y0 < fig_bb.y0 - GEOM_EPS_PX
            or bb.x1 > fig_bb.x1 + GEOM_EPS_PX
            or bb.y1 > fig_bb.y1 + GEOM_EPS_PX
        ):
            overflow_count += 1
    if layout_locked:
        passed = overflow_count == 0
        detail = f"{overflow_count} chrome artists exceed figure bounds (locked layout, axis {axis_index})"
    else:
        passed = True
        detail = "figure overflow absorbed by tight bbox"
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
        "data": {
            "axis_index": int(axis_index),
            "overflow_count": int(overflow_count),
            "layout_locked": bool(layout_locked),
        },
    }
