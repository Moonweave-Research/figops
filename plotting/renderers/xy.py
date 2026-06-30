from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from plotting.renderers.common import group_points, yerr_values


@dataclass(frozen=True)
class XYRendererContext:
    marker_tokens: Callable[..., tuple[float, float, float | None]]
    scatter_marker_area: Callable[[float], float]
    series_style: Callable[[Any, int, object], dict[str, object]]
    display_label: Callable[..., str]
    annotate_points: Callable[..., None]
    apply_legend: Callable[..., None]
    apply_marker_axis_margin: Callable[..., None]
    apply_axis_limits: Callable[[object, Any], None]
    apply_tick_style: Callable[[object, Any], None]


def marker_color_kwargs(sty: dict[str, object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if "markerfacecolor" in sty:
        kwargs["facecolors"] = sty["markerfacecolor"]
    if "markeredgecolor" in sty:
        kwargs["edgecolors"] = sty["markeredgecolor"]
    if "alpha" in sty:
        kwargs["alpha"] = sty["alpha"]
    if "zorder" in sty:
        kwargs["zorder"] = sty["zorder"]
    return kwargs


def line_marker_color_kwargs(sty: dict[str, object]) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if "color" in sty:
        kwargs["color"] = sty["color"]
    if "markerfacecolor" in sty:
        kwargs["markerfacecolor"] = sty["markerfacecolor"]
    if "markeredgecolor" in sty:
        kwargs["markeredgecolor"] = sty["markeredgecolor"]
    if "alpha" in sty:
        kwargs["alpha"] = sty["alpha"]
    if "zorder" in sty:
        kwargs["zorder"] = sty["zorder"]
    return kwargs


def render_xy_plot(
    ax,
    points: list[dict],
    spec: Any,
    *,
    line: bool,
    small_panel: bool = False,
    context: XYRendererContext,
) -> None:
    grouped = group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)
    marker_size, marker_edge_width, _marker_margin = context.marker_tokens(spec, small_panel=small_panel)
    scatter_size = context.scatter_marker_area(marker_size)
    legend_entries: list[tuple[str, str]] = []
    label_points: list[dict] = []

    for idx, (series_name, series_points) in enumerate(grouped.items()):
        xs = [point["x"] for point in series_points]
        ys = [point["y"] for point in series_points]
        yerr = yerr_values(series_points, spec)
        sty = context.series_style(spec, idx, series_name)
        if "label" in sty:
            legend_label = str(sty["label"])
        elif has_multi_series:
            legend_label = context.display_label(series_name, compress_labels=spec.compress_labels)
        else:
            legend_label = None
        if legend_label is not None:
            legend_entries.append((str(series_name), str(legend_label)))
        series_marker_size = float(sty.get("size", marker_size))
        series_scatter_size = float(sty.get("size", scatter_size))
        series_linewidth = float(sty.get("linewidth", 1.2))
        line_marker = str(sty.get("marker") if sty.get("_marker_overridden") else "none")

        cap_size = spec.yerr_cap_width
        cap_thick = max(0.5, spec.yerr_cap_width * 0.4)
        if line:
            if yerr is not None:
                ax.errorbar(
                    xs,
                    ys,
                    yerr=yerr,
                    fmt=line_marker,
                    linestyle=sty["linestyle"],
                    linewidth=series_linewidth,
                    markersize=series_marker_size,
                    markeredgewidth=marker_edge_width,
                    **line_marker_color_kwargs(sty),
                    capsize=cap_size,
                    capthick=cap_thick,
                    label=legend_label,
                )
            else:
                ax.plot(
                    xs,
                    ys,
                    marker=line_marker,
                    linestyle=sty["linestyle"],
                    linewidth=series_linewidth,
                    markersize=series_marker_size,
                    markeredgewidth=marker_edge_width,
                    **line_marker_color_kwargs(sty),
                    label=legend_label,
                )
        elif yerr is not None:
            ax.errorbar(
                xs,
                ys,
                yerr=yerr,
                fmt=sty["marker"],
                linestyle="none",
                markersize=series_marker_size,
                markeredgewidth=marker_edge_width,
                **line_marker_color_kwargs(sty),
                capsize=cap_size,
                capthick=cap_thick,
                label=legend_label,
            )
        else:
            ax.scatter(
                xs,
                ys,
                s=series_scatter_size,
                marker=sty["marker"],
                linewidths=marker_edge_width,
                **marker_color_kwargs(sty),
                label=legend_label,
            )

        if spec.label_column:
            label_points.extend(series_points)

    if spec.label_column and label_points:
        context.annotate_points(
            ax,
            [point["x"] for point in label_points],
            [point["y"] for point in label_points],
            [str(point["label"]) for point in label_points],
            compress_labels=spec.compress_labels,
            point_label_options=spec.point_label_options,
            points=label_points,
        )
    if has_multi_series:
        ax._graph_hub_legend_entries = legend_entries
        context.apply_legend(ax, spec, n_series=len(grouped))
    context.apply_marker_axis_margin(ax, spec, small_panel=small_panel)
    context.apply_axis_limits(ax, spec)
    context.apply_tick_style(ax, spec)
