"""Layout-oriented geometry checks for titles, labels, and panel chrome."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .geometry_primitives import _boxes_overlap, _extent, _overlap_fraction, _overlap_severity

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


PaintablePredicate = Callable[[Any], bool]


def _axis_label_title_overlap(
    ax: Axes,
    renderer: Any,
    axis_index: int,
    *,
    is_paintable: PaintablePredicate,
) -> dict[str, Any]:
    name = "axis_label_title_overlap"
    artists = [
        artist
        for artist in (ax.xaxis.label, ax.yaxis.label, ax.title)
        if artist is not None and artist.get_text() and is_paintable(artist)
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


def _figure_title_panel_title_overlap(
    fig: Figure,
    data_axes: list[Axes],
    renderer: Any,
    *,
    is_paintable: PaintablePredicate,
) -> dict[str, Any]:
    name = "figure_title_panel_title_overlap"
    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is None or not suptitle.get_text() or not is_paintable(suptitle):
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
        if title is None or not title.get_text() or not is_paintable(title):
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
