import tempfile
from pathlib import Path

from matplotlib.axes import Axes

from hub_core.mcp.schemas import list_tool_definitions
from hub_core.mcp.transport import _validate_tool_arguments
from hub_core.rendering import PLOT_TYPES, PlotType
from plotting.bridge_renderer import BridgeFigureSpec


def _noop_render(ax: Axes, points: list[dict], spec: BridgeFigureSpec) -> None:
    ax.set_title(spec.title)


def test_registered_plot_type_updates_mcp_schema_and_validator():
    original = dict(PLOT_TYPES)
    try:
        PLOT_TYPES["test_plugin"] = PlotType(
            name="test_plugin",
            render=_noop_render,
            arg_schema={"type": "object", "properties": {"custom": {"type": "string"}}},
            capabilities={
                "supports_series": False,
                "supports_yerr": False,
                "supports_broken_axis": False,
            },
        )

        definitions = list_tool_definitions()
        render_tool = next(tool for tool in definitions if tool["name"] == "graphhub.render_csv_graph")
        plot_type_enum = render_tool["inputSchema"]["properties"]["plot_type"]["enum"]

        assert "test_plugin" in plot_type_enum

        with tempfile.TemporaryDirectory(prefix="graphhub_plot_registry_") as tmpdir:
            data_path = Path(tmpdir) / "data.csv"
            data_path.write_text("x,y\n1,2\n", encoding="utf-8")
            errors = _validate_tool_arguments(
                "graphhub.render_csv_graph",
                {
                    "data_path": str(data_path),
                    "x_column": "x",
                    "y_column": "y",
                    "plot_type": "test_plugin",
                },
                definitions,
            )

        assert errors == []
    finally:
        PLOT_TYPES.clear()
        PLOT_TYPES.update(original)


def test_builtin_plot_types_registered():
    assert {"bar", "line", "scatter", "xy", "heatmap"}.issubset(PLOT_TYPES)
