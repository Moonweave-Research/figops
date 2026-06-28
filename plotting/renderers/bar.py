from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from plotting.renderers.common import first_seen_values, group_points, resolve_explicit_order, yerr_values


@dataclass(frozen=True)
class BarRendererContext:
    display_label: Callable[..., str]
    series_style: Callable[[Any, int, object], dict[str, object]]
    annotate_points: Callable[..., None]
    apply_legend: Callable[..., None]


def validate_bar_aggregate(spec: Any) -> None:
    aggregate = str(spec.aggregate or "").strip().lower()
    if not aggregate:
        return
    if aggregate not in {"mean", "median"}:
        raise ValueError("aggregate must be one of: mean, median")
    if str(spec.plot_type or "").strip().lower() != "bar":
        raise ValueError("aggregate is only supported for plot_type 'bar'")
    if spec.series_column:
        raise ValueError("aggregate is only supported for single-series bar plots")


def aggregate_single_series_bar_points(points: list[dict], method: str) -> list[dict]:
    grouped: dict[float | str, list[dict]] = {}
    for point in points:
        grouped.setdefault(point["x"], []).append(point)

    aggregated: list[dict] = []
    for category, category_points in grouped.items():
        values = [float(point["y"]) for point in category_points]
        if method == "mean":
            y_value = float(np.mean(values))
        else:
            y_value = float(np.median(values))
        representative = dict(category_points[0])
        representative["x"] = category
        representative["y"] = y_value
        representative["yerr"] = float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0
        representative["yerr_minus"] = None
        representative["label"] = ""
        aggregated.append(representative)
    return aggregated


def render_bar_plot(ax, points: list[dict], spec: Any, *, context: BarRendererContext) -> None:
    grouped = group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)
    aggregate = str(spec.aggregate or "").strip().lower()
    if aggregate and not has_multi_series:
        points = aggregate_single_series_bar_points(points, aggregate)
        grouped = group_points(points, spec)
    data_order = first_seen_values([point["x"] for point in points])
    categories = resolve_explicit_order(
        data_order,
        spec.category_order,
        field_name="category_order",
    )

    base_positions = list(range(len(categories)))
    category_to_position = {category: index for index, category in enumerate(categories)}

    if has_multi_series:
        series_names = list(grouped.keys())
        width = 0.8 / max(len(series_names), 1)
        offset_start = -0.4 + width / 2
        legend_entries: list[tuple[str, str]] = []
        label_positions: list[tuple[float, float, dict]] = []
        for series_index, series_name in enumerate(series_names):
            series_points = grouped[series_name]
            xs = [category_to_position[point["x"]] + offset_start + series_index * width for point in series_points]
            ys = [point["y"] for point in series_points]
            yerr = yerr_values(series_points, spec)
            sty = context.series_style(spec, series_index, series_name)
            legend_label = context.display_label(series_name, compress_labels=spec.compress_labels)
            legend_entries.append((str(series_name), str(legend_label)))
            bars = ax.bar(
                xs,
                ys,
                width=width,
                yerr=yerr,
                capsize=spec.yerr_cap_width,
                hatch=sty["hatch"],
                edgecolor="black",
                linewidth=0.5,
                label=legend_label,
            )
            if spec.label_column:
                y_offset = max(abs(v) for v in ys) * 0.03 if ys else 0
                label_positions.extend(
                    (bar.get_x() + bar.get_width() / 2, y + y_offset, point)
                    for bar, y, point in zip(bars, ys, series_points)
                )
        if spec.label_column and label_positions:
            context.annotate_points(
                ax,
                [item[0] for item in label_positions],
                [item[1] for item in label_positions],
                [str(item[2]["label"]) for item in label_positions],
                compress_labels=spec.compress_labels,
                point_label_options=spec.point_label_options,
                points=[item[2] for item in label_positions],
            )
        ax._graph_hub_legend_entries = legend_entries
        context.apply_legend(ax, spec, n_series=len(series_names))
    else:
        if len(points) > len(categories):
            # Duplicate categories overplot bars at the same x (last visually wins).
            # Surface it rather than silently aggregating, which could mask intent.
            warnings.warn(
                f"bridge_renderer: single-series bar has {len(points) - len(categories)} "
                "duplicate category value(s); bars overplot at the same x position",
                stacklevel=2,
            )
        row_positions = [category_to_position[point["x"]] for point in points]
        ys = [point["y"] for point in points]
        yerr = yerr_values(points, spec)
        bars = ax.bar(
            row_positions,
            ys,
            yerr=yerr,
            capsize=spec.yerr_cap_width,
            edgecolor="black",
            linewidth=0.5,
        )
        if spec.label_column:
            context.annotate_points(
                ax,
                [bar.get_x() + bar.get_width() / 2 for bar in bars],
                ys,
                [str(point["label"]) for point in points],
                compress_labels=spec.compress_labels,
                point_label_options=spec.point_label_options,
                points=points,
            )

    ax.set_xticks(base_positions)
    ax._graph_hub_original_xtick_labels = {index: str(category) for index, category in enumerate(categories)}
    tick_labels = [context.display_label(category, compress_labels=spec.compress_labels) for category in categories]
    ax.set_xticklabels(tick_labels)
    if any(len(label) > 14 for label in tick_labels):
        for label in ax.get_xticklabels():
            label.set_rotation(20)
            label.set_ha("right")
