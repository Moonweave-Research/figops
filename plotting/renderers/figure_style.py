from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt

from themes.journal_theme import DOUBLE_COLUMN, SINGLE_COLUMN, set_figure_size
from themes.style_profiles import get_render_style_tokens

FORMAT_FIGSIZE_MM: dict[str, tuple[float, float]] = {
    "nature": (89, 71),
    "science": (89, 71),
    "default": (89, 71),
    "ppt": (152, 114),
}


def figsize_for_format(target_format: str) -> tuple[float, float]:
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
