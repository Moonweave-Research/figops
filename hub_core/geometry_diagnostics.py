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
    }
)


def diagnose_figure_geometry(
    fig: Figure,
    data_axes: list[Axes],
    *,
    layout_locked: bool,
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
