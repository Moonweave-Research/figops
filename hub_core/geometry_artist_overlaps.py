"""Generic artist-overlap checks for geometry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from matplotlib.transforms import Bbox

from .geometry_primitives import GEOM_EPS_PX, _box_area, _extent, _overlap_fraction, _overlap_severity

if TYPE_CHECKING:
    from matplotlib.axes import Axes


MarkerFootprintProvider = Callable[[Any, Any], list[tuple[str, Bbox]]]
PaintablePredicate = Callable[[Any], bool]


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


def _artist_overlap_candidate_items(
    ax: Axes,
    renderer: Any,
    *,
    is_paintable: PaintablePredicate,
    marker_footprint_box_entries: MarkerFootprintProvider,
) -> list[tuple[str, Bbox, Any]]:
    from matplotlib.text import Text

    candidates: list[tuple[str, Bbox, Any]] = []
    seen: set[int] = set()

    def add_artist(artist: Any, fallback: str) -> None:
        if artist is None or id(artist) in seen or not is_paintable(artist):
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
        if not is_paintable(line):
            continue
        for segment_index, segment_box in enumerate(_line_overlap_boxes(ax, line)):
            if _box_area(segment_box) > 0:
                candidates.append((f"line:{index}[{segment_index}]", segment_box, None))
    for index, patch in enumerate(ax.patches):
        if getattr(patch, "_graph_hub_leader_patch", False):
            continue
        add_artist(patch, f"patch:{index}")

    for label, marker_box in marker_footprint_box_entries(ax, ax.figure):
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


def _artist_overlap_candidates(
    ax: Axes,
    renderer: Any,
    *,
    is_paintable: PaintablePredicate,
    marker_footprint_box_entries: MarkerFootprintProvider,
) -> list[tuple[str, Bbox]]:
    return [
        (label, box)
        for label, box, _artist in _artist_overlap_candidate_items(
            ax,
            renderer,
            is_paintable=is_paintable,
            marker_footprint_box_entries=marker_footprint_box_entries,
        )
    ]


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


def _artist_overlaps(
    ax: Axes,
    renderer: Any,
    axis_index: int,
    *,
    is_paintable: PaintablePredicate,
    marker_footprint_box_entries: MarkerFootprintProvider,
    max_text_artists: int,
    artist_overlap_warn: float,
    max_reported_pairs: int,
) -> dict[str, Any]:
    name = "artist_overlaps"
    candidates = _artist_overlap_candidate_items(
        ax,
        renderer,
        is_paintable=is_paintable,
        marker_footprint_box_entries=marker_footprint_box_entries,
    )

    pair_candidates: list[tuple[int, int]] = []
    for index_a in range(len(candidates)):
        label_a, box_a, artist_a = candidates[index_a]
        for index_b in range(index_a + 1, len(candidates)):
            label_b, box_b, artist_b = candidates[index_b]
            if _is_reportable_artist_overlap(ax, label_a, box_a, artist_a, label_b, box_b, artist_b):
                pair_candidates.append((index_a, index_b))

    if len(pair_candidates) > max_text_artists:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: reportable artist pair count {len(pair_candidates)} exceeds cap {max_text_artists}",
            "data": {"axis_index": int(axis_index), "candidate_pairs": int(len(pair_candidates))},
        }

    overlaps: list[dict[str, Any]] = []
    for index_a, index_b in pair_candidates:
        label_a, box_a, _artist_a = candidates[index_a]
        label_b, box_b, _artist_b = candidates[index_b]
        iou = _overlap_fraction(box_a, box_b)
        if iou <= artist_overlap_warn:
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
    if len(overlaps) > max_reported_pairs:
        overlaps = overlaps[:max_reported_pairs]
        truncated = True

    return {
        "name": name,
        "passed": len(overlaps) == 0,
        "detail": f"{len(overlaps)} artist overlaps (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "overlaps": overlaps,
            "overlaps_truncated": bool(truncated),
            "threshold": float(artist_overlap_warn),
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


def _box_center(box: Bbox) -> tuple[float, float]:
    return (float((box.x0 + box.x1) / 2), float((box.y0 + box.y1) / 2))
