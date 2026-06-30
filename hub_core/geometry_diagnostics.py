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

from .geometry_artist_overlaps import _artist_candidate_kind as _artist_candidate_kind
from .geometry_artist_overlaps import _artist_label as _artist_label
from .geometry_artist_overlaps import _artist_overlap_candidate_items as _artist_overlap_candidate_items_impl
from .geometry_artist_overlaps import _artist_overlap_candidates as _artist_overlap_candidates_impl
from .geometry_artist_overlaps import _artist_overlaps as _artist_overlaps_impl
from .geometry_artist_overlaps import _is_leader_connected_text_marker_pair as _is_leader_connected_text_marker_pair
from .geometry_artist_overlaps import _is_reportable_artist_overlap as _is_reportable_artist_overlap
from .geometry_artist_overlaps import _leader_target_inside_marker_box as _leader_target_inside_marker_box
from .geometry_artist_overlaps import _line_overlap_boxes as _line_overlap_boxes
from .geometry_bounds_checks import _artists_outside_axes as _artists_outside_axes_impl
from .geometry_bounds_checks import _artists_outside_figure as _artists_outside_figure_impl
from .geometry_bounds_checks import _chrome_artists as _chrome_artists_impl
from .geometry_bounds_checks import _degenerate_outside_fraction as _degenerate_outside_fraction
from .geometry_bounds_checks import _overlap_fraction_1d as _overlap_fraction_1d
from .geometry_bounds_checks import _visible_data_artists as _visible_data_artists_impl
from .geometry_bounds_checks import _visible_data_lim as _visible_data_lim_impl
from .geometry_label_offsets import _label_offset_consistency as _label_offset_consistency_impl
from .geometry_label_offsets import _nearest_marker_direction as _nearest_marker_direction_impl
from .geometry_label_offsets import _point_label_skips as _point_label_skips
from .geometry_label_offsets import _text_axis_edge_proximity as _text_axis_edge_proximity_impl
from .geometry_layout_checks import _axis_label_title_overlap as _axis_label_title_overlap_impl
from .geometry_layout_checks import _figure_title_panel_title_overlap as _figure_title_panel_title_overlap_impl
from .geometry_marker_styles import _collection_marker_style as _collection_marker_style
from .geometry_marker_styles import _is_none_color as _is_none_color
from .geometry_marker_styles import _line_marker_style as _line_marker_style
from .geometry_marker_styles import _marker_style as _marker_style
from .geometry_marker_styles import _path_signature as _path_signature
from .geometry_marker_styles import _rgba_tuple as _rgba_tuple
from .geometry_marker_styles import _style_color as _style_color
from .geometry_marker_styles import _style_diff as _style_diff
from .geometry_overlay_contrast import _annotation_overlay_contrast as _annotation_overlay_contrast
from .geometry_overlay_contrast import _artist_rgb as _artist_rgb
from .geometry_overlay_contrast import _composite_rgb as _composite_rgb
from .geometry_overlay_contrast import _contrast_ratio as _contrast_ratio
from .geometry_overlay_contrast import _overlay_artist_rgb as _overlay_artist_rgb
from .geometry_overlay_contrast import _overlay_contrast_items as _overlay_contrast_items
from .geometry_overlay_contrast import _relative_luminance as _relative_luminance
from .geometry_primitives import GEOM_EPS_PX as GEOM_EPS_PX
from .geometry_primitives import _box_area as _box_area
from .geometry_primitives import _boxes_overlap as _boxes_overlap
from .geometry_primitives import _circle_overlap_fraction as _circle_overlap_fraction
from .geometry_primitives import _extent as _extent
from .geometry_primitives import _inter_area as _inter_area
from .geometry_primitives import _overlap_fraction as _overlap_fraction
from .geometry_primitives import _overlap_severity as _overlap_severity
from .geometry_style_checks import _append_linewidth_offender as _append_linewidth_offender
from .geometry_style_checks import _default_font_token_sizes as _default_font_token_sizes
from .geometry_style_checks import _font_size_matches_token as _font_size_matches_token
from .geometry_style_checks import _font_size_token_drift as _font_size_token_drift
from .geometry_style_checks import _journal_compliance as _journal_compliance
from .geometry_style_checks import _journal_font_offenders as _journal_font_offenders
from .geometry_style_checks import _journal_line_offenders as _journal_line_offenders
from .geometry_style_checks import _line_width_values as _line_width_values
from .geometry_tick_labels import _axis_crowding as _axis_crowding_impl
from .geometry_tick_labels import _axis_tick_overlaps as _axis_tick_overlaps_impl
from .geometry_tick_labels import _tick_label_crowding as _tick_label_crowding_impl
from .geometry_tick_labels import _tick_label_overlaps as _tick_label_overlaps_impl
from .geometry_tick_labels import _truncate_pairs as _truncate_pairs_impl
from .geometry_tick_labels import _visible_tick_labels as _visible_tick_labels_impl

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
    return _visible_data_artists_impl(ax, is_paintable=_is_paintable)


def _visible_tick_labels(labels: list[Any]) -> list[Any]:
    return _visible_tick_labels_impl(labels, is_paintable=_is_paintable)


def _truncate_pairs(pairs: list[list[int]]) -> tuple[list[list[int]], bool]:
    return _truncate_pairs_impl(pairs, max_reported_pairs=_MAX_REPORTED_PAIRS)


def _tick_label_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    return _tick_label_overlaps_impl(
        ax,
        renderer,
        axis_index,
        is_paintable=_is_paintable,
        max_text_artists=MAX_TEXT_ARTISTS,
        max_reported_pairs=_MAX_REPORTED_PAIRS,
    )


def _axis_tick_overlaps(labels: list[Any], renderer: Any, axis: str) -> list[list[int]] | None:
    return _axis_tick_overlaps_impl(labels, renderer, axis, max_text_artists=MAX_TEXT_ARTISTS)


def _tick_label_crowding(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    return _tick_label_crowding_impl(
        ax,
        renderer,
        axis_index,
        is_paintable=_is_paintable,
        max_text_artists=MAX_TEXT_ARTISTS,
        tick_crowding_warn=TICK_CROWDING_WARN,
        crowding_near_low=_CROWDING_NEAR_LOW,
        crowding_near_high=_CROWDING_NEAR_HIGH,
    )


def _axis_crowding(labels: list[Any], ax: Axes, renderer: Any, axis: str) -> float | None:
    return _axis_crowding_impl(labels, ax, renderer, axis, max_text_artists=MAX_TEXT_ARTISTS)


def _visible_data_lim(ax: Axes) -> Bbox | None:
    return _visible_data_lim_impl(ax, is_paintable=_is_paintable)


def _artists_outside_axes(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    return _artists_outside_axes_impl(
        ax,
        renderer,
        axis_index,
        is_paintable=_is_paintable,
        data_outside_axes_warn=DATA_OUTSIDE_AXES_WARN,
    )


def _chrome_artists(ax: Axes) -> list[Any]:
    return _chrome_artists_impl(ax, is_paintable=_is_paintable)


def _artists_outside_figure(
    ax: Axes,
    fig: Figure,
    renderer: Any,
    axis_index: int,
    layout_locked: bool,
) -> dict[str, Any]:
    return _artists_outside_figure_impl(
        ax,
        fig,
        renderer,
        axis_index,
        layout_locked,
        is_paintable=_is_paintable,
    )


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
    return _axis_label_title_overlap_impl(ax, renderer, axis_index, is_paintable=_is_paintable)


def _figure_title_panel_title_overlap(fig: Figure, data_axes: list[Axes], renderer: Any) -> dict[str, Any]:
    return _figure_title_panel_title_overlap_impl(fig, data_axes, renderer, is_paintable=_is_paintable)


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
    return _text_axis_edge_proximity_impl(
        ax,
        renderer,
        axis_index,
        is_paintable=_is_paintable,
        threshold_px=TEXT_AXIS_EDGE_WARN_PX,
        max_reported_pairs=_MAX_REPORTED_PAIRS,
    )


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


def _artist_overlap_candidate_items(ax: Axes, renderer: Any) -> list[tuple[str, Bbox, Any]]:
    return _artist_overlap_candidate_items_impl(
        ax,
        renderer,
        is_paintable=_is_paintable,
        marker_footprint_box_entries=_marker_footprint_box_entries,
    )


def _artist_overlap_candidates(ax: Axes, renderer: Any) -> list[tuple[str, Bbox]]:
    return _artist_overlap_candidates_impl(
        ax,
        renderer,
        is_paintable=_is_paintable,
        marker_footprint_box_entries=_marker_footprint_box_entries,
    )


def _artist_overlaps(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    return _artist_overlaps_impl(
        ax,
        renderer,
        axis_index,
        is_paintable=_is_paintable,
        marker_footprint_box_entries=_marker_footprint_box_entries,
        max_text_artists=MAX_TEXT_ARTISTS,
        artist_overlap_warn=ARTIST_OVERLAP_WARN,
        max_reported_pairs=_MAX_REPORTED_PAIRS,
    )


def _nearest_marker_direction(ax: Axes, text: Any, renderer: Any) -> str | None:
    return _nearest_marker_direction_impl(
        ax,
        text,
        renderer,
        marker_footprint_box_entries=_marker_footprint_box_entries,
    )


def _label_offset_consistency(fig: Figure, data_axes: list[Axes], renderer: Any) -> dict[str, Any]:
    return _label_offset_consistency_impl(
        fig,
        data_axes,
        renderer,
        marker_footprint_box_entries=_marker_footprint_box_entries,
        is_paintable=_is_paintable,
        max_reported_pairs=_MAX_REPORTED_PAIRS,
    )
