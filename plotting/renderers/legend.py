from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from plotting.utils import get_standard_legend_props
from themes.journal_theme import get_legend_args

LEGEND_DATA_OVERLAP_WARN = 0.05
SMART_LEGEND_INSIDE_CANDIDATES: tuple[str, ...] = (
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "center right",
    "center left",
    "lower center",
    "upper center",
)


def normalized_legend_options(spec: Any) -> dict[str, object]:
    raw_options = spec.legend_options
    if raw_options in (None, {}, []):
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError("legend_options must be an object")
    allowed = {"title", "order", "ncol"}
    unsupported = sorted(set(raw_options) - allowed)
    if unsupported:
        raise ValueError(f"legend_options has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_options.get("title") is not None:
        normalized["title"] = str(raw_options["title"])
    if raw_options.get("order") is not None:
        order = raw_options["order"]
        if not isinstance(order, (list, tuple)):
            raise ValueError("legend_options.order must be an array of labels")
        labels = tuple(str(label) for label in order if str(label).strip())
        if len(labels) != len(set(labels)):
            raise ValueError("legend_options.order must not contain duplicate labels")
        normalized["order"] = labels
    if raw_options.get("ncol") is not None:
        try:
            ncol = int(raw_options["ncol"])
        except (TypeError, ValueError) as exc:
            raise ValueError("legend_options.ncol must be an integer") from exc
        if ncol < 1 or ncol > 8:
            raise ValueError("legend_options.ncol must be between 1 and 8")
        normalized["ncol"] = ncol
    return normalized


def resolved_legend_layout(spec: Any) -> str:
    if spec.legend_layout != "auto":
        return spec.legend_layout
    if spec.target_format == "ppt":
        return "right_outside"
    return "smart"


def separate_top_legend_title(ax, spec: Any) -> None:
    legend = ax.get_legend()
    if not spec.title or (
        resolved_legend_layout(spec) != "top_outside"
        and getattr(legend, "_graph_hub_legend_placement", None) != "top_outside"
    ):
        return
    if legend is None:
        return

    fig = ax.figure
    pad_px = float(plt.rcParams.get("axes.titlepad", 6.0)) * fig.dpi / 72.0
    for _ in range(2):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        title_bb = ax.title.get_window_extent(renderer)
        legend_bb = legend.get_window_extent(renderer)
        overlap_width = min(title_bb.x1, legend_bb.x1) - max(title_bb.x0, legend_bb.x0)
        overlap_height = min(title_bb.y1, legend_bb.y1) - max(title_bb.y0, legend_bb.y0)
        if overlap_width <= 0 or overlap_height <= 0:
            return

        axes_height = ax.get_window_extent(renderer).height
        if axes_height <= 0:
            return
        title_x, title_y = ax.title.get_position()
        ax.set_title(ax.title.get_text(), x=title_x, y=title_y + (overlap_height + pad_px) / axes_height)


def find_best_legend_location(ax) -> dict:
    x_data = []
    y_data = []

    x_lim = ax.get_xlim()
    y_lim = ax.get_ylim()

    for line in ax.lines:
        x_data.extend(line.get_xdata())
        y_data.extend(line.get_ydata())
    for coll in ax.collections:
        if hasattr(coll, "get_offsets"):
            offsets = coll.get_offsets()
            if len(offsets) > 0:
                x_data.extend(offsets[:, 0])
                y_data.extend(offsets[:, 1])

    if not x_data:
        return {"loc": "best", "frameon": False}

    x_range = x_lim[1] - x_lim[0]
    y_range = y_lim[1] - y_lim[0]
    if x_range == 0 or y_range == 0:
        return {"loc": "best", "frameon": False}

    grid_size = 10
    grid = np.zeros((grid_size, grid_size))

    try:
        x_norm = (np.array(x_data) - x_lim[0]) / x_range
        y_norm = (np.array(y_data) - y_lim[0]) / y_range

        mask = (x_norm >= 0) & (x_norm <= 1) & (y_norm >= 0) & (y_norm <= 1)
        x_norm, y_norm = x_norm[mask], y_norm[mask]

        for xi, yi in zip(x_norm, y_norm):
            gx = min(int(xi * grid_size), grid_size - 1)
            gy = min(int(yi * grid_size), grid_size - 1)
            grid[gy, gx] += 1
    except (ValueError, ZeroDivisionError):
        return {"loc": "best", "frameon": False}

    best_score = float("inf")
    best_pos = (grid_size - 1, grid_size - 1)

    for row in range(1, grid_size - 1):
        for col in range(1, grid_size - 1):
            row_start, row_end = max(0, row - 1), min(grid_size, row + 2)
            col_start, col_end = max(0, col - 1), min(grid_size, col + 2)
            score = np.sum(grid[row_start:row_end, col_start:col_end])

            dist_to_edge = min(row, grid_size - 1 - row, col, grid_size - 1 - col)
            score += dist_to_edge * 0.1

            if score < best_score:
                best_score = score
                best_pos = (row, col)

    target_x = best_pos[1] / grid_size
    target_y = best_pos[0] / grid_size

    target_x = max(0.05, min(0.95, target_x))
    target_y = max(0.05, min(0.95, target_y))

    is_crowded = best_score > (len(x_data) * 0.1)

    legend_args = {
        "bbox_to_anchor": (target_x, target_y),
        "loc": "center",
        "bbox_transform": ax.transAxes,
        "frameon": True,
        "fontsize": "small",
    }

    if is_crowded:
        legend_args["framealpha"] = 0.7
    else:
        legend_args["frameon"] = False

    return legend_args


def legend_data_overlap_fraction(ax) -> float:
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    legend = ax.get_legend()
    if legend is None or not legend.get_visible():
        return 0.0
    from hub_core.geometry_diagnostics import _box_area, _data_union_bbox, _extent, _inter_area

    legend_bb = _extent(legend, renderer)
    data_union = _data_union_bbox(ax, renderer)
    if legend_bb is None or data_union is None:
        return 0.0
    legend_area = _box_area(legend_bb)
    if legend_area <= 0:
        return 0.0
    return float(_inter_area(legend_bb, data_union) / legend_area)


def legend_inside_axes(ax) -> bool:
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    legend = ax.get_legend()
    if legend is None or not legend.get_visible():
        return False
    legend_box = legend.get_window_extent(renderer)
    axes_box = ax.get_window_extent(renderer)
    return bool(
        legend_box.x0 >= axes_box.x0
        and legend_box.x1 <= axes_box.x1
        and legend_box.y0 >= axes_box.y0
        and legend_box.y1 <= axes_box.y1
    )


def replace_legend(ax, **kwargs):
    legend = ax.get_legend()
    if legend is None:
        return None
    handles, labels = ax.get_legend_handles_labels()
    pairs = [(handle, label) for handle, label in zip(handles, labels) if label and label != "_nolegend_"]
    if not pairs:
        return legend
    legend.remove()
    handles, labels = zip(*pairs)
    return ax.legend(handles, labels, **kwargs)


def avoid_smart_legend_data_collision(fig, ax, spec: Any) -> str:
    legend = ax.get_legend()
    if legend is None:
        return "none"
    if legend_data_overlap_fraction(ax) <= LEGEND_DATA_OVERLAP_WARN and legend_inside_axes(ax):
        setattr(legend, "_graph_hub_legend_placement", "inside")
        return "inside"

    for loc in SMART_LEGEND_INSIDE_CANDIDATES:
        candidate = replace_legend(ax, loc=loc, frameon=False, fontsize="small")
        if candidate is None:
            return "none"
        fig.tight_layout(pad=0.5)
        if legend_data_overlap_fraction(ax) <= LEGEND_DATA_OVERLAP_WARN and legend_inside_axes(ax):
            setattr(candidate, "_graph_hub_legend_placement", "inside")
            return "inside"

    ncol = min(max(len(ax.get_legend_handles_labels()[1]), 1), 3)
    fallback = replace_legend(
        ax,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=ncol,
        frameon=False,
        fontsize=plt.rcParams.get("legend.fontsize", 7.0),
    )
    if fallback is not None:
        setattr(fallback, "_graph_hub_legend_placement", "top_outside")
    fig.tight_layout(pad=0.5)
    separate_top_legend_title(ax, spec)
    return "top_outside"


def legend_kwargs(ax, spec: Any, *, n_series: int) -> dict:
    layout = resolved_legend_layout(spec)
    if layout == "smart":
        return find_best_legend_location(ax)
    if layout == "right_outside":
        return get_legend_args("right_outside", ncol=1)
    if layout == "best":
        kwargs = dict(get_legend_args("standard"))
        kwargs["frameon"] = False
        return kwargs
    if layout == "standard":
        kwargs = dict(get_legend_args("standard"))
        kwargs["frameon"] = False
        return kwargs

    kwargs = dict(get_standard_legend_props())
    kwargs["ncol"] = min(max(n_series, 1), 4)
    return kwargs


def apply_legend(ax, spec: Any, *, n_series: int) -> None:
    kwargs = legend_kwargs(ax, spec, n_series=n_series)
    options = normalized_legend_options(spec)
    if "title" in options:
        kwargs["title"] = options["title"]
    if "ncol" in options:
        kwargs["ncol"] = options["ncol"]
    try:
        handles, labels = ax.get_legend_handles_labels()
    except ValueError:
        ax.legend(**kwargs)
        return
    if options.get("order"):
        legend_entries = list(getattr(ax, "_graph_hub_legend_entries", ()))
        raw_to_label = {raw: label for raw, label in legend_entries}
        label_to_items = {label: (handle, label) for handle, label in zip(handles, labels)}
        ordered_keys = tuple(options["order"])
        missing = [raw for raw in ordered_keys if raw not in raw_to_label]
        if missing:
            raise ValueError(f"legend_options.order contains unknown series key(s): {', '.join(missing)}")
        ordered_labels = [raw_to_label[raw] for raw in ordered_keys]
        ordered_items = [label_to_items[label] for label in ordered_labels if label in label_to_items]
        ordered_label_set = set(ordered_labels)
        remaining_items = [(handle, label) for handle, label in zip(handles, labels) if label not in ordered_label_set]
        if ordered_items:
            handles, labels = zip(*(ordered_items + remaining_items), strict=True)
            handles = list(handles)
            labels = list(labels)
    ax.legend(handles, labels, **kwargs)
