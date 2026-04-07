"""Y-axis break rendering for discontinuous data ranges."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes


def render_broken_y_axis(
    fig: plt.Figure,
    ax_position: list[float],
    x: np.ndarray,
    y: np.ndarray,
    break_range: tuple[float, float],
    *,
    plot_func: str = "scatter",
    break_style: str = "diagonal",
    height_ratio: tuple[float, float] = (1, 1),
    gap_fraction: float = 0.02,
    **plot_kwargs,
) -> tuple[Axes, Axes]:
    left, bottom, width, height = ax_position
    total_ratio = height_ratio[0] + height_ratio[1]
    top_h = height * (height_ratio[0] / total_ratio) - gap_fraction / 2
    bot_h = height * (height_ratio[1] / total_ratio) - gap_fraction / 2
    top_bottom = bottom + bot_h + gap_fraction
    bot_bottom = bottom

    ax_top = fig.add_axes([left, top_bottom, width, top_h])
    ax_bot = fig.add_axes([left, bot_bottom, width, bot_h], sharex=ax_top)

    break_start, break_end = break_range
    y_arr = np.asarray(y)
    x_arr = np.asarray(x)

    y_max = float(y_arr.max()) if len(y_arr) else break_end
    y_min = float(y_arr.min()) if len(y_arr) else break_start

    full_range = max(y_max - y_min, abs(break_end - break_start), 1e-6)
    margin_top = full_range * 0.05
    margin_bot = full_range * 0.05

    ax_top.set_ylim(break_end - margin_top, y_max + margin_top)
    ax_bot.set_ylim(y_min - margin_bot, break_start + margin_bot)

    if plot_func == "scatter":
        ax_top.scatter(x_arr, y_arr, **plot_kwargs)
        ax_bot.scatter(x_arr, y_arr, **plot_kwargs)
    else:
        ax_top.plot(x_arr, y_arr, **plot_kwargs)
        ax_bot.plot(x_arr, y_arr, **plot_kwargs)

    ax_top.spines["bottom"].set_visible(False)
    ax_bot.spines["top"].set_visible(False)
    ax_top.tick_params(labelbottom=False, bottom=False)
    ax_bot.tick_params(top=False)

    _draw_break_marks(ax_top, ax_bot, style=break_style)

    return ax_top, ax_bot


def _draw_break_marks(ax_top: Axes, ax_bot: Axes, style: str = "diagonal") -> None:
    d = 0.015

    kwargs_top = dict(transform=ax_top.transAxes, color="k", clip_on=False, linewidth=0.8)
    ax_top.plot((-d, +d), (-d, +d), **kwargs_top)
    ax_top.plot((1 - d, 1 + d), (-d, +d), **kwargs_top)

    kwargs_bot = dict(transform=ax_bot.transAxes, color="k", clip_on=False, linewidth=0.8)
    ax_bot.plot((-d, +d), (1 - d, 1 + d), **kwargs_bot)
    ax_bot.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs_bot)
