from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from typing import Any

import numpy as np

from themes.physics_colormap import resolve_colormap
from themes.style_profiles import get_render_style_tokens


def render_heatmap_plot(ax: Any, points: list[dict], spec: Any) -> None:
    xs = sorted({point["x"] for point in points})
    ys = sorted({point["y"] for point in points})
    x_index = {value: column for column, value in enumerate(xs)}
    y_index = {value: row for row, value in enumerate(ys)}
    grid = np.full((len(ys), len(xs)), np.nan)
    duplicate_cells = 0
    for point in points:
        row = y_index[point["y"]]
        column = x_index[point["x"]]
        if not math.isnan(grid[row, column]):
            duplicate_cells += 1
        grid[row, column] = point["z"]
    if duplicate_cells:
        warnings.warn(
            f"bridge_renderer: {duplicate_cells} duplicate (x,y) heatmap cell(s) overwritten (last value wins)",
            stacklevel=2,
        )

    cmap = resolve_colormap(spec.physics_type, fallback=_default_colormap(spec))
    mesh = ax.pcolormesh(xs, ys, grid, cmap=cmap, shading="auto")
    if spec.annotate_values:
        _annotate_heatmap_values(ax, xs, ys, grid, mesh)
    colorbar = ax.figure.colorbar(mesh, ax=ax)
    colorbar.ax._graph_hub_role = "colorbar"  # positive tag for geometry-diagnostics classification
    colorbar.set_label(spec.z_column)


def _default_colormap(spec: Any) -> str:
    tokens, _meta = get_render_style_tokens(spec.target_format, spec.profile_name)
    return str(tokens.get("default_colormap", "viridis"))


def _format_heatmap_annotation_value(value: float) -> str:
    return f"{value:.3g}"


def _heatmap_annotation_color(mesh: Any, value: float) -> str:
    rgba = mesh.cmap(mesh.norm(value))
    red, green, blue = rgba[:3]
    luminance = 0.299 * red + 0.587 * green + 0.114 * blue
    return "black" if luminance >= 0.5 else "white"


def _annotate_heatmap_values(
    ax: Any,
    xs: Sequence[float | str],
    ys: Sequence[float | str],
    grid: Any,
    mesh: Any,
) -> None:
    for row, y_value in enumerate(ys):
        for column, x_value in enumerate(xs):
            value = float(grid[row, column])
            if not math.isfinite(value):
                continue
            ax.text(
                x_value,
                y_value,
                _format_heatmap_annotation_value(value),
                ha="center",
                va="center",
                color=_heatmap_annotation_color(mesh, value),
                fontsize="small",
                zorder=5,
            )
