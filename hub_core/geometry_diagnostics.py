"""
Objective render geometry diagnostics.

Pure matplotlib geometry measurement on a fully-drawn, still-open Figure.
No subjective scoring, no LLM critic — every reported number traces to an
artist extent in display/pixel space. Mirrors hub_core/figure_preflight.py:
a pure function that RAISES on programmer/input errors and NEVER raises on a
geometry finding.

Import constraint: matplotlib only. Nothing from themes/ or hub_core/
(themes/ already imports hub_core, so a back-import would form a cycle).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import numpy as np
from matplotlib.transforms import Bbox

from .geometry_marker_styles import _collection_marker_style as _collection_marker_style
from .geometry_marker_styles import _is_none_color as _is_none_color
from .geometry_marker_styles import _line_marker_style as _line_marker_style
from .geometry_marker_styles import _marker_style as _marker_style
from .geometry_marker_styles import _path_signature as _path_signature
from .geometry_marker_styles import _rgba_tuple as _rgba_tuple
from .geometry_marker_styles import _style_color as _style_color
from .geometry_marker_styles import _style_diff as _style_diff
from .geometry_primitives import GEOM_EPS_PX as GEOM_EPS_PX
from .geometry_primitives import _box_area as _box_area
from .geometry_primitives import _boxes_overlap as _boxes_overlap
from .geometry_primitives import _circle_overlap_fraction as _circle_overlap_fraction
from .geometry_primitives import _extent as _extent
from .geometry_primitives import _inter_area as _inter_area
from .geometry_primitives import _overlap_fraction as _overlap_fraction
from .geometry_primitives import _overlap_severity as _overlap_severity

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

SCHEMA_VERSION = "geometry_diagnostics/1"
ALPHA_EPS = 0.01
MAX_TEXT_ARTISTS = 200
TICK_CROWDING_WARN = 0.90
DATA_OUTSIDE_AXES_WARN = 0.01
LEGEND_OVERLAP_WARN = 0.05
COLORBAR_OVERLAP_WARN = 0.02
MARKER_MARKER_OVERLAP_WARN = 0.55
ARTIST_OVERLAP_WARN = 0.05
POINT_MARKER_OVERLAP_WARN = 0.10
TEXT_AXIS_EDGE_WARN_PX = 3.0
TEXT_OVERLAY_CONTRAST_WARN = 3.0

_CROWDING_NEAR_LOW = 0.85
_CROWDING_NEAR_HIGH = 0.95
_MAX_REPORTED_PAIRS = 50
_ERRORBAR_CAP_MARKERS = frozenset({"_", "|", 0, 1, 2, 3, 10, 11})

_WARNING_ELIGIBLE = frozenset(
    {
        "tick_label_overlaps",
        "tick_label_crowding",
        "artists_outside_axes",
        "artists_outside_figure",
        "axis_label_title_overlap",
        "figure_title_panel_title_overlap",
        "colorbar_overlap",
        "point_annotation_overlaps",
        "artist_overlaps",
        "legend_internal_overlaps",
        "marker_marker_overlaps",
        "text_axis_edge_proximity",
        "legend_marker_consistency",
        "label_offset_consistency",
        "point_label_skips",
        "annotation_overlay_contrast",
        "font_size_token_drift",
        "journal_compliance",
    }
)


def diagnose_figure_geometry(
    fig: Figure,
    data_axes: list[Axes],
    *,
    layout_locked: bool,
    font_token_sizes: list[float] | None = None,
    journal_compliance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure objective geometry facts on a fully-drawn, still-open Figure.

    Returns a pure JSON-value tree (no numpy scalars, no matplotlib objects):
        {"schema_version", "passed", "checks", "warnings"}
    where each check is {"name", "passed", "detail", "data"} and pairs are
    list[list[int]]. Raises TypeError/ValueError on bad input (no renderer
    obtainable, empty data_axes). NEVER raises for a geometry finding.
    """
    if not data_axes:
        raise ValueError("data_axes must contain at least one Axes.")

    renderer = _get_renderer(fig)

    checks: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        checks.append(_tick_label_overlaps(ax, renderer, axis_index))
        checks.append(_tick_label_crowding(ax, renderer, axis_index))
        checks.append(_artists_outside_axes(ax, renderer, axis_index))
        checks.append(_artists_outside_figure(ax, fig, renderer, axis_index, layout_locked))
        checks.append(_legend_data_collision(ax, renderer, axis_index))
        checks.append(_axis_label_title_overlap(ax, renderer, axis_index))
        checks.append(_colorbar_overlap(ax, fig, renderer, axis_index))
        checks.append(_blank_area_ratio(ax, renderer, axis_index))
        checks.append(_point_annotation_overlaps(ax, renderer, axis_index))
        checks.append(_artist_overlaps(ax, renderer, axis_index))
        checks.append(_legend_internal_overlaps(ax, renderer, axis_index))
        checks.append(_marker_marker_overlaps(ax, renderer, axis_index))
        checks.append(_text_axis_edge_proximity(ax, renderer, axis_index))
        checks.append(_legend_marker_consistency(ax, axis_index))
        checks.append(_point_label_skips(ax, axis_index))
        checks.append(_annotation_overlay_contrast(ax, renderer, axis_index))
    checks.append(_figure_title_panel_title_overlap(fig, data_axes, renderer))
    checks.append(_label_offset_consistency(fig, data_axes, renderer))
    checks.append(_font_size_token_drift(data_axes, font_token_sizes))
    if journal_compliance:
        checks.append(_journal_compliance(fig, data_axes, journal_compliance))

    # passed is None marks an informational skip (e.g. over-cap); never count it as a pass.
    evaluated = [c["passed"] for c in checks if c["name"] in _WARNING_ELIGIBLE and c["passed"] is not None]
    passed = None if not evaluated else all(evaluated)
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": None if passed is None else bool(passed),
        "checks": checks,
        "warnings": [],
    }


def _get_renderer(fig: Figure) -> Any:
    try:
        return fig.canvas.get_renderer()
    except (AttributeError, RuntimeError):
        fig.canvas.draw()
        try:
            return fig.canvas.get_renderer()
        except (AttributeError, RuntimeError) as exc:
            raise TypeError(f"No renderer obtainable for figure: {exc}") from exc


def _is_paintable(artist: Any) -> bool:
    if not artist.get_visible():
        return False
    alpha = artist.get_alpha()
    return alpha is None or alpha > ALPHA_EPS


def _visible_data_artists(ax: Axes) -> list[Any]:
    artists: list[Any] = []
    artists.extend(line for line in ax.get_lines() if _is_paintable(line))
    artists.extend(coll for coll in ax.collections if _is_paintable(coll))
    artists.extend(patch for patch in ax.patches if _is_paintable(patch))
    return artists


def _visible_tick_labels(labels: list[Any]) -> list[Any]:
    return [t for t in labels if t.get_text() and _is_paintable(t)]


def _truncate_pairs(pairs: list[list[int]]) -> tuple[list[list[int]], bool]:
    if len(pairs) > _MAX_REPORTED_PAIRS:
        return pairs[:_MAX_REPORTED_PAIRS], True
    return pairs, False


def _tick_label_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "tick_label_overlaps"
    x_pairs = _axis_tick_overlaps(_visible_tick_labels(list(ax.get_xticklabels())), renderer, "x")
    y_pairs = _axis_tick_overlaps(_visible_tick_labels(list(ax.get_yticklabels())), renderer, "y")
    if x_pairs is None or y_pairs is None:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: text artist count exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index)},
        }
    x_pairs, x_truncated = _truncate_pairs(x_pairs)
    y_pairs, y_truncated = _truncate_pairs(y_pairs)
    count = len(x_pairs) + len(y_pairs)
    return {
        "name": name,
        "passed": count == 0,
        "detail": (f"x: {len(x_pairs)} overlapping pairs; y: {len(y_pairs)} overlapping pairs (axis {axis_index})"),
        "data": {
            "axis_index": int(axis_index),
            "x_overlap_pairs": x_pairs,
            "y_overlap_pairs": y_pairs,
            "x_overlap_pairs_truncated": bool(x_truncated),
            "y_overlap_pairs_truncated": bool(y_truncated),
        },
    }


def _axis_tick_overlaps(labels: list[Any], renderer: Any, axis: str) -> list[list[int]] | None:
    if len(labels) > MAX_TEXT_ARTISTS:
        return None
    measured: list[tuple[int, float, float, Bbox]] = []
    for index, label in enumerate(labels):
        bb = _extent(label, renderer)
        if bb is None:
            continue
        center = (bb.x0 + bb.x1) / 2 if axis == "x" else (bb.y0 + bb.y1) / 2
        proj_len = bb.width if axis == "x" else bb.height
        measured.append((index, float(center), float(proj_len), bb))
    measured.sort(key=lambda item: item[1])
    pairs: list[list[int]] = []
    for first, second in zip(measured, measured[1:]):
        index_a, center_a, proj_a, box_a = first
        index_b, center_b, proj_b, box_b = second
        rotation_a = labels[index_a].get_rotation() % 180 != 0
        rotation_b = labels[index_b].get_rotation() % 180 != 0
        if rotation_a or rotation_b:
            gap = (center_b - center_a) - (proj_a + proj_b) / 2
            overlaps = gap < 0
        else:
            overlaps = _boxes_overlap(box_a, box_b)
        if overlaps:
            pairs.append([int(index_a), int(index_b)])
    return pairs


def _tick_label_crowding(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "tick_label_crowding"
    x_ratio = _axis_crowding(_visible_tick_labels(list(ax.get_xticklabels())), ax, renderer, "x")
    y_ratio = _axis_crowding(_visible_tick_labels(list(ax.get_yticklabels())), ax, renderer, "y")
    if x_ratio is None or y_ratio is None:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: text artist count exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index)},
        }
    worst = max(x_ratio, y_ratio)
    near_boundary = bool(_CROWDING_NEAR_LOW <= worst <= _CROWDING_NEAR_HIGH)
    return {
        "name": name,
        "passed": bool(worst <= TICK_CROWDING_WARN),
        "detail": f"x occupancy {x_ratio:.2f}; y occupancy {y_ratio:.2f} (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "x_crowding_ratio": float(x_ratio),
            "y_crowding_ratio": float(y_ratio),
            "near_boundary": bool(near_boundary),
        },
    }


def _axis_crowding(labels: list[Any], ax: Axes, renderer: Any, axis: str) -> float | None:
    if len(labels) > MAX_TEXT_ARTISTS:
        return None
    axes_bb = ax.get_window_extent(renderer)
    span = axes_bb.width if axis == "x" else axes_bb.height
    if span <= 0:
        return 0.0
    intervals: list[tuple[float, float]] = []
    for label in labels:
        bb = _extent(label, renderer)
        if bb is None:
            continue
        start = float(bb.x0 if axis == "x" else bb.y0)
        end = float(bb.x1 if axis == "x" else bb.y1)
        intervals.append((start, end))
    if not intervals:
        return 0.0
    intervals.sort()
    covered = 0.0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        covered += max(0.0, current_end - current_start)
        current_start, current_end = start, end
    covered += max(0.0, current_end - current_start)
    return float(covered / span)


def _visible_data_lim(ax: Axes) -> Bbox | None:
    """Value-space extent over VISIBLE data artists only (round1-#14).

    Raw ax.dataLim retains hidden/cleared artists' extents; rebuilding from visible
    artists keeps a set_visible(False) artist from inflating the autoscale-miss check.
    """
    boxes: list[Bbox] = []
    for line in ax.get_lines():
        if not _is_paintable(line):
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
        if not _is_paintable(collection) or not hasattr(collection, "get_datalim"):
            continue
        try:
            bb = collection.get_datalim(ax.transData)
        except (ValueError, RuntimeError):
            continue
        if bb is not None and np.all(np.isfinite(bb.get_points())):
            boxes.append(bb)
    for patch in ax.patches:
        if not _is_paintable(patch):
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


def _artists_outside_axes(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "artists_outside_axes"
    visible = _visible_data_artists(ax)
    data_lim = _visible_data_lim(ax) if visible else None
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
        "passed": bool(outside_frac <= DATA_OUTSIDE_AXES_WARN),
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


def _chrome_artists(ax: Axes) -> list[Any]:
    artists: list[Any] = []
    for artist in (ax.xaxis.label, ax.yaxis.label, ax.title):
        if artist is not None and artist.get_text() and _is_paintable(artist):
            artists.append(artist)
    artists.extend(_visible_tick_labels(list(ax.get_xticklabels())))
    artists.extend(_visible_tick_labels(list(ax.get_yticklabels())))
    legend = ax.get_legend()
    if legend is not None and _is_paintable(legend):
        artists.append(legend)
    return artists


def _artists_outside_figure(
    ax: Axes,
    fig: Figure,
    renderer: Any,
    axis_index: int,
    layout_locked: bool,
) -> dict[str, Any]:
    name = "artists_outside_figure"
    fig_bb = fig.bbox
    overflow_count = 0
    for artist in _chrome_artists(ax):
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


def _data_artist_display_bbox(artist: Any, ax: Axes, renderer: Any) -> Bbox | None:
    # Scatter/path collections return a non-finite get_window_extent; fall back to the
    # transformed offset extent so legend/blank metrics see the marker cloud.
    bb = _extent(artist, renderer)
    if bb is not None and bb.width > 0 and bb.height > 0:
        return bb
    get_offsets = getattr(artist, "get_offsets", None)
    if get_offsets is None:
        return None
    offsets = get_offsets()
    if offsets is None or len(offsets) == 0:
        return None
    display = ax.transData.transform(np.asarray(offsets))
    if not np.all(np.isfinite(display)):
        return None
    xs = display[:, 0]
    ys = display[:, 1]
    return Bbox.from_extents(float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))


def _data_union_bbox(ax: Axes, renderer: Any) -> Bbox | None:
    boxes: list[Bbox] = []
    for artist in _visible_data_artists(ax):
        bb = _data_artist_display_bbox(artist, ax, renderer)
        if bb is not None:
            boxes.append(bb)
    if not boxes:
        return None
    return Bbox.union(boxes)


def _legend_data_collision(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "legend_data_collision"
    legend = ax.get_legend()
    if legend is None or not _is_paintable(legend):
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no legend",
            "data": {"axis_index": int(axis_index)},
        }
    legend_bb = _extent(legend, renderer)
    data_union = _data_union_bbox(ax, renderer)
    overlap_frac = 0.0
    if legend_bb is not None and data_union is not None:
        legend_area = _box_area(legend_bb)
        if legend_area > 0:
            overlap_frac = float(_inter_area(legend_bb, data_union) / legend_area)
    return {
        "name": name,
        "passed": True,
        "detail": "informational; bbox-union approximation, not ink-accurate",
        "data": {"axis_index": int(axis_index), "overlap_frac": overlap_frac},
    }


def _legend_internal_items(ax: Axes, renderer: Any) -> list[tuple[str, str, Bbox]]:
    legend = ax.get_legend()
    if legend is None or not _is_paintable(legend):
        return []
    items: list[tuple[str, str, Bbox]] = []
    handles = getattr(legend, "legend_handles", getattr(legend, "legendHandles", []))
    for index, handle in enumerate(handles):
        if not _is_paintable(handle):
            continue
        bb = _extent(handle, renderer)
        if bb is not None and _box_area(bb) > 0:
            items.append(("handle", f"legend_handle:{index}", bb))
    for index, text in enumerate(legend.get_texts()):
        if not text.get_text() or not _is_paintable(text):
            continue
        bb = _extent(text, renderer)
        if bb is not None and _box_area(bb) > 0:
            items.append(("text", f"legend_text:{text.get_text()!r}", bb))
    return items


def _legend_internal_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "legend_internal_overlaps"
    items = _legend_internal_items(ax, renderer)
    if not items:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no legend internals",
            "data": {"axis_index": int(axis_index)},
        }

    overlaps: list[dict[str, Any]] = []
    for index_a in range(len(items)):
        kind_a, label_a, box_a = items[index_a]
        for index_b in range(index_a + 1, len(items)):
            kind_b, label_b, box_b = items[index_b]
            overlap = _overlap_fraction(box_a, box_b)
            if overlap <= 0:
                continue
            pair_kind = "handle_text" if {kind_a, kind_b} == {"handle", "text"} else f"{kind_a}_{kind_b}"
            overlaps.append(
                {
                    "axes": int(axis_index),
                    "a": label_a,
                    "b": label_b,
                    "kind": pair_kind,
                    "iou": round(overlap, 4),
                    "severity": _overlap_severity(overlap),
                }
            )
    if len(overlaps) > _MAX_REPORTED_PAIRS:
        overlaps = overlaps[:_MAX_REPORTED_PAIRS]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(overlaps) == 0,
        "detail": f"{len(overlaps)} legend-internal overlaps (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "overlaps": overlaps,
            "overlaps_truncated": bool(truncated),
        },
    }


def _axis_label_title_overlap(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "axis_label_title_overlap"
    artists = [
        artist
        for artist in (ax.xaxis.label, ax.yaxis.label, ax.title)
        if artist is not None and artist.get_text() and _is_paintable(artist)
    ]
    boxes = [(artist, _extent(artist, renderer)) for artist in artists]
    boxes = [(artist, bb) for artist, bb in boxes if bb is not None]
    overlaps = 0
    for index_a in range(len(boxes)):
        for index_b in range(index_a + 1, len(boxes)):
            if _boxes_overlap(boxes[index_a][1], boxes[index_b][1]):
                overlaps += 1
    return {
        "name": name,
        "passed": overlaps == 0,
        "detail": f"{overlaps} label/title overlaps (axis {axis_index})",
        "data": {"axis_index": int(axis_index), "overlap_count": int(overlaps)},
    }


def _figure_title_panel_title_overlap(fig: Figure, data_axes: list[Axes], renderer: Any) -> dict[str, Any]:
    name = "figure_title_panel_title_overlap"
    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is None or not suptitle.get_text() or not _is_paintable(suptitle):
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no figure title",
            "data": {"overlap_count": 0, "overlaps": []},
        }
    suptitle_bb = _extent(suptitle, renderer)
    if suptitle_bb is None:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: figure title extent unavailable",
            "data": {"overlap_count": 0, "overlaps": []},
        }

    overlaps: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        title = getattr(ax, "title", None)
        if title is None or not title.get_text() or not _is_paintable(title):
            continue
        title_bb = _extent(title, renderer)
        if title_bb is None:
            continue
        overlap = _overlap_fraction(suptitle_bb, title_bb)
        if overlap > 0:
            overlaps.append(
                {
                    "axis_index": int(axis_index),
                    "figure_title": suptitle.get_text(),
                    "panel_title": title.get_text(),
                    "overlap_fraction": round(float(overlap), 4),
                    "severity": _overlap_severity(overlap),
                }
            )
    return {
        "name": name,
        "passed": len(overlaps) == 0,
        "detail": f"{len(overlaps)} figure-title/panel-title overlaps",
        "data": {"overlap_count": int(len(overlaps)), "overlaps": overlaps},
    }


def _colorbar_overlap(ax: Axes, fig: Figure, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "colorbar_overlap"
    colorbars = [cax for cax in fig.axes if getattr(cax, "_graph_hub_role", None) == "colorbar" and cax.get_visible()]
    if not colorbars:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no tagged colorbar",
            "data": {"axis_index": int(axis_index)},
        }
    panel_bb = ax.get_window_extent(renderer)
    panel_area = _box_area(panel_bb)
    worst = 0.0
    for cax in colorbars:
        cbar_bb = cax.get_window_extent(renderer)
        cbar_area = _box_area(cbar_bb)
        denom = min(panel_area, cbar_area)
        if denom > 0:
            worst = max(worst, _inter_area(panel_bb, cbar_bb) / denom)
    worst = float(worst)
    return {
        "name": name,
        "passed": bool(worst <= COLORBAR_OVERLAP_WARN),
        "detail": f"colorbar overlaps panel by {worst * 100:.1f}% (axis {axis_index})",
        "data": {"axis_index": int(axis_index), "overlap_frac": worst},
    }


def _blank_area_ratio(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "blank_area_ratio"
    axes_bb = ax.get_window_extent(renderer)
    axes_area = _box_area(axes_bb)
    boxes: list[Bbox] = []
    data_boxes = (_data_artist_display_bbox(artist, ax, renderer) for artist in _visible_data_artists(ax))
    chrome_boxes = (_extent(artist, renderer) for artist in _chrome_artists(ax))
    for bb in (*data_boxes, *chrome_boxes):
        if bb is None:
            continue
        clipped = Bbox.intersection(bb, axes_bb)
        if clipped is not None and clipped.width > 0 and clipped.height > 0:
            boxes.append(clipped)
    if axes_area <= 0 or not boxes:
        blank_ratio = 1.0
    else:
        union = Bbox.union(boxes)
        clipped_union = Bbox.intersection(union, axes_bb)
        covered = _box_area(clipped_union) if clipped_union is not None else 0.0
        blank_ratio = float(max(0.0, 1 - covered / axes_area))
    return {
        "name": name,
        "passed": True,
        "detail": "informational; bbox-union over-approximates coverage",
        "data": {"axis_index": int(axis_index), "blank_ratio": blank_ratio},
    }


def _marker_footprint_entries(ax: Axes, fig: Figure) -> list[tuple[str, Bbox, tuple[float, float], float]]:
    """Return marker footprints as display-space circles plus bounding boxes.

    Adjacent dense-series markers can share a few pixels while remaining
    legible, so marker-marker warnings use circle area overlap rather than bbox
    contact. The 0.55 default threshold corresponds to equal-size centers being
    closer than about one third of the marker diameter: severe pile-up, not
    ordinary dense plotting.
    """
    px_per_point = fig.dpi / 72.0
    entries: list[tuple[str, Bbox, tuple[float, float], float]] = []
    for collection_index, collection in enumerate(ax.collections):
        if not _is_paintable(collection) or not hasattr(collection, "get_sizes"):
            continue  # scatter-style PathCollection only; QuadMesh/pcolormesh has no markers
        offsets = collection.get_offsets()
        if offsets is None or len(offsets) == 0:
            continue
        sizes = collection.get_sizes()
        display = ax.transData.transform(np.asarray(offsets))
        if not np.all(np.isfinite(display)):
            continue
        for point_index, (x_px, y_px) in enumerate(display):
            if not _collection_marker_is_paintable(collection, point_index):
                continue
            if sizes is not None and len(sizes) > 0:
                size = float(sizes[min(point_index, len(sizes) - 1)])
                # scatter `s` is marker area in pt^2, so diameter = 2*sqrt(s/pi)
                diameter_pt = 2.0 * float(np.sqrt(size / np.pi))
            else:
                diameter_pt = 6.0
            radius_px = max(GEOM_EPS_PX, diameter_pt / 2 * px_per_point)
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
        if not _line_marker_is_paintable(line):
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
        radius_px = max(GEOM_EPS_PX, float(line.get_markersize()) / 2 * px_per_point)
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


def _marker_footprint_box_entries(ax: Axes, fig: Figure) -> list[tuple[str, Bbox]]:
    return [(label, box) for label, box, _center, _radius in _marker_footprint_entries(ax, fig)]


def _alpha_from_rgba_value(value: Any) -> float | None:
    rgba = _rgba_tuple(value)
    if rgba is None:
        return None
    return float(rgba[3])


def _sequence_entry_alpha(values: Any, index: int) -> float | None:
    if values is None or len(values) == 0:
        return None
    value = values[min(index, len(values) - 1)]
    return _alpha_from_rgba_value(value)


def _collection_marker_is_paintable(collection: Any, point_index: int) -> bool:
    face_alpha = _sequence_entry_alpha(collection.get_facecolors(), point_index)
    edge_alpha = _sequence_entry_alpha(collection.get_edgecolors(), point_index)
    if face_alpha is None and edge_alpha is None:
        return True
    return max(face_alpha or 0.0, edge_alpha or 0.0) > ALPHA_EPS


def _line_marker_is_paintable(line: Any) -> bool:
    marker = line.get_marker()
    if marker in {None, "", "None", "none", " "}:
        return False
    if marker in _ERRORBAR_CAP_MARKERS:
        return False
    if float(line.get_markersize()) <= 0:
        return False
    face_alpha = _alpha_from_rgba_value(line.get_markerfacecolor())
    edge_alpha = _alpha_from_rgba_value(line.get_markeredgecolor())
    if face_alpha is None and edge_alpha is None:
        return True
    return max(face_alpha or 0.0, edge_alpha or 0.0) > ALPHA_EPS


def _marker_marker_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "marker_marker_overlaps"
    markers = _marker_footprint_entries(ax, ax.figure)
    if len(markers) > MAX_TEXT_ARTISTS:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: marker count {len(markers)} exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index)},
        }
    overlaps: list[dict[str, Any]] = []
    total_pairs = len(markers) * (len(markers) - 1) // 2
    for index_a in range(len(markers)):
        label_a, _box_a, center_a, radius_a = markers[index_a]
        for index_b in range(index_a + 1, len(markers)):
            label_b, _box_b, center_b, radius_b = markers[index_b]
            overlap = _circle_overlap_fraction(center_a, radius_a, center_b, radius_b)
            if overlap <= MARKER_MARKER_OVERLAP_WARN:
                continue
            overlaps.append(
                {
                    "axes": int(axis_index),
                    "a": label_a,
                    "b": label_b,
                    "iou": round(overlap, 4),
                    "severity": _overlap_severity(overlap),
                }
            )
    if len(overlaps) > _MAX_REPORTED_PAIRS:
        overlaps = overlaps[:_MAX_REPORTED_PAIRS]
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
            "threshold": float(MARKER_MARKER_OVERLAP_WARN),
            "overlap_fraction": float(len(overlaps) / total_pairs) if total_pairs else 0.0,
            "total_pairs": int(total_pairs),
        },
    }


def _text_axis_edge_proximity(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "text_axis_edge_proximity"
    axes_bb = ax.get_window_extent(renderer)
    findings: list[dict[str, Any]] = []
    for text in ax.texts:
        if not text.get_text() or not _is_paintable(text):
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
            if 0 <= distance <= TEXT_AXIS_EDGE_WARN_PX and edge not in clipped_edges
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
    if len(findings) > _MAX_REPORTED_PAIRS:
        findings = findings[:_MAX_REPORTED_PAIRS]
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
            "threshold_px": float(TEXT_AXIS_EDGE_WARN_PX),
        },
    }


def _legend_marker_consistency(ax: Axes, axis_index: int) -> dict[str, Any]:
    name = "legend_marker_consistency"
    legend = ax.get_legend()
    if legend is None or not _is_paintable(legend):
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no legend",
            "data": {"axis_index": int(axis_index), "mismatches": []},
        }

    data_by_label: dict[str, list[Any]] = {}
    for artist in [*ax.get_lines(), *ax.collections]:
        if not _is_paintable(artist):
            continue
        label = str(artist.get_label() or "")
        if not label or label.startswith("_"):
            continue
        data_by_label.setdefault(label, []).append(artist)

    handles = getattr(legend, "legend_handles", getattr(legend, "legendHandles", []))
    texts = [text.get_text() for text in legend.get_texts()]
    mismatches: list[dict[str, Any]] = []
    for index, label in enumerate(texts):
        if index >= len(handles) or label not in data_by_label:
            continue
        legend_style = _marker_style(handles[index])
        if legend_style is None:
            continue
        for data_index, data_artist in enumerate(data_by_label[label]):
            data_style = _marker_style(data_artist)
            if data_style is None:
                continue
            diff = _style_diff(legend_style, data_style)
            if not diff:
                continue
            mismatches.append(
                {
                    "axes": int(axis_index),
                    "legend_label": str(label),
                    "entity": f"{label}:{data_index}",
                    "legend_style": legend_style,
                    "data_style": data_style,
                    "diff": diff,
                    "severity": "medium",
                }
            )

    if len(mismatches) > _MAX_REPORTED_PAIRS:
        mismatches = mismatches[:_MAX_REPORTED_PAIRS]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(mismatches) == 0,
        "detail": f"{len(mismatches)} legend marker style mismatches (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "mismatches": mismatches,
            "mismatches_truncated": bool(truncated),
        },
    }


def _marker_footprint_boxes(ax: Axes, fig: Figure, renderer: Any) -> Bbox | None:
    boxes = [box for _label, box in _marker_footprint_box_entries(ax, fig)]
    if not boxes:
        return None
    return Bbox.union(boxes)


def _box_center(box: Bbox) -> tuple[float, float]:
    return (float((box.x0 + box.x1) / 2), float((box.y0 + box.y1) / 2))


def _box_vector_away(source: Bbox, obstacle: Bbox, *, step_px: float, seed: Any = None) -> tuple[float, float]:
    sx, sy = _box_center(source)
    ox, oy = _box_center(obstacle)
    inter = Bbox.intersection(source, obstacle)
    if inter is not None and inter.width > 0 and inter.height > 0:
        if sx < ox:
            clear_x = obstacle.x0 - source.x1 - step_px
        else:
            clear_x = obstacle.x1 - source.x0 + step_px
        if sy < oy:
            clear_y = obstacle.y0 - source.y1 - step_px
        else:
            clear_y = obstacle.y1 - source.y0 + step_px
        if abs(abs(clear_x) - abs(clear_y)) > GEOM_EPS_PX:
            if abs(clear_x) < abs(clear_y):
                return (float(clear_x), 0.0)
            return (0.0, float(clear_y))

    vx = sx - ox
    vy = sy - oy
    norm = float(np.hypot(vx, vy))
    if norm <= GEOM_EPS_PX:
        angle_seed = (
            seed if seed is not None else (round(sx, 3), round(sy, 3), round(ox, 3), round(oy, 3), round(step_px, 3))
        )
        # Deterministic seed: Python's hash() varies with PYTHONHASHSEED across runs.
        seed_int = int(hashlib.sha256(repr(angle_seed).encode()).hexdigest(), 16)
        angle = (seed_int % 360) * np.pi / 180.0
        return (float(np.cos(angle) * step_px), float(np.sin(angle) * step_px))
    return (float(vx / norm * step_px), float(vy / norm * step_px))


def _point_annotation_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "point_annotation_overlaps"
    from matplotlib.text import Annotation

    annotations = [a for a in ax.texts if isinstance(a, Annotation) and _is_paintable(a)]
    if len(annotations) > MAX_TEXT_ARTISTS:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: annotation count {len(annotations)} exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index)},
        }
    measured: list[tuple[int, float, Bbox]] = []
    for index, annotation in enumerate(annotations):
        bb = _extent(annotation, renderer)
        if bb is None:
            continue
        center = (bb.x0 + bb.x1) / 2
        measured.append((index, float(center), bb))

    pairs: list[list[int]] = []
    measured.sort(key=lambda item: item[1])
    for first, second in zip(measured, measured[1:]):
        if _boxes_overlap(first[2], second[2]):
            pairs.append(sorted((int(first[0]), int(second[0]))))

    marker_hits: list[int] = []
    marker_entries = _marker_footprint_box_entries(ax, ax.figure)
    if marker_entries:
        for index, _center, bb in measured:
            if any(
                _overlap_fraction(bb, marker_box) > POINT_MARKER_OVERLAP_WARN
                for _label, marker_box in marker_entries
            ):
                marker_hits.append(int(index))

    count = len(pairs) + len(marker_hits)
    pairs, truncated = _truncate_pairs(pairs)
    return {
        "name": name,
        "passed": count == 0,
        "detail": f"{len(pairs)} annotation overlaps, {len(marker_hits)} marker hits (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "overlap_pairs": pairs,
            "overlap_pairs_truncated": bool(truncated),
            "marker_hits": marker_hits,
        },
    }


def _artist_label(artist: Any, fallback: str) -> str:
    from matplotlib.legend import Legend
    from matplotlib.text import Annotation, Text

    if isinstance(artist, Legend):
        return "legend"
    if isinstance(artist, Annotation):
        text = artist.get_text() or fallback
        return f"annotation:{text!r}"
    if isinstance(artist, Text):
        text = artist.get_text() or fallback
        if artist.axes is not None and artist is artist.axes.title:
            return f"title:{text!r}"
        return f"text:{text!r}"
    return fallback


def _artist_overlap_candidate_items(ax: Axes, renderer: Any) -> list[tuple[str, Bbox, Any]]:
    from matplotlib.text import Text

    candidates: list[tuple[str, Bbox, Any]] = []
    seen: set[int] = set()

    def add_artist(artist: Any, fallback: str) -> None:
        if artist is None or id(artist) in seen or not _is_paintable(artist):
            return
        if isinstance(artist, Text) and not artist.get_text():
            return
        bb = _extent(artist, renderer)
        if bb is None or _box_area(bb) <= 0:
            return
        seen.add(id(artist))
        candidates.append((_artist_label(artist, fallback), bb, artist))

    legend = ax.get_legend()
    if legend is not None:
        add_artist(legend, "legend")
    add_artist(ax.title, "title")
    for index, text in enumerate(ax.texts):
        add_artist(text, f"text:{index}")
    for index, line in enumerate(ax.get_lines()):
        if not _is_paintable(line):
            continue
        for segment_index, segment_box in enumerate(_line_overlap_boxes(ax, line)):
            if _box_area(segment_box) > 0:
                candidates.append((f"line:{index}[{segment_index}]", segment_box, None))
    for index, patch in enumerate(ax.patches):
        if getattr(patch, "_graph_hub_leader_patch", False):
            continue
        add_artist(patch, f"patch:{index}")

    for label, marker_box in _marker_footprint_box_entries(ax, ax.figure):
        if _box_area(marker_box) > 0:
            candidates.append((label, marker_box, None))
    return candidates


def _line_overlap_boxes(ax: Axes, line: Any) -> list[Bbox]:
    xy = np.asarray(line.get_xydata(), dtype=float)
    if xy.size == 0:
        return []
    finite = xy[np.all(np.isfinite(xy), axis=1)]
    if len(finite) < 2:
        return []
    display = ax.transData.transform(finite)
    if not np.all(np.isfinite(display)):
        return []
    half_width = max(GEOM_EPS_PX, float(line.get_linewidth()) / 2)
    boxes: list[Bbox] = []
    for start, end in zip(display, display[1:]):
        x0 = min(float(start[0]), float(end[0])) - half_width
        x1 = max(float(start[0]), float(end[0])) + half_width
        y0 = min(float(start[1]), float(end[1])) - half_width
        y1 = max(float(start[1]), float(end[1])) + half_width
        boxes.append(Bbox.from_extents(x0, y0, x1, y1))
    return boxes


def _artist_overlap_candidates(ax: Axes, renderer: Any) -> list[tuple[str, Bbox]]:
    return [(label, box) for label, box, _artist in _artist_overlap_candidate_items(ax, renderer)]


def _artist_candidate_kind(label: str) -> str:
    if label.startswith("marker:"):
        return "data"
    if label.startswith("line:"):
        return "data"
    if label.startswith("patch:"):
        return "data"
    if label == "legend":
        return "legend"
    return "chrome"


def _is_reportable_artist_overlap(
    ax: Axes,
    label_a: str,
    box_a: Bbox,
    artist_a: Any,
    label_b: str,
    box_b: Bbox,
    artist_b: Any,
) -> bool:
    if _is_leader_connected_text_marker_pair(ax, label_a, box_a, artist_a, label_b, box_b, artist_b):
        return False
    kind_a = _artist_candidate_kind(label_a)
    kind_b = _artist_candidate_kind(label_b)
    # Data-data contacts are normal in dense plots and error bars. Dedicated
    # checks handle severe marker pile-ups; generic artist overlaps stay focused
    # on label/chrome/legend collisions that readers actually experience.
    if kind_a == "data" and kind_b == "data":
        return False
    return True


def _artist_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "artist_overlaps"
    candidates = _artist_overlap_candidate_items(ax, renderer)

    pair_candidates: list[tuple[int, int]] = []
    for index_a in range(len(candidates)):
        label_a, box_a, artist_a = candidates[index_a]
        for index_b in range(index_a + 1, len(candidates)):
            label_b, box_b, artist_b = candidates[index_b]
            if _is_reportable_artist_overlap(ax, label_a, box_a, artist_a, label_b, box_b, artist_b):
                pair_candidates.append((index_a, index_b))

    if len(pair_candidates) > MAX_TEXT_ARTISTS:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: reportable artist pair count {len(pair_candidates)} exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index), "candidate_pairs": int(len(pair_candidates))},
        }

    overlaps: list[dict[str, Any]] = []
    for index_a, index_b in pair_candidates:
        label_a, box_a, _artist_a = candidates[index_a]
        label_b, box_b, _artist_b = candidates[index_b]
        iou = _overlap_fraction(box_a, box_b)
        if iou <= ARTIST_OVERLAP_WARN:
            continue
        overlaps.append(
            {
                "axes": int(axis_index),
                "a": label_a,
                "b": label_b,
                "iou": round(iou, 4),
                "severity": _overlap_severity(iou),
            }
        )

    truncated = False
    if len(overlaps) > _MAX_REPORTED_PAIRS:
        overlaps = overlaps[:_MAX_REPORTED_PAIRS]
        truncated = True

    return {
        "name": name,
        "passed": len(overlaps) == 0,
        "detail": f"{len(overlaps)} artist overlaps (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "overlaps": overlaps,
            "overlaps_truncated": bool(truncated),
            "threshold": float(ARTIST_OVERLAP_WARN),
            "candidate_pairs": int(len(pair_candidates)),
        },
    }


def _is_leader_connected_text_marker_pair(
    ax: Axes,
    label_a: str,
    box_a: Bbox,
    artist_a: Any,
    label_b: str,
    box_b: Bbox,
    artist_b: Any,
) -> bool:
    from matplotlib.text import Text

    if isinstance(artist_a, Text) and label_b.startswith("marker:"):
        return _leader_target_inside_marker_box(ax, artist_a, box_a, box_b)
    if isinstance(artist_b, Text) and label_a.startswith("marker:"):
        return _leader_target_inside_marker_box(ax, artist_b, box_b, box_a)
    return False


def _leader_target_inside_marker_box(ax: Axes, text: Any, text_box: Bbox, marker_box: Bbox) -> bool:
    if not getattr(text, "_graph_hub_leader_connected", False):
        return False
    target = getattr(text, "_graph_hub_leader_target_data", None)
    if not isinstance(target, (tuple, list)) or len(target) != 2:
        return False
    try:
        target_px = ax.transData.transform((float(target[0]), float(target[1])))
    except (TypeError, ValueError):
        return False
    if not (marker_box.x0 <= target_px[0] <= marker_box.x1 and marker_box.y0 <= target_px[1] <= marker_box.y1):
        return False
    if text_box.x0 <= target_px[0] <= text_box.x1 and text_box.y0 <= target_px[1] <= text_box.y1:
        return False
    text_center_x, text_center_y = _box_center(text_box)
    distance_px = ((text_center_x - target_px[0]) ** 2 + (text_center_y - target_px[1]) ** 2) ** 0.5
    return bool(distance_px > GEOM_EPS_PX * 4)


def _nearest_marker_direction(ax: Axes, text: Any, renderer: Any) -> str | None:
    text_bb = _extent(text, renderer)
    if text_bb is None:
        return None
    tx, ty = _box_center(text_bb)
    marker_boxes = _marker_footprint_box_entries(ax, ax.figure)
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


def _label_offset_consistency(fig: Figure, data_axes: list[Axes], renderer: Any) -> dict[str, Any]:
    name = "label_offset_consistency"
    labels: dict[str, list[dict[str, Any]]] = {}
    for axis_index, ax in enumerate(data_axes):
        for text in ax.texts:
            if not text.get_text() or not _is_paintable(text):
                continue
            direction = _nearest_marker_direction(ax, text, renderer)
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
    if len(inconsistencies) > _MAX_REPORTED_PAIRS:
        inconsistencies = inconsistencies[:_MAX_REPORTED_PAIRS]
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


def _annotation_overlay_contrast(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "annotation_overlay_contrast"
    texts = [
        text
        for text in ax.texts
        if text.get_text() and _is_paintable(text) and getattr(text, "_graph_hub_annotation_text_role", "")
    ]
    overlays = _overlay_contrast_items(ax, renderer)
    if not texts or not overlays:
        return {
            "name": name,
            "passed": True,
            "detail": f"0 low-contrast annotation/overlay pairs (axis {axis_index})",
            "data": {"axis_index": int(axis_index), "pairs": []},
        }
    offenders: list[dict[str, Any]] = []
    for text_index, text in enumerate(texts):
        text_bb = _extent(text, renderer)
        if text_bb is None:
            continue
        text_rgb = _artist_rgb(text.get_color(), fallback=(0.0, 0.0, 0.0))
        for overlay_index, overlay in enumerate(overlays):
            if not _boxes_overlap(text_bb, overlay["bbox"]):
                continue
            contrast = _contrast_ratio(text_rgb, overlay["rgb"])
            if contrast < TEXT_OVERLAY_CONTRAST_WARN:
                offenders.append(
                    {
                        "text_index": int(text_index),
                        "text": text.get_text(),
                        "overlay_index": int(overlay_index),
                        "overlay_role": overlay["role"],
                        "overlay_label": overlay["label"],
                        "contrast_ratio": round(float(contrast), 3),
                        "threshold": TEXT_OVERLAY_CONTRAST_WARN,
                    }
                )
    if len(offenders) > _MAX_REPORTED_PAIRS:
        offenders = offenders[:_MAX_REPORTED_PAIRS]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(offenders) == 0,
        "detail": f"{len(offenders)} low-contrast annotation/overlay pairs (axis {axis_index})",
        "data": {"axis_index": int(axis_index), "pairs": offenders, "pairs_truncated": bool(truncated)},
    }


def _overlay_contrast_items(ax: Axes, renderer: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for artist in [*ax.collections, *ax.patches]:
        if not getattr(artist, "_graph_hub_overlay_role", "") or not _is_paintable(artist):
            continue
        bb = _extent(artist, renderer)
        if bb is None:
            continue
        items.append(
            {
                "bbox": bb,
                "rgb": _overlay_artist_rgb(artist),
                "role": str(getattr(artist, "_graph_hub_overlay_role", "overlay")),
                "label": str(getattr(artist, "_graph_hub_overlay_label", "")),
            }
        )
    return items


def _overlay_artist_rgb(artist: Any) -> tuple[float, float, float]:
    facecolors = getattr(artist, "get_facecolors", lambda: [])()
    if len(facecolors):
        rgba = facecolors[0]
        alpha = float(rgba[3]) if len(rgba) > 3 else 1.0
        return _composite_rgb(tuple(float(v) for v in rgba[:3]), alpha)
    facecolor = getattr(artist, "get_facecolor", lambda: None)()
    if isinstance(facecolor, (list, tuple)) and len(facecolor) and isinstance(facecolor[0], (list, tuple)):
        facecolor = facecolor[0]
    return _artist_rgb(facecolor, fallback=(1.0, 1.0, 1.0), composite=True)


def _artist_rgb(
    color: Any, *, fallback: tuple[float, float, float], composite: bool = False
) -> tuple[float, float, float]:
    try:
        from matplotlib.colors import to_rgba

        rgba = to_rgba(color)
    except (TypeError, ValueError):
        return fallback
    rgb = tuple(float(v) for v in rgba[:3])
    if composite:
        return _composite_rgb(rgb, float(rgba[3]))
    return rgb


def _composite_rgb(rgb: tuple[float, float, float], alpha: float) -> tuple[float, float, float]:
    alpha = max(0.0, min(1.0, float(alpha)))
    return tuple(float(channel * alpha + (1.0 - alpha)) for channel in rgb)


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        value = max(0.0, min(1.0, float(value)))
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(value) for value in rgb)
    return float(0.2126 * red + 0.7152 * green + 0.0722 * blue)


def _contrast_ratio(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    first_lum = _relative_luminance(first)
    second_lum = _relative_luminance(second)
    lighter = max(first_lum, second_lum)
    darker = min(first_lum, second_lum)
    return float((lighter + 0.05) / (darker + 0.05))


def _default_font_token_sizes(data_axes: list[Axes]) -> list[float]:
    sizes: set[float] = set()
    for ax in data_axes:
        for artist in (ax.xaxis.label, ax.yaxis.label):
            if artist is not None and _is_paintable(artist):
                sizes.add(round(float(artist.get_fontsize()), 2))
        for text in [
            *_visible_tick_labels(list(ax.get_xticklabels())),
            *_visible_tick_labels(list(ax.get_yticklabels())),
        ]:
            sizes.add(round(float(text.get_fontsize()), 2))
        legend = ax.get_legend()
        if legend is not None and _is_paintable(legend):
            for text in legend.get_texts():
                if text.get_text() and _is_paintable(text):
                    sizes.add(round(float(text.get_fontsize()), 2))
    return sorted(sizes)


def _font_size_matches_token(size: float, token_sizes: list[float], *, tolerance: float = 0.05) -> bool:
    return any(abs(size - token) <= tolerance for token in token_sizes)


def _font_size_token_drift(data_axes: list[Axes], font_token_sizes: list[float] | None) -> dict[str, Any]:
    name = "font_size_token_drift"
    token_sizes = sorted({round(float(size), 2) for size in (font_token_sizes or []) if float(size) > 0})
    if not token_sizes:
        token_sizes = _default_font_token_sizes(data_axes)
    if not token_sizes:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no font token sizes",
            "data": {"token_sizes": []},
        }

    offenders: list[dict[str, Any]] = []
    role_sizes: dict[str, set[float]] = {"text": set(), "axis": set(), "legend": set(), "tick": set()}
    for axis_index, ax in enumerate(data_axes):
        for text in ax.texts:
            if not text.get_text() or not _is_paintable(text):
                continue
            size = round(float(text.get_fontsize()), 2)
            role_sizes["text"].add(size)
            if not _font_size_matches_token(size, token_sizes):
                offenders.append({"axes": int(axis_index), "role": "text", "text": text.get_text(), "fontsize": size})
        for role, artist in (("axis", ax.xaxis.label), ("axis", ax.yaxis.label)):
            if artist is None or not artist.get_text() or not _is_paintable(artist):
                continue
            size = round(float(artist.get_fontsize()), 2)
            role_sizes[role].add(size)
            if not _font_size_matches_token(size, token_sizes):
                offenders.append({"axes": int(axis_index), "role": role, "text": artist.get_text(), "fontsize": size})
        for text in [
            *_visible_tick_labels(list(ax.get_xticklabels())),
            *_visible_tick_labels(list(ax.get_yticklabels())),
        ]:
            size = round(float(text.get_fontsize()), 2)
            role_sizes["tick"].add(size)
            if not _font_size_matches_token(size, token_sizes):
                offenders.append({"axes": int(axis_index), "role": "tick", "text": text.get_text(), "fontsize": size})
        legend = ax.get_legend()
        if legend is not None and _is_paintable(legend):
            for text in legend.get_texts():
                if not text.get_text() or not _is_paintable(text):
                    continue
                size = round(float(text.get_fontsize()), 2)
                role_sizes["legend"].add(size)
                if not _font_size_matches_token(size, token_sizes):
                    offenders.append(
                        {"axes": int(axis_index), "role": "legend", "text": text.get_text(), "fontsize": size}
                    )

    role_size_counts = {role: len(sizes) for role, sizes in role_sizes.items() if sizes}
    divergent_roles = sorted(role for role, count in role_size_counts.items() if count > 1)
    if len(offenders) > _MAX_REPORTED_PAIRS:
        offenders = offenders[:_MAX_REPORTED_PAIRS]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(offenders) == 0 and not divergent_roles,
        "detail": (
            f"{len(offenders)} text artists use non-token font sizes; divergent roles: "
            f"{', '.join(divergent_roles) or 'none'}"
        ),
        "data": {
            "token_sizes": token_sizes,
            "offenders": offenders,
            "offenders_truncated": bool(truncated),
            "role_size_counts": role_size_counts,
            "divergent_roles": divergent_roles,
        },
    }


def _journal_compliance(fig: Figure, data_axes: list[Axes], compliance: dict[str, Any]) -> dict[str, Any]:
    name = "journal_compliance"
    target_format = str(compliance.get("target_format", "unknown"))
    min_font = float(compliance["min_font_size_pt"])
    min_line = float(compliance["min_line_width_pt"])
    max_height = float(compliance["max_figure_height_mm"])
    figure_height_mm = float(fig.get_size_inches()[1] * 25.4)

    font_offenders = _journal_font_offenders(data_axes, min_font)
    line_offenders = _journal_line_offenders(data_axes, min_line)
    height_offender = figure_height_mm > max_height + 0.01
    passed = not font_offenders and not line_offenders and not height_offender
    return {
        "name": name,
        "passed": bool(passed),
        "detail": (
            f"{target_format}: {len(font_offenders)} font offenders below {min_font:g} pt; "
            f"{len(line_offenders)} line offenders below {min_line:g} pt; "
            f"height {figure_height_mm:.2f}/{max_height:g} mm"
        ),
        "data": {
            "target_format": target_format,
            "min_font_size_pt": min_font,
            "min_line_width_pt": min_line,
            "max_figure_height_mm": max_height,
            "figure_height_mm": figure_height_mm,
            "font_offenders": font_offenders,
            "line_offenders": line_offenders,
            "height_offender": bool(height_offender),
        },
    }


def _journal_font_offenders(data_axes: list[Axes], min_font: float) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        text_artists = [
            ("title", ax.title),
            ("axis", ax.xaxis.label),
            ("axis", ax.yaxis.label),
            *(("tick", text) for text in _visible_tick_labels(list(ax.get_xticklabels()))),
            *(("tick", text) for text in _visible_tick_labels(list(ax.get_yticklabels()))),
            *(("text", text) for text in ax.texts if text.get_text() and _is_paintable(text)),
        ]
        legend = ax.get_legend()
        if legend is not None and _is_paintable(legend):
            text_artists.extend(
                ("legend", text) for text in legend.get_texts() if text.get_text() and _is_paintable(text)
            )
            title = legend.get_title()
            if title is not None and title.get_text() and _is_paintable(title):
                text_artists.append(("legend", title))
        for role, text in text_artists:
            if text is None or not text.get_text() or not _is_paintable(text):
                continue
            size = round(float(text.get_fontsize()), 2)
            if size + 0.01 < min_font:
                offenders.append({"axes": int(axis_index), "role": role, "text": text.get_text(), "fontsize": size})
                if len(offenders) >= _MAX_REPORTED_PAIRS:
                    return offenders
    return offenders


def _journal_line_offenders(data_axes: list[Axes], min_line: float) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        for index, line in enumerate(ax.get_lines()):
            if _is_paintable(line):
                _append_linewidth_offender(offenders, axis_index, "line", index, line.get_linewidth(), min_line)
        for index, coll in enumerate(ax.collections):
            if _is_paintable(coll):
                for linewidth in _line_width_values(coll.get_linewidths()):
                    _append_linewidth_offender(offenders, axis_index, "collection", index, linewidth, min_line)
        for index, patch in enumerate(ax.patches):
            if _is_paintable(patch):
                _append_linewidth_offender(offenders, axis_index, "patch", index, patch.get_linewidth(), min_line)
        for spine_name, spine in ax.spines.items():
            if _is_paintable(spine):
                _append_linewidth_offender(
                    offenders,
                    axis_index,
                    f"spine:{spine_name}",
                    0,
                    spine.get_linewidth(),
                    min_line,
                )
        if len(offenders) >= _MAX_REPORTED_PAIRS:
            return offenders[:_MAX_REPORTED_PAIRS]
    return offenders


def _line_width_values(value: Any) -> list[float]:
    values = np.asarray(value, dtype=float).ravel()
    return [float(item) for item in values if np.isfinite(item)]


def _append_linewidth_offender(
    offenders: list[dict[str, Any]],
    axis_index: int,
    role: str,
    index: int,
    linewidth: Any,
    min_line: float,
) -> None:
    value = float(linewidth)
    if value <= 0:
        return
    rounded = round(value, 3)
    if rounded + 0.001 < min_line:
        offenders.append({"axes": int(axis_index), "role": role, "index": int(index), "linewidth": rounded})
