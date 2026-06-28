from __future__ import annotations

from typing import Any

from themes.style_profiles import get_render_style_tokens


def render_box_plot(ax: Any, points: list[dict], spec: Any) -> None:
    from plotting.common_plots import plot_box_with_points

    plot_box_with_points(
        _points_to_distribution_frame(points, spec),
        spec.x_column,
        spec.y_column,
        ax=ax,
        category_order=spec.category_order or None,
    )


def render_violin_plot(ax: Any, points: list[dict], spec: Any) -> None:
    from plotting.common_plots import plot_violin_with_points

    tokens, _meta = get_render_style_tokens(spec.target_format, spec.profile_name)
    plot_violin_with_points(
        _points_to_distribution_frame(points, spec),
        spec.x_column,
        spec.y_column,
        ax=ax,
        category_order=spec.category_order or None,
        kde_points=tokens["violin_kde_points"],
        kde_bw_method=tokens["violin_kde_bw_method"],
        violin_width=tokens["violin_width"],
    )


def _points_to_distribution_frame(points: list[dict], spec: Any):
    import pandas as pd

    return pd.DataFrame(
        {
            spec.x_column: [point["x"] for point in points],
            spec.y_column: [point["y"] for point in points],
        }
    )
