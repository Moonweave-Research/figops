"""Annotation-overlay contrast checks for geometry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .geometry_primitives import _boxes_overlap, _extent

if TYPE_CHECKING:
    from matplotlib.axes import Axes


ALPHA_EPS = 0.01
MAX_REPORTED_OVERLAY_PAIRS = 50
TEXT_OVERLAY_CONTRAST_WARN = 3.0


def _is_paintable_artist(artist: Any) -> bool:
    if not artist.get_visible():
        return False
    alpha = artist.get_alpha()
    return alpha is None or alpha > ALPHA_EPS


def _annotation_overlay_contrast(ax: Axes, renderer: Any, axis_index: int) -> dict[str, Any]:
    name = "annotation_overlay_contrast"
    texts = [
        text
        for text in ax.texts
        if text.get_text() and _is_paintable_artist(text) and getattr(text, "_graph_hub_annotation_text_role", "")
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
    if len(offenders) > MAX_REPORTED_OVERLAY_PAIRS:
        offenders = offenders[:MAX_REPORTED_OVERLAY_PAIRS]
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
        if not getattr(artist, "_graph_hub_overlay_role", "") or not _is_paintable_artist(artist):
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
