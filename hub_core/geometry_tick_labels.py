"""Tick-label overlap and crowding checks for geometry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .geometry_primitives import _boxes_overlap, _extent

if TYPE_CHECKING:
    from matplotlib.axes import Axes


PaintablePredicate = Callable[[Any], bool]


def _visible_tick_labels(labels: list[Any], *, is_paintable: PaintablePredicate) -> list[Any]:
    return [label for label in labels if label.get_text() and is_paintable(label)]


def _axis_tick_labels(ax: Any, axis: str, *, minor: bool = False) -> list[Any]:
    """Return major or minor labels without changing the public major index space.

    ``Axes.get_*ticklabels()`` defaults to major ticks.  Keeping this small
    compatibility helper here lets the overlap metric inspect labels that are
    actually painted by a minor formatter while preserving the historical
    ``x_overlap_pairs``/``y_overlap_pairs`` indices for major labels.
    """

    getter = ax.get_xticklabels if axis == "x" else ax.get_yticklabels
    try:
        return list(getter(minor=minor))
    except TypeError:
        # A minimal test double (or an older Matplotlib facade) may not expose
        # the ``minor`` keyword.  Its default remains the major-label path.
        return list(getter())


def _offset_text_evidence(axis_obj: Any, *, is_paintable: PaintablePredicate) -> dict[str, Any]:
    """Expose the rendered offset text as policy-neutral, deterministic evidence."""

    getter = getattr(axis_obj, "get_offset_text", None)
    if getter is None:
        return {"text": "", "visible": False, "paintable": False, "displayed": False}
    offset = getter()
    if offset is None:
        return {"text": "", "visible": False, "paintable": False, "displayed": False}
    text = str(offset.get_text() or "")
    return {
        "text": text,
        "visible": bool(offset.get_visible()),
        "paintable": bool(is_paintable(offset)),
        "displayed": bool(text and is_paintable(offset)),
    }


def _truncate_pairs(pairs: list[list[int]], *, max_reported_pairs: int) -> tuple[list[list[int]], bool]:
    if len(pairs) > max_reported_pairs:
        return pairs[:max_reported_pairs], True
    return pairs, False


def _tick_label_overlaps(
    ax: Axes,
    renderer: Any,
    axis_index: int,
    *,
    is_paintable: PaintablePredicate,
    max_text_artists: int,
    max_reported_pairs: int,
) -> dict[str, Any]:
    name = "tick_label_overlaps"
    x_major_labels = _visible_tick_labels(
        _axis_tick_labels(ax, "x", minor=False), is_paintable=is_paintable
    )
    y_major_labels = _visible_tick_labels(
        _axis_tick_labels(ax, "y", minor=False), is_paintable=is_paintable
    )
    x_minor_labels = _visible_tick_labels(
        _axis_tick_labels(ax, "x", minor=True), is_paintable=is_paintable
    )
    y_minor_labels = _visible_tick_labels(
        _axis_tick_labels(ax, "y", minor=True), is_paintable=is_paintable
    )
    x_pairs = _axis_tick_overlaps(
        x_major_labels,
        renderer,
        "x",
        max_text_artists=max_text_artists,
    )
    y_pairs = _axis_tick_overlaps(
        y_major_labels,
        renderer,
        "y",
        max_text_artists=max_text_artists,
    )
    x_minor_pairs = _axis_tick_overlaps(
        x_minor_labels,
        renderer,
        "x",
        max_text_artists=max_text_artists,
    )
    y_minor_pairs = _axis_tick_overlaps(
        y_minor_labels,
        renderer,
        "y",
        max_text_artists=max_text_artists,
    )
    if x_pairs is None or y_pairs is None:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: text artist count exceeds cap {max_text_artists}",
            "data": {"axis_index": int(axis_index)},
    }
    x_pairs, x_truncated = _truncate_pairs(x_pairs, max_reported_pairs=max_reported_pairs)
    y_pairs, y_truncated = _truncate_pairs(y_pairs, max_reported_pairs=max_reported_pairs)
    if x_minor_pairs is not None:
        x_minor_pairs, x_minor_truncated = _truncate_pairs(
            x_minor_pairs, max_reported_pairs=max_reported_pairs
        )
    else:
        x_minor_truncated = False
    if y_minor_pairs is not None:
        y_minor_pairs, y_minor_truncated = _truncate_pairs(
            y_minor_pairs, max_reported_pairs=max_reported_pairs
        )
    else:
        y_minor_truncated = False
    x_minor_label_texts = [str(label.get_text()) for label in x_minor_labels[:max_text_artists]]
    y_minor_label_texts = [str(label.get_text()) for label in y_minor_labels[:max_text_artists]]
    # Deliberately keep ``passed`` and its count major-only for compatibility.
    # Minor evidence is additive and policy-neutral; callers can decide whether
    # a journal policy should suppress it without changing generic diagnostics.
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
            "x_minor_labels": x_minor_label_texts,
            "y_minor_labels": y_minor_label_texts,
            "x_minor_label_count": len(x_minor_labels),
            "y_minor_label_count": len(y_minor_labels),
            "x_minor_labels_truncated": len(x_minor_labels) > len(x_minor_label_texts),
            "y_minor_labels_truncated": len(y_minor_labels) > len(y_minor_label_texts),
            "x_minor_overlap_pairs": x_minor_pairs,
            "y_minor_overlap_pairs": y_minor_pairs,
            "x_minor_overlap_pairs_truncated": bool(x_minor_truncated),
            "y_minor_overlap_pairs_truncated": bool(y_minor_truncated),
            "x_offset_text": _offset_text_evidence(ax.xaxis, is_paintable=is_paintable),
            "y_offset_text": _offset_text_evidence(ax.yaxis, is_paintable=is_paintable),
        },
    }


def _axis_tick_overlaps(
    labels: list[Any],
    renderer: Any,
    axis: str,
    *,
    max_text_artists: int,
) -> list[list[int]] | None:
    if len(labels) > max_text_artists:
        return None
    measured: list[tuple[int, float, float, Any]] = []
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


def _tick_label_crowding(
    ax: Axes,
    renderer: Any,
    axis_index: int,
    *,
    is_paintable: PaintablePredicate,
    max_text_artists: int,
    tick_crowding_warn: float,
    crowding_near_low: float,
    crowding_near_high: float,
) -> dict[str, Any]:
    name = "tick_label_crowding"
    x_ratio = _axis_crowding(
        _visible_tick_labels(list(ax.get_xticklabels()), is_paintable=is_paintable),
        ax,
        renderer,
        "x",
        max_text_artists=max_text_artists,
    )
    y_ratio = _axis_crowding(
        _visible_tick_labels(list(ax.get_yticklabels()), is_paintable=is_paintable),
        ax,
        renderer,
        "y",
        max_text_artists=max_text_artists,
    )
    if x_ratio is None or y_ratio is None:
        return {
            "name": name,
            "passed": None,
            "detail": f"skipped: text artist count exceeds cap {max_text_artists}",
            "data": {"axis_index": int(axis_index)},
        }
    worst = max(x_ratio, y_ratio)
    near_boundary = bool(crowding_near_low <= worst <= crowding_near_high)
    return {
        "name": name,
        "passed": bool(worst <= tick_crowding_warn),
        "detail": f"x occupancy {x_ratio:.2f}; y occupancy {y_ratio:.2f} (axis {axis_index})",
        "data": {
            "axis_index": int(axis_index),
            "x_crowding_ratio": float(x_ratio),
            "y_crowding_ratio": float(y_ratio),
            "near_boundary": bool(near_boundary),
        },
    }


def _axis_crowding(
    labels: list[Any],
    ax: Axes,
    renderer: Any,
    axis: str,
    *,
    max_text_artists: int,
) -> float | None:
    if len(labels) > max_text_artists:
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
