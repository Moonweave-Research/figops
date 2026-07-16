from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt

from themes.journal_theme import DOUBLE_COLUMN, SINGLE_COLUMN, set_figure_size
from themes.style_profiles import get_render_style_tokens, get_series_style

FORMAT_FIGSIZE_MM: dict[str, tuple[float, float]] = {
    "nature": (89, 71),
    "science": (89, 71),
    "default": (89, 71),
    "ppt": (152, 114),
}


def figsize_for_format(target_format: str) -> tuple[float, float]:
    if str(target_format).strip().lower() == "neutral":
        return tuple(float(value) for value in plt.rcParams["figure.figsize"])
    tokens, _meta = get_render_style_tokens(target_format, "baseline")
    if "figure_width_mm" in tokens:
        w_mm = float(tokens["figure_width_mm"])
        h_mm = float(tokens.get("figure_height_mm", w_mm * 0.8))
        return set_figure_size(w_mm, h_mm)
    w_mm, h_mm = FORMAT_FIGSIZE_MM.get(target_format, (89, 71))
    return set_figure_size(w_mm, h_mm)


def column_width_mm(target_format: str, column_width: str, profile_name: str = "baseline") -> float:
    width_key = str(column_width or "double").strip().lower()
    tokens, _meta = get_render_style_tokens(target_format, profile_name)
    column_widths = tokens.get("figure_column_widths_mm")
    if isinstance(column_widths, dict) and width_key in column_widths:
        return float(column_widths[width_key])
    return float(DOUBLE_COLUMN if width_key == "double" else SINGLE_COLUMN)


def marker_tokens(spec: Any, *, small_panel: bool = False) -> tuple[float, float, float | None]:
    tokens, _meta = get_render_style_tokens(spec.target_format, spec.profile_name)
    marker_size = float(tokens.get("main_marker_size", plt.rcParams["lines.markersize"]))
    if small_panel:
        marker_size = float(tokens.get("facet_marker_size", marker_size))
    marker_edge_width = float(tokens.get("main_marker_edge_width", plt.rcParams["lines.markeredgewidth"]))
    margin_key = "facet_axis_marker_margin_fraction" if small_panel else "axis_marker_margin_fraction"
    marker_margin = tokens.get(margin_key)
    if marker_margin is None and small_panel:
        marker_margin = tokens.get("axis_marker_margin_fraction")
    return marker_size, marker_edge_width, float(marker_margin) if marker_margin is not None else None


def scatter_marker_area(marker_size_pt: float) -> float:
    return math.pi * (marker_size_pt / 2.0) ** 2


def apply_marker_axis_margin(ax: Any, spec: Any, *, small_panel: bool = False) -> None:
    _marker_size, _marker_edge_width, margin = marker_tokens(spec, small_panel=small_panel)
    if margin is None:
        return
    current_x, current_y = ax.margins()
    ax.margins(x=max(float(current_x), margin), y=max(float(current_y), margin))


def _series_style_override(spec: Any, series_name: object) -> dict[str, object]:
    styles = spec.series_styles or {}
    if not isinstance(styles, dict):
        return {}
    style = styles.get(str(series_name))
    if style is None and series_name == "__single__":
        style = styles.get("__single__") or styles.get("default")
    return dict(style) if isinstance(style, dict) else {}


def _style_float(style: dict[str, object], key: str) -> float | None:
    if key not in style:
        return None
    try:
        return float(style[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"series_styles {key} must be numeric") from exc


def series_style(spec: Any, series_index: int, series_name: object) -> dict[str, object]:
    """Resolve profile defaults and explicit per-series overrides."""
    style = dict(get_series_style(series_index))
    override = _series_style_override(spec, series_name)
    if "marker" in override:
        marker = str(override.get("marker") or "").strip()
        if marker:
            style["marker"] = marker
            style["_marker_overridden"] = True
    if "linestyle" in override:
        style["linestyle"] = str(override.get("linestyle") or style.get("linestyle") or "-")
    if "hatch" in override:
        style["hatch"] = str(override.get("hatch") or "")
    if "color" in override:
        color = str(override.get("color") or "").strip()
        if color:
            style["color"] = color
    if "label" in override:
        label = str(override.get("label") or "").strip()
        if label:
            style["label"] = label
    for numeric_key in ("alpha", "size", "linewidth", "zorder"):
        if numeric_key in override:
            style[numeric_key] = _style_float(override, numeric_key)
    fill = str(override.get("fill") or "").strip().lower()
    markerfacecolor = override.get("facecolor", override.get("markerfacecolor"))
    markeredgecolor = override.get("edgecolor", override.get("markeredgecolor"))
    if markerfacecolor is None and "color" in style and fill not in {"none", "open"}:
        markerfacecolor = style["color"]
    if markeredgecolor is None and "color" in style:
        markeredgecolor = style["color"]
    if fill in {"none", "open"}:
        markerfacecolor = "none"
    elif fill in {"filled", "full"} and markerfacecolor is None:
        markerfacecolor = None
    if markerfacecolor is not None:
        style["markerfacecolor"] = str(markerfacecolor)
    if markeredgecolor is not None:
        style["markeredgecolor"] = str(markeredgecolor)
    return style
