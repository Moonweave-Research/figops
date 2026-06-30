from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from plotting.renderers.common import group_points, yerr_values
from plotting.renderers.xy import line_marker_color_kwargs, marker_color_kwargs


@dataclass(frozen=True)
class BrokenAxisRendererContext:
    draw_break_marks: Callable[..., None]
    marker_tokens: Callable[..., tuple[float, float, float | None]]
    scatter_marker_area: Callable[[float], float]
    series_style: Callable[[Any, int, object], dict[str, object]]
    display_label: Callable[..., str]
    normalized_point_label_options: Callable[[Any], dict[str, object]]
    point_label_candidates: Callable[..., tuple[list[dict[str, object]], list[dict[str, object]]]]
    draw_point_label: Callable[..., None]
    record_point_label_skips: Callable[..., None]
    apply_legend: Callable[..., None]


def make_broken_y_axes(
    fig,
    points: list[dict],
    break_range: tuple[float, float] | None,
    *,
    context: BrokenAxisRendererContext,
):
    if break_range is None:
        raise ValueError("y_break_range is required for broken-axis rendering")
    left, bottom, width, height = [0.125, 0.11, 0.775, 0.77]
    gap_fraction = 0.02
    top_h = height * 0.5 - gap_fraction / 2
    bot_h = height * 0.5 - gap_fraction / 2
    ax_top = fig.add_axes([left, bottom + bot_h + gap_fraction, width, top_h])
    ax_bot = fig.add_axes([left, bottom, width, bot_h], sharex=ax_top)

    break_start, break_end = break_range
    ys = [float(point["y"]) for point in points]
    y_max = max(ys) if ys else break_end
    y_min = min(ys) if ys else break_start
    full_range = max(y_max - y_min, abs(break_end - break_start), 1e-6)
    margin = full_range * 0.05

    ax_top.set_ylim(break_end - margin, y_max + margin)
    ax_bot.set_ylim(y_min - margin, break_start + margin)
    ax_top.spines["bottom"].set_visible(False)
    ax_bot.spines["top"].set_visible(False)
    ax_top.tick_params(labelbottom=False, bottom=False)
    ax_bot.tick_params(top=False)
    context.draw_break_marks(ax_top, ax_bot, style="diagonal")
    return ax_top, ax_bot


def draw_grouped_broken_xy(
    ax_top,
    ax_bot,
    points: list[dict],
    spec: Any,
    *,
    line: bool,
    context: BrokenAxisRendererContext,
) -> None:
    grouped = group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)
    legend_entries: list[tuple[str, str]] = []

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

        draw_broken_xy_series(ax_top, xs, ys, yerr, sty, label=legend_label, spec=spec, line=line, context=context)
        draw_broken_xy_series(ax_bot, xs, ys, yerr, sty, label="_nolegend_", spec=spec, line=line, context=context)

    if spec.label_column:
        annotate_broken_axis_points(ax_top, ax_bot, points, spec, context=context)
    if has_multi_series:
        ax_top._graph_hub_legend_entries = legend_entries
        context.apply_legend(ax_top, spec, n_series=len(grouped))


def draw_broken_xy_series(
    ax,
    xs,
    ys,
    yerr,
    sty: dict,
    *,
    label: str | None,
    spec: Any,
    line: bool,
    context: BrokenAxisRendererContext,
) -> None:
    cap_size = spec.yerr_cap_width
    cap_thick = max(0.5, spec.yerr_cap_width * 0.4)
    marker_size, marker_edge_width, _marker_margin = context.marker_tokens(spec)
    series_marker_size = float(sty.get("size", marker_size))
    series_scatter_size = float(sty.get("size", context.scatter_marker_area(marker_size)))
    series_linewidth = float(sty.get("linewidth", 1.2))
    line_marker = str(sty.get("marker") if sty.get("_marker_overridden") else "none")
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
                label=label,
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
                label=label,
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
            label=label,
        )
    else:
        ax.scatter(
            xs,
            ys,
            s=series_scatter_size,
            marker=sty["marker"],
            linewidths=marker_edge_width,
            **marker_color_kwargs(sty),
            label=label,
        )


def annotate_broken_axis_points(
    ax_top,
    ax_bot,
    series_points: list[dict],
    spec: Any,
    *,
    context: BrokenAxisRendererContext,
) -> None:
    break_start, break_end = spec.y_break_range or (float("-inf"), float("inf"))
    options = context.normalized_point_label_options(spec)
    candidates, skipped = context.point_label_candidates(
        [point["x"] for point in series_points],
        [point["y"] for point in series_points],
        [str(point["label"]) for point in series_points],
        options=options,
        points=series_points,
    )
    for display_index, item in enumerate(candidates):
        y = float(item["y"])
        target = ax_top
        if y <= break_start:
            target = ax_bot
        elif break_start < y < break_end:
            target = ax_top if abs(y - break_end) < abs(y - break_start) else ax_bot
        context.draw_point_label(
            target,
            item,
            options=options,
            display_index=display_index,
            compress_labels=spec.compress_labels,
        )
    if skipped:
        context.record_point_label_skips(ax_top, skipped=skipped, total=len(series_points), shown=len(candidates))
