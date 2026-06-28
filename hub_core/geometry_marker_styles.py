"""Marker-style normalization helpers for geometry diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np

ALPHA_EPS = 0.01


def _is_none_color(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.lower() in {"none", "transparent"}:
        return True
    rgba = _rgba_tuple(value)
    return rgba is not None and rgba[3] <= ALPHA_EPS


def _rgba_tuple(value: Any) -> tuple[float, float, float, float] | None:
    from matplotlib.colors import to_rgba

    try:
        rgba = to_rgba(value)
    except (TypeError, ValueError):
        return None
    return tuple(round(float(channel), 4) for channel in rgba)


def _style_color(value: Any) -> str:
    if _is_none_color(value):
        return "none"
    rgba = _rgba_tuple(value)
    if rgba is None:
        return str(value)
    return f"rgba({rgba[0]:.4f},{rgba[1]:.4f},{rgba[2]:.4f},{rgba[3]:.4f})"


def _path_signature(path: Any) -> str:
    vertices = np.asarray(path.vertices, dtype=float)
    if vertices.size == 0 or not np.all(np.isfinite(vertices)):
        return "empty"
    centered = vertices - vertices.mean(axis=0)
    scale = float(np.max(np.abs(centered)))
    if scale > 0:
        centered = centered / scale
    return ";".join(f"{x:.3f},{y:.3f}" for x, y in np.round(centered, 3))


def _line_marker_style(artist: Any) -> dict[str, Any] | None:
    from matplotlib.markers import MarkerStyle

    marker = artist.get_marker()
    style = {
        "line_color": _style_color(artist.get_color()),
        "linestyle": str(artist.get_linestyle()),
        "linewidth": round(float(artist.get_linewidth()), 3),
    }
    if marker in {None, "", "None", "none", " "}:
        return {
            **style,
            "marker": "none",
            "marker_shape": "none",
            "facecolor": "none",
            "edgecolor": "none",
            "fill": False,
            "size": 0.0,
        }
    try:
        marker_style = MarkerStyle(marker)
        marker_shape = _path_signature(marker_style.get_path().transformed(marker_style.get_transform()))
    except (TypeError, ValueError):
        marker_shape = str(marker)
    facecolor = artist.get_markerfacecolor()
    fill = not _is_none_color(facecolor) and artist.get_fillstyle() != "none"
    return {
        **style,
        "marker": str(marker),
        "marker_shape": marker_shape,
        "facecolor": _style_color(facecolor),
        "edgecolor": _style_color(artist.get_markeredgecolor()),
        "fill": bool(fill),
        "size": round(float(artist.get_markersize()), 3),
    }


def _collection_marker_style(artist: Any) -> dict[str, Any] | None:
    if not hasattr(artist, "get_offsets") or not hasattr(artist, "get_sizes"):
        return None
    offsets = artist.get_offsets()
    if offsets is None or len(offsets) == 0:
        return None
    facecolors = artist.get_facecolors()
    edgecolors = artist.get_edgecolors()
    sizes = artist.get_sizes()
    face_values = {_style_color(color) for color in facecolors} if len(facecolors) else {"none"}
    edge_values = {_style_color(color) for color in edgecolors} if len(edgecolors) else {"none"}
    size_values = {round(2.0 * float(np.sqrt(size / np.pi)), 3) for size in sizes} if len(sizes) else {0.0}
    paths = artist.get_paths() if hasattr(artist, "get_paths") else []
    marker_shape = _path_signature(paths[0]) if paths else "collection"
    facecolor = "mixed" if len(face_values) > 1 else next(iter(face_values))
    edgecolor = "mixed" if len(edge_values) > 1 else next(iter(edge_values))
    size: float | str = "mixed" if len(size_values) > 1 else next(iter(size_values))
    return {
        "marker": "collection",
        "marker_shape": marker_shape,
        "facecolor": facecolor,
        "edgecolor": edgecolor,
        "fill": bool(facecolor not in {"none", "mixed"}),
        "size": size,
        "variable_style": bool(len(face_values) > 1 or len(edge_values) > 1 or len(size_values) > 1),
    }


def _marker_style(artist: Any) -> dict[str, Any] | None:
    from matplotlib.lines import Line2D

    if isinstance(artist, Line2D):
        return _line_marker_style(artist)
    return _collection_marker_style(artist)


def _style_diff(legend_style: dict[str, Any], data_style: dict[str, Any]) -> list[str]:
    diff: list[str] = []
    for key in ("marker", "facecolor", "edgecolor", "size", "fill", "line_color", "linestyle", "linewidth"):
        if key not in legend_style or key not in data_style:
            continue
        if key == "marker":
            if legend_style.get("marker_shape") != data_style.get("marker_shape"):
                diff.append(key)
        elif key == "size":
            legend_size = legend_style.get(key, 0.0)
            data_size = data_style.get(key, 0.0)
            if isinstance(legend_size, str) or isinstance(data_size, str):
                if legend_size != data_size:
                    diff.append(key)
            elif abs(float(legend_size) - float(data_size)) > 0.5:
                diff.append(key)
        elif key == "linewidth":
            if abs(float(legend_style.get(key, 0.0)) - float(data_style.get(key, 0.0))) > 0.05:
                diff.append(key)
        elif legend_style.get(key) != data_style.get(key):
            diff.append(key)
    if "facecolor" in diff and "fill" in diff:
        diff.remove("fill")
        diff.append("fill")
    return diff
