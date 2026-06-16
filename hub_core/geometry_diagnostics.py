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

from typing import TYPE_CHECKING, Any

import numpy as np
from matplotlib.transforms import Bbox

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

SCHEMA_VERSION = "geometry_diagnostics/1"
GEOM_EPS_PX = 1.0
ALPHA_EPS = 0.01
MAX_TEXT_ARTISTS = 200
TICK_CROWDING_WARN = 0.90
DATA_OUTSIDE_AXES_WARN = 0.01
LEGEND_OVERLAP_WARN = 0.05
COLORBAR_OVERLAP_WARN = 0.02
MARKER_MARKER_OVERLAP_WARN = 0.05
TEXT_AXIS_EDGE_WARN_PX = 3.0

_CROWDING_NEAR_LOW = 0.85
_CROWDING_NEAR_HIGH = 0.95
_MAX_REPORTED_PAIRS = 50

_WARNING_ELIGIBLE = frozenset(
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
    }
)


def diagnose_figure_geometry(
    fig: Figure,
    data_axes: list[Axes],
    *,
    layout_locked: bool,
    font_token_sizes: list[float] | None = None,
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
    checks.append(_label_offset_consistency(fig, data_axes, renderer))
    checks.append(_font_size_token_drift(data_axes, font_token_sizes))

    passed = all(c["passed"] for c in checks if c["name"] in _WARNING_ELIGIBLE)
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": bool(passed),
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


def _extent(artist: Any, renderer: Any) -> Bbox | None:
    try:
        bb = artist.get_window_extent(renderer)
    except (RuntimeError, ValueError):
        return None
    if bb is None or not np.all(np.isfinite(bb.get_points())):
        return None
    return bb


def _inter_area(box_a: Bbox, box_b: Bbox) -> float:
    inter = Bbox.intersection(box_a, box_b)
    if inter is None or inter.width <= 0 or inter.height <= 0:
        return 0.0
    area = inter.width * inter.height
    if area <= GEOM_EPS_PX**2:
        return 0.0
    return float(area)


def _boxes_overlap(box_a: Bbox, box_b: Bbox) -> bool:
    return _inter_area(box_a, box_b) > 0.0


def _box_area(box: Bbox) -> float:
    return float(abs(box.width) * abs(box.height))


def _overlap_fraction(box_a: Bbox, box_b: Bbox) -> float:
    denom = min(_box_area(box_a), _box_area(box_b))
    if denom <= 0:
        return 0.0
    return float(_inter_area(box_a, box_b) / denom)


def _overlap_severity(value: float) -> str:
    if value >= 0.50:
        return "high"
    if value >= 0.20:
        return "medium"
    if value > 0:
        return "low"
    return "none"


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
            "passed": True,
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
            "passed": True,
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
    total = 0.0
    for label in labels:
        bb = _extent(label, renderer)
        if bb is None:
            continue
        total += bb.width if axis == "x" else bb.height
    return float(total / span)


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
    if (
        data_lim is None
        or not np.all(np.isfinite(data_lim.get_points()))
        or data_lim.width <= 0
        or data_lim.height <= 0
    ):
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no data artists",
            "data": {"axis_index": int(axis_index)},
        }
    if ax.get_autoscalex_on() is False and ax.get_autoscaley_on() is False:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: explicit limits (intentional zoom/crop)",
            "data": {"axis_index": int(axis_index)},
        }
    data_bb = ax.transData.transform_bbox(data_lim)
    axes_bb = ax.get_window_extent(renderer)
    data_area = _box_area(data_bb)
    if data_area <= 0:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: degenerate data extent",
            "data": {"axis_index": int(axis_index)},
        }
    outside_frac = float(1 - _inter_area(data_bb, axes_bb) / data_area)
    return {
        "name": name,
        "passed": bool(outside_frac <= DATA_OUTSIDE_AXES_WARN),
        "detail": f"data extent exceeds axes by {outside_frac * 100:.1f}% (axis {axis_index})",
        "data": {"axis_index": int(axis_index), "outside_fraction": outside_frac},
    }


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


def _marker_footprint_box_entries(ax: Axes, fig: Figure) -> list[tuple[str, Bbox]]:
    px_per_point = fig.dpi / 72.0
    boxes: list[tuple[str, Bbox]] = []
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
            if sizes is not None and len(sizes) > 0:
                size = float(sizes[min(point_index, len(sizes) - 1)])
                diameter_pt = float(np.sqrt(size))
            else:
                diameter_pt = 6.0
            radius_px = max(GEOM_EPS_PX, diameter_pt / 2 * px_per_point)
            boxes.append(
                (
                    f"marker:collection{collection_index}[{point_index}]",
                    Bbox.from_extents(
                        float(x_px) - radius_px,
                        float(y_px) - radius_px,
                        float(x_px) + radius_px,
                        float(y_px) + radius_px,
                    ),
                )
            )
    return boxes


def _marker_marker_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "marker_marker_overlaps"
    markers = _marker_footprint_box_entries(ax, ax.figure)
    if len(markers) > MAX_TEXT_ARTISTS:
        return {
            "name": name,
            "passed": True,
            "detail": f"skipped: marker count {len(markers)} exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index)},
        }
    overlaps: list[dict[str, Any]] = []
    for index_a in range(len(markers)):
        label_a, box_a = markers[index_a]
        for index_b in range(index_a + 1, len(markers)):
            label_b, box_b = markers[index_b]
            overlap = _overlap_fraction(box_a, box_b)
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
        "detail": f"{len(overlaps)} marker-marker overlaps (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "overlaps": overlaps,
            "overlaps_truncated": bool(truncated),
            "threshold": float(MARKER_MARKER_OVERLAP_WARN),
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


def _is_none_color(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.lower() in {"none", "transparent"}:
        return True
    rgba = _rgba_tuple(value)
    return rgba is not None and rgba[3] <= ALPHA_EPS


def _rgba_tuple(value: Any) -> tuple[float, float, float, float] | None:
    from matplotlib.colors import to_rgba

    try:
        rgba = to_rgba(value)
    except (TypeError, ValueError):
        return None
    return tuple(round(float(channel), 4) for channel in rgba)


def _style_color(value: Any) -> str:
    if _is_none_color(value):
        return "none"
    rgba = _rgba_tuple(value)
    if rgba is None:
        return str(value)
    return f"rgba({rgba[0]:.4f},{rgba[1]:.4f},{rgba[2]:.4f},{rgba[3]:.4f})"


def _path_signature(path: Any) -> str:
    vertices = np.asarray(path.vertices, dtype=float)
    if vertices.size == 0 or not np.all(np.isfinite(vertices)):
        return "empty"
    centered = vertices - vertices.mean(axis=0)
    scale = float(np.max(np.abs(centered)))
    if scale > 0:
        centered = centered / scale
    return ";".join(f"{x:.3f},{y:.3f}" for x, y in np.round(centered, 3))


def _line_marker_style(artist: Any) -> dict[str, Any] | None:
    from matplotlib.markers import MarkerStyle

    marker = artist.get_marker()
    if marker in {None, "", "None", "none", " "}:
        return None
    try:
        marker_style = MarkerStyle(marker)
        marker_shape = _path_signature(marker_style.get_path().transformed(marker_style.get_transform()))
    except (TypeError, ValueError):
        marker_shape = str(marker)
    facecolor = artist.get_markerfacecolor()
    fill = not _is_none_color(facecolor) and artist.get_fillstyle() != "none"
    return {
        "marker": str(marker),
        "marker_shape": marker_shape,
        "facecolor": _style_color(facecolor),
        "edgecolor": _style_color(artist.get_markeredgecolor()),
        "fill": bool(fill),
        "size": round(float(artist.get_markersize()), 3),
    }


def _collection_marker_style(artist: Any) -> dict[str, Any] | None:
    if not hasattr(artist, "get_offsets") or not hasattr(artist, "get_sizes"):
        return None
    offsets = artist.get_offsets()
    if offsets is None or len(offsets) == 0:
        return None
    facecolors = artist.get_facecolors()
    edgecolors = artist.get_edgecolors()
    sizes = artist.get_sizes()
    face_values = {_style_color(color) for color in facecolors} if len(facecolors) else {"none"}
    edge_values = {_style_color(color) for color in edgecolors} if len(edgecolors) else {"none"}
    size_values = {round(float(np.sqrt(size)), 3) for size in sizes} if len(sizes) else {0.0}
    if len(face_values) > 1 or len(edge_values) > 1 or len(size_values) > 1:
        return None
    paths = artist.get_paths() if hasattr(artist, "get_paths") else []
    marker_shape = _path_signature(paths[0]) if paths else "collection"
    facecolor = next(iter(face_values))
    return {
        "marker": "collection",
        "marker_shape": marker_shape,
        "facecolor": facecolor,
        "edgecolor": next(iter(edge_values)),
        "fill": bool(facecolor != "none"),
        "size": next(iter(size_values)),
    }


def _marker_style(artist: Any) -> dict[str, Any] | None:
    from matplotlib.lines import Line2D

    if isinstance(artist, Line2D):
        return _line_marker_style(artist)
    return _collection_marker_style(artist)


def _style_diff(legend_style: dict[str, Any], data_style: dict[str, Any]) -> list[str]:
    diff: list[str] = []
    for key in ("marker", "facecolor", "edgecolor", "size", "fill"):
        if key == "marker":
            if legend_style.get("marker_shape") != data_style.get("marker_shape"):
                diff.append(key)
        elif key == "size":
            if abs(float(legend_style.get(key, 0.0)) - float(data_style.get(key, 0.0))) > 0.5:
                diff.append(key)
        elif legend_style.get(key) != data_style.get(key):
            diff.append(key)
    if "facecolor" in diff and "fill" in diff:
        diff.remove("fill")
        diff.append("fill")
    return diff


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


def _box_vector_away(source: Bbox, obstacle: Bbox, *, step_px: float) -> tuple[float, float]:
    sx, sy = _box_center(source)
    ox, oy = _box_center(obstacle)
    vx = sx - ox
    vy = sy - oy
    norm = float(np.hypot(vx, vy))
    if norm <= GEOM_EPS_PX:
        return (step_px, step_px)
    return (float(vx / norm * step_px), float(vy / norm * step_px))


def _point_annotation_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "point_annotation_overlaps"
    from matplotlib.text import Annotation

    annotations = [a for a in ax.texts if isinstance(a, Annotation) and _is_paintable(a)]
    if len(annotations) > MAX_TEXT_ARTISTS:
        return {
            "name": name,
            "passed": True,
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

    marker_box = _marker_footprint_boxes(ax, ax.figure, renderer)
    marker_hits: list[int] = []
    if marker_box is not None:
        for index, _center, bb in measured:
            if _boxes_overlap(bb, marker_box):
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

    for label, marker_box in _marker_footprint_box_entries(ax, ax.figure):
        if _box_area(marker_box) > 0:
            candidates.append((label, marker_box, None))
    return candidates


def _artist_overlap_candidates(ax: Axes, renderer: Any) -> list[tuple[str, Bbox]]:
    return [(label, box) for label, box, _artist in _artist_overlap_candidate_items(ax, renderer)]


def _artist_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "artist_overlaps"
    candidates = _artist_overlap_candidate_items(ax, renderer)
    if len(candidates) > MAX_TEXT_ARTISTS:
        return {
            "name": name,
            "passed": True,
            "detail": f"skipped: artist count {len(candidates)} exceeds cap {MAX_TEXT_ARTISTS}",
            "data": {"axis_index": int(axis_index)},
        }

    overlaps: list[dict[str, Any]] = []
    for index_a in range(len(candidates)):
        label_a, box_a, _artist_a = candidates[index_a]
        area_a = _box_area(box_a)
        for index_b in range(index_a + 1, len(candidates)):
            label_b, box_b, _artist_b = candidates[index_b]
            if _is_leader_connected_text_marker_pair(ax, label_a, box_a, _artist_a, label_b, box_b, _artist_b):
                continue
            inter = _inter_area(box_a, box_b)
            if inter <= 0:
                continue
            denom = min(area_a, _box_area(box_b))
            iou = float(inter / denom) if denom > 0 else 0.0
            overlaps.append(
                {
                    "axes": int(axis_index),
                    "a": label_a,
                    "b": label_b,
                    "iou": round(iou, 4),
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
    nearest_box = min(marker_boxes, key=lambda item: (tx - _box_center(item[1])[0]) ** 2 + (ty - _box_center(item[1])[1]) ** 2)[1]
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
            labels.setdefault(text.get_text(), []).append(
                {"axis_index": int(axis_index), "direction": direction}
            )

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


def _default_font_token_sizes(data_axes: list[Axes]) -> list[float]:
    sizes: set[float] = set()
    for ax in data_axes:
        for artist in (ax.xaxis.label, ax.yaxis.label):
            if artist is not None and _is_paintable(artist):
                sizes.add(round(float(artist.get_fontsize()), 2))
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
    role_sizes: dict[str, set[float]] = {"text": set(), "axis": set(), "legend": set()}
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
        legend = ax.get_legend()
        if legend is not None and _is_paintable(legend):
            for text in legend.get_texts():
                if not text.get_text() or not _is_paintable(text):
                    continue
                size = round(float(text.get_fontsize()), 2)
                role_sizes["legend"].add(size)
                if not _font_size_matches_token(size, token_sizes):
                    offenders.append({"axes": int(axis_index), "role": "legend", "text": text.get_text(), "fontsize": size})

    role_size_counts = {role: len(sizes) for role, sizes in role_sizes.items() if sizes}
    if len(offenders) > _MAX_REPORTED_PAIRS:
        offenders = offenders[:_MAX_REPORTED_PAIRS]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(offenders) == 0,
        "detail": f"{len(offenders)} text artists use non-token font sizes",
        "data": {
            "token_sizes": token_sizes,
            "offenders": offenders,
            "offenders_truncated": bool(truncated),
            "role_size_counts": role_size_counts,
        },
    }
