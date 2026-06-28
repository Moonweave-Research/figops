from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from plotting.renderers.common import resolve_explicit_order


@dataclass(frozen=True)
class FacetRendererContext:
    render_xy_plot: Callable[..., None]
    display_label: Callable[..., str]
    marker_tokens: Callable[..., tuple[float, float, float | None]]
    apply_facet_headroom: Callable[[object, Any], None]


def render_facet_plot(ax, points: list[dict], spec: Any, *, context: FacetRendererContext) -> None:
    if not spec.facet_column:
        raise ValueError("facet plot_type requires facet_column")
    if spec.facet_scales not in {"fixed", "free"}:
        raise ValueError("facet_scales must be 'fixed' or 'free'")
    if not points:
        warnings.warn(
            f"bridge_renderer: no valid data points for {spec.title!r}, figure will be blank",
            stacklevel=2,
        )
        return

    fig = ax.figure
    ax.set_visible(False)
    grouped = group_facet_points(points)
    facet_names = resolve_explicit_order(
        list(grouped),
        spec.facet_order,
        field_name="facet_order",
    )
    n_facets = len(facet_names)
    n_rows, n_cols = resolve_facet_grid(n_facets, spec)
    shared_x = None
    shared_y = None
    share_axes = spec.facet_scales == "fixed"
    facet_axes = []

    for idx, facet_name in enumerate(facet_names):
        facet_points = grouped[str(facet_name)]
        row_idx = idx // n_cols
        col_idx = idx % n_cols
        facet_ax = fig.add_subplot(
            n_rows,
            n_cols,
            idx + 1,
            sharex=shared_x if share_axes else None,
            sharey=shared_y if share_axes else None,
        )
        facet_axes.append(facet_ax)
        if share_axes and shared_x is None:
            shared_x = facet_ax
            shared_y = facet_ax
        context.render_xy_plot(facet_ax, facet_points, spec, line=True, small_panel=True)
        facet_ax.set_title(context.display_label(facet_name, compress_labels=spec.compress_labels))
        if row_idx == n_rows - 1:
            facet_ax.set_xlabel(spec.x_axis_label or spec.x_column)
        else:
            facet_ax.set_xlabel("")
            facet_ax.tick_params(labelbottom=False)
        if col_idx == 0:
            facet_ax.set_ylabel(spec.y_axis_label or spec.y_column)
        else:
            facet_ax.set_ylabel("")
        if facet_ax.get_legend() is not None:
            facet_ax.get_legend().remove()

    if share_axes and (spec.facet_ncols is not None or spec.facet_nrows is not None or n_cols > 3):
        expand_shared_facet_limits_for_markers(facet_axes, spec, context=context)

    if spec.title:
        fig.suptitle(spec.title)
    context.apply_facet_headroom(fig, spec)


def resolve_facet_grid(n_facets: int, spec: Any) -> tuple[int, int]:
    n_cols = optional_positive_int(spec.facet_ncols, "facet_ncols")
    n_rows = optional_positive_int(spec.facet_nrows, "facet_nrows")
    if n_cols is not None and n_rows is not None:
        if n_cols * n_rows < n_facets:
            raise ValueError(f"facet_ncols * facet_nrows must hold {n_facets} facets; got {n_cols} * {n_rows}.")
        return n_rows, n_cols
    if n_cols is not None:
        return math.ceil(n_facets / n_cols), n_cols
    if n_rows is not None:
        return n_rows, math.ceil(n_facets / n_rows)

    auto_cols = min(5, max(1, math.ceil(math.sqrt(n_facets))))
    auto_rows = math.ceil(n_facets / auto_cols)
    if auto_rows > 5:
        warnings.warn(
            f"bridge_renderer: automatic facet grid has {auto_rows} rows for {n_facets} facets; "
            "set facet_ncols/facet_nrows to control large layouts",
            stacklevel=2,
        )
    return auto_rows, auto_cols


def optional_positive_int(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def expand_shared_facet_limits_for_markers(axes, spec: Any, *, context: FacetRendererContext) -> None:
    _marker_size, _marker_edge_width, margin = context.marker_tokens(spec, small_panel=True)
    if margin is None or not axes:
        return
    margin *= 3.0
    x_min, x_max = axes[0].get_xlim()
    y_min, y_max = axes[0].get_ylim()
    x_span = x_max - x_min
    y_span = y_max - y_min
    if x_span > 0:
        axes[0].set_xlim(x_min - x_span * margin, x_max + x_span * margin)
    if y_span > 0:
        axes[0].set_ylim(y_min - y_span * margin, y_max + y_span * margin)


def group_facet_points(points: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for point in points:
        key = str(point.get("facet") or "")
        grouped.setdefault(key, []).append(point)
    return grouped
