from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from plotting.bridge_renderer import BridgeFigureSpec
else:
    Axes = Any
    BridgeFigureSpec = Any

Point = dict[str, Any]
PlotRender = Callable[[Axes, list[Point], BridgeFigureSpec], None]


@dataclass(frozen=True)
class PlotType:
    name: str
    render: PlotRender
    arg_schema: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


class RenderBackend(Protocol):
    def render_plot(self, ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None: ...


@dataclass(frozen=True)
class MatplotlibRenderBackend:
    plot_types: dict[str, PlotType]

    def render_plot(self, ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
        plot_type = str(spec.plot_type or "line").strip().lower()
        self.plot_types[plot_type].render(ax, points, spec)


def _common_capabilities(**overrides: Any) -> dict[str, Any]:
    capabilities = {
        "supports_series": True,
        "supports_yerr": True,
        "supports_broken_axis": False,
    }
    capabilities.update(overrides)
    return capabilities


def _render_bar(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    from plotting.bridge_renderer import _render_bar_plot

    _render_bar_plot(ax, points, spec)


def _render_line(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    from plotting.bridge_renderer import _render_xy_plot

    _render_xy_plot(ax, points, spec, line=True)


def _render_scatter(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    from plotting.bridge_renderer import _render_xy_plot

    _render_xy_plot(ax, points, spec, line=False)


def _render_heatmap(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    if not spec.z_column:
        raise ValueError("heatmap requires z_column")
    from plotting.bridge_renderer import _render_heatmap_plot

    _render_heatmap_plot(ax, points, spec)


def _render_box(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    from plotting.bridge_renderer import _render_box_plot

    _render_box_plot(ax, points, spec)


def _render_violin(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    from plotting.bridge_renderer import _render_violin_plot

    _render_violin_plot(ax, points, spec)


def _render_facet(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    from plotting.bridge_renderer import _render_facet_plot

    _render_facet_plot(ax, points, spec)


_DISTRIBUTION_ARG_SCHEMA = {
    "type": "object",
    "required": ["x_column", "y_column"],
    "properties": {
        "x_column": {"type": "string"},
        "y_column": {"type": "string"},
        "category_order": {"type": "array", "items": {"type": ["string", "number"]}},
    },
}


_STATISTICAL_OVERLAY_ARG_SCHEMA = {
    "type": "object",
    "properties": {
        "fit_line": {"type": "boolean"},
        "ci_band": {"type": "boolean"},
        "significance_markers": {"type": "array"},
    },
}


_BAR_ARG_SCHEMA = {
    "type": "object",
    "properties": {
        "aggregate": {"type": "string", "enum": ["mean", "median"]},
        "category_order": {"type": "array", "items": {"type": ["string", "number"]}},
    },
}


_FACET_ARG_SCHEMA = {
    "type": "object",
    "required": ["facet_column"],
    "properties": {
        "facet_column": {"type": "string"},
        "facet_scales": {"type": "string", "enum": ["fixed", "free"]},
        "facet_order": {"type": "array", "items": {"type": "string"}},
    },
}


PLOT_TYPES: dict[str, PlotType] = {
    "bar": PlotType(
        name="bar",
        render=_render_bar,
        arg_schema=_BAR_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_broken_axis=False,
            supports_replicate_aggregation=True,
            supports_category_order=True,
            aggregate_methods=["mean", "median"],
        ),
    ),
    "line": PlotType(
        name="line",
        render=_render_line,
        arg_schema=_STATISTICAL_OVERLAY_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_broken_axis=True,
            supports_statistical_overlays=True,
            supports_fit_line=True,
            supports_ci_band=True,
            supports_significance_markers=True,
        ),
    ),
    "scatter": PlotType(
        name="scatter",
        render=_render_scatter,
        arg_schema=_STATISTICAL_OVERLAY_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_broken_axis=True,
            supports_statistical_overlays=True,
            supports_fit_line=True,
            supports_ci_band=True,
            supports_significance_markers=True,
        ),
    ),
    "xy": PlotType(
        name="xy",
        render=_render_line,
        arg_schema=_STATISTICAL_OVERLAY_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_broken_axis=True,
            supports_statistical_overlays=True,
            supports_fit_line=True,
            supports_ci_band=True,
            supports_significance_markers=True,
        ),
    ),
    "heatmap": PlotType(
        name="heatmap",
        render=_render_heatmap,
        arg_schema={"type": "object", "required": ["z_column"]},
        capabilities=_common_capabilities(
            supports_series=False,
            supports_yerr=False,
            supports_broken_axis=False,
            supports_z=True,
        ),
    ),
    "box": PlotType(
        name="box",
        render=_render_box,
        arg_schema=_DISTRIBUTION_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_series=False,
            supports_yerr=False,
            supports_broken_axis=False,
            shows_individual_points=True,
            warns_small_n=True,
            supports_category_order=True,
        ),
    ),
    "violin": PlotType(
        name="violin",
        render=_render_violin,
        arg_schema=_DISTRIBUTION_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_series=False,
            supports_yerr=False,
            supports_broken_axis=False,
            shows_individual_points=True,
            warns_small_n=True,
            falls_back_for_small_n=True,
            supports_category_order=True,
        ),
    ),
    "facet": PlotType(
        name="facet",
        render=_render_facet,
        arg_schema=_FACET_ARG_SCHEMA,
        capabilities=_common_capabilities(
            supports_broken_axis=False,
            supports_faceting=True,
            base_plot_type="line",
            shares_axes=True,
            default_scales="fixed",
            free_scales=True,
            supports_facet_order=True,
        ),
    ),
}

default_backend = MatplotlibRenderBackend(PLOT_TYPES)


def render_plot(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    default_backend.render_plot(ax, points, spec)
