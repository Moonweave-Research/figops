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


PLOT_TYPES: dict[str, PlotType] = {
    "bar": PlotType(
        name="bar",
        render=_render_bar,
        arg_schema={},
        capabilities=_common_capabilities(supports_broken_axis=False),
    ),
    "line": PlotType(
        name="line",
        render=_render_line,
        arg_schema={},
        capabilities=_common_capabilities(supports_broken_axis=True),
    ),
    "scatter": PlotType(
        name="scatter",
        render=_render_scatter,
        arg_schema={},
        capabilities=_common_capabilities(supports_broken_axis=True),
    ),
    "xy": PlotType(
        name="xy",
        render=_render_line,
        arg_schema={},
        capabilities=_common_capabilities(supports_broken_axis=True),
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
}

default_backend = MatplotlibRenderBackend(PLOT_TYPES)


def render_plot(ax: Axes, points: list[Point], spec: BridgeFigureSpec) -> None:
    default_backend.render_plot(ax, points, spec)
