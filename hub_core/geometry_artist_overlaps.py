"""Generic artist-overlap checks for geometry diagnostics."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from matplotlib.transforms import Bbox

from .geometry_primitives import GEOM_EPS_PX, _box_area, _extent, _overlap_fraction, _overlap_severity

_LINE_SEGMENT_LABEL_PATTERN = re.compile(r"^line:(\d+)\[(\d+)\]$")

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


def _line_overlap_segments(
    ax: Axes,
    line: Any,
) -> list[tuple[Bbox, np.ndarray | None, np.ndarray | None]]:
    """Return a padded segment bbox and its centerline endpoints.

    The bbox remains the legacy candidate geometry used by the IoU metric,
    while the endpoints provide exact line-vs-artist evidence for any pair
    that contains one line segment.  Both are emitted in the same segment
    order, so a ``line:i[j]`` label can be resolved back to its centerline.

    This intentionally preserves the legacy finite-point handling and data
    transform used by :func:`_line_overlap_boxes`; changing either would
    silently change candidate labels or their bbox values for existing users.
    A finite-point pair spanning a NaN path break retains its legacy box but
    has unresolved exact endpoints, so callers cannot claim a collision
    across the synthetic gap.
    """

    xy = np.asarray(line.get_xydata(), dtype=float)
    if xy.size == 0:
        return []
    finite_mask = np.all(np.isfinite(xy[:, :2]), axis=1)
    finite_indices = np.flatnonzero(finite_mask)
    finite = xy[finite_mask, :2]
    if len(finite) < 2:
        return []
    display = ax.transData.transform(finite)
    if not np.all(np.isfinite(display)):
        return []
    try:
        line_transform = line.get_transform()
    except (AttributeError, RuntimeError):
        line_transform = ax.transData
    if line_transform is None or not hasattr(line_transform, "transform"):
        line_transform = ax.transData
    try:
        exact_display = np.asarray(line_transform.transform(finite), dtype=float)
    except (TypeError, ValueError, OverflowError, RuntimeError):
        exact_display = display
    exact_display_valid = exact_display.shape == display.shape and np.all(np.isfinite(exact_display))
    half_width = max(GEOM_EPS_PX, float(line.get_linewidth()) / 2)
    segments: list[tuple[Bbox, np.ndarray | None, np.ndarray | None]] = []
    for point_index, (start, end) in enumerate(zip(display, display[1:])):
        x0 = min(float(start[0]), float(end[0])) - half_width
        x1 = max(float(start[0]), float(end[0])) + half_width
        y0 = min(float(start[1]), float(end[1])) - half_width
        y1 = max(float(start[1]), float(end[1])) + half_width
        if (
            int(finite_indices[point_index + 1]) == int(finite_indices[point_index]) + 1
            and exact_display_valid
        ):
            exact_start: np.ndarray | None = np.asarray(exact_display[point_index], dtype=float)
            exact_end: np.ndarray | None = np.asarray(exact_display[point_index + 1], dtype=float)
        else:
            exact_start = None
            exact_end = None
        segments.append((Bbox.from_extents(x0, y0, x1, y1), exact_start, exact_end))
    return segments


def _line_overlap_boxes(ax: Axes, line: Any) -> list[Bbox]:
    """Return legacy padded AABBs for each finite line segment."""

    return [box for box, _start, _end in _line_overlap_segments(ax, line)]


def _line_segment_resolver(ax: Axes) -> Callable[[str], tuple[np.ndarray, np.ndarray] | None]:
    """Resolve a ``line:i[j]`` candidate label to centerline endpoints.

    The resolver is deliberately total: malformed labels and labels that no
    longer resolve to a current line/segment return ``None`` rather than
    raising during diagnostics.  Segment lists are cached per line so a
    dense candidate set does not recompute the same line for every pair; the
    caller's reported-cap controls how many facts are emitted.
    """

    cache: dict[int, list[tuple[Bbox, np.ndarray | None, np.ndarray | None]]] = {}
    lines = list(ax.get_lines())

    def resolve(label: str) -> tuple[np.ndarray, np.ndarray] | None:
        if not isinstance(label, str):
            return None
        match = _LINE_SEGMENT_LABEL_PATTERN.match(label)
        if match is None:
            return None
        line_index = int(match.group(1))
        segment_index = int(match.group(2))
        if not 0 <= line_index < len(lines):
            return None
        if line_index not in cache:
            cache[line_index] = _line_overlap_segments(ax, lines[line_index])
        segments = cache[line_index]
        if not 0 <= segment_index < len(segments):
            return None
        _box, start, end = segments[segment_index]
        if start is None or end is None:
            return None
        return start, end

    return resolve


def _pair_centerline_intersection_px(
    resolve: Callable[[str], tuple[np.ndarray, np.ndarray] | None],
    label_a: str,
    box_a: Bbox,
    label_b: str,
    box_b: Bbox,
) -> float | None:
    """Measure exact centerline length for a line/non-line candidate pair.

    ``None`` denotes pairs with no line or with two lines; those pairs retain
    their legacy bbox IoU only.  For exactly one line, the returned length is
    the positive-length Liang--Barsky intersection with the other artist's
    bbox.  A zero value therefore exposes a diagonal-bbox artifact without
    discarding the original bbox candidate data.
    """

    segment_a = resolve(label_a)
    segment_b = resolve(label_b)
    if (segment_a is None) == (segment_b is None):
        return None
    if segment_a is not None:
        start, end, other_box = segment_a[0], segment_a[1], box_b
    else:
        assert segment_b is not None
        start, end, other_box = segment_b[0], segment_b[1], box_a
    return float(_segment_bbox_intersection_length(start, end, other_box))


def _segment_bbox_intersection_length(
    start: np.ndarray,
    end: np.ndarray,
    box: Bbox,
) -> float:
    """Return the positive-length intersection of a segment and a box.

    ``_line_overlap_boxes`` intentionally models a line as a padded AABB for
    the legacy IoU check.  That approximation is too coarse for a thin line:
    its box has a tiny area relative to a text bbox even when the line runs
    directly through the text.  This helper instead clips the *centerline*
    against the text bbox (Liang--Barsky), so corner/edge contacts do not
    become crossings and a line only counts when it spends measurable length
    inside the text box.
    """

    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    dx = x1 - x0
    dy = y1 - y0
    segment_length = float(np.hypot(dx, dy))
    if not np.isfinite(segment_length) or segment_length <= GEOM_EPS_PX:
        return 0.0

    # Parametric clipping against x >= box.x0, x <= box.x1,
    # y >= box.y0, and y <= box.y1.  Keeping the interval in [0, 1]
    # avoids constructing an expanded bbox (which would reintroduce
    # linewidth-dependent false positives).
    lower = 0.0
    upper = 1.0
    for p, q in (
        (-dx, x0 - float(box.x0)),
        (dx, float(box.x1) - x0),
        (-dy, y0 - float(box.y0)),
        (dy, float(box.y1) - y0),
    ):
        if abs(p) <= np.finfo(float).eps:
            if q < 0:
                return 0.0
            continue
        ratio = q / p
        if p < 0:
            if ratio > upper:
                return 0.0
            lower = max(lower, ratio)
        else:
            if ratio < lower:
                return 0.0
            upper = min(upper, ratio)
    if upper <= lower:
        return 0.0
    clipped_length = segment_length * (upper - lower)
    if clipped_length <= GEOM_EPS_PX:
        return 0.0
    return float(clipped_length)


def _line_display_segments(ax: Axes, line: Any, *, max_segments: int) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """Return finite display-space line segments with stable source indices.

    NaN-separated paths are not joined.  A finite segment cap keeps this
    metric bounded for a pathological polyline while retaining the original
    segment index in every reported fact.
    """

    if max_segments <= 0:
        return []
    try:
        xy = np.asarray(line.get_xydata(), dtype=float)
    except (TypeError, ValueError):
        return []
    if xy.ndim != 2 or xy.shape[1] < 2 or xy.shape[0] < 2:
        return []
    # The path cap also bounds the transform itself; do not materialize a
    # million-vertex polyline merely to retain the first bounded candidates.
    xy = xy[: max_segments + 1, :2]

    try:
        transform = line.get_transform()
    except (AttributeError, RuntimeError):
        transform = ax.transData
    if transform is None or not hasattr(transform, "transform"):
        transform = ax.transData
    try:
        # ``axhline``/``axvline`` use blended axis/data transforms; using the
        # line's own transform keeps those reference lines correct when the
        # data limits are not the default 0..1 range.
        display = np.asarray(transform.transform(xy[:, :2]), dtype=float)
    except (TypeError, ValueError, OverflowError, RuntimeError):
        return []
    if display.shape != (xy.shape[0], 2):
        return []

    segments: list[tuple[int, np.ndarray, np.ndarray]] = []
    for segment_index, (start, end) in enumerate(zip(display[:-1], display[1:])):
        if not (np.all(np.isfinite(start)) and np.all(np.isfinite(end))):
            continue
        segments.append((int(segment_index), start, end))
        if len(segments) >= max_segments:
            break
    return segments


def _line_text_crossings(
    ax: Axes,
    renderer: Any,
    *,
    is_paintable: PaintablePredicate,
    candidate_cap: int,
    reported_cap: int,
) -> dict[str, Any]:
    """Measure high-confidence line-segment/text-bbox crossings.

    The result is deliberately a policy-neutral fact object: it reports what
    was measured and bounded, but never a threshold, verdict, or severity.
    Lines and text are considered in stable Matplotlib artist order.  A
    segment counts only when its centerline has more than ``GEOM_EPS_PX`` of
    positive-length intersection with a visible, non-empty text bbox.
    """

    if candidate_cap <= 0 or reported_cap <= 0:
        raise ValueError("candidate_cap and reported_cap must be positive")

    from matplotlib.text import Text

    line_entries: list[tuple[int, str, Any]] = []
    for line_index, line in enumerate(ax.get_lines()):
        if is_paintable(line):
            line_entries.append((int(line_index), f"line:{line_index}", line))
    text_entries: list[tuple[int, str, Bbox]] = []

    def add_text(text: Any, fallback: str, text_index: int) -> None:
        if not isinstance(text, Text) or not is_paintable(text) or not text.get_text():
            return
        bb = _extent(text, renderer)
        if bb is None or _box_area(bb) <= 0:
            return
        text_entries.append((int(text_index), _artist_label(text, fallback), bb))

    add_text(ax.title, "title", 0)
    for text_index, text in enumerate(ax.texts, start=1):
        add_text(text, f"text:{text_index - 1}", text_index)

    evaluated_lines = line_entries[:candidate_cap]
    evaluated_texts = text_entries[:candidate_cap]
    text_bounds = (
        np.asarray(
            [
                [float(text_box.x0), float(text_box.y0), float(text_box.x1), float(text_box.y1)]
                for _index, _label, text_box in evaluated_texts
            ],
            dtype=float,
        )
        if evaluated_texts
        else np.empty((0, 4), dtype=float)
    )
    crossing_count = 0
    crossings: list[dict[str, Any]] = []
    # A line with millions of vertices must not turn a diagnostics call into
    # an unbounded walk.  Use the same candidate cap for vertices and retain
    # the original segment index for deterministic evidence.
    for line_index, line_label, line in evaluated_lines:
        segments = _line_display_segments(ax, line, max_segments=candidate_cap)
        for segment_index, start, end in segments:
            segment_length = float(np.hypot(*(end - start)))
            if text_bounds.size == 0:
                continue
            segment_x0 = min(float(start[0]), float(end[0]))
            segment_x1 = max(float(start[0]), float(end[0]))
            segment_y0 = min(float(start[1]), float(end[1]))
            segment_y1 = max(float(start[1]), float(end[1]))
            # Most segments are nowhere near most text bboxes.  Keep the
            # exact Liang--Barsky predicate below, but cheaply cull disjoint
            # AABBs in NumPy first to avoid an O(lines*segments*texts) Python
            # loop for dense figures.
            possible_texts = np.flatnonzero(
                (text_bounds[:, 2] > segment_x0)
                & (text_bounds[:, 0] < segment_x1)
                & (text_bounds[:, 3] > segment_y0)
                & (text_bounds[:, 1] < segment_y1)
            )
            for text_position in possible_texts:
                text_index, text_label, text_box = evaluated_texts[int(text_position)]
                intersection_length = _segment_bbox_intersection_length(start, end, text_box)
                if intersection_length <= GEOM_EPS_PX:
                    continue
                crossing_count += 1
                if len(crossings) >= reported_cap:
                    continue
                crossings.append(
                    {
                        "line": line_label,
                        "text": text_label,
                        "line_index": int(line_index),
                        "segment_index": int(segment_index),
                        "text_index": int(text_index),
                        "intersection_length_px": round(float(intersection_length), 6),
                        "segment_length_px": round(float(segment_length), 6),
                    }
                )

    return {
        "line_count": int(len(line_entries)),
        "evaluated_line_count": int(len(evaluated_lines)),
        "lines_truncated": bool(len(line_entries) > len(evaluated_lines)),
        "text_count": int(len(text_entries)),
        "evaluated_text_count": int(len(evaluated_texts)),
        "texts_truncated": bool(len(text_entries) > len(evaluated_texts)),
        "crossing_count": int(crossing_count),
        "reported_crossing_count": int(len(crossings)),
        "crossings": crossings,
        "crossings_truncated": bool(crossing_count > len(crossings)),
    }


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
