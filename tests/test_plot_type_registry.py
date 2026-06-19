import tempfile
from pathlib import Path

from matplotlib.axes import Axes

from hub_core.mcp.schemas import describe_graphhub_surface, list_tool_definitions
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


def test_registered_plot_type_updates_describe_without_hand_edit():
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

        surface = describe_graphhub_surface()
        described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}

        assert "test_plugin" in described
        assert described["test_plugin"]["arg_schema"] == PLOT_TYPES["test_plugin"].arg_schema
        assert described["test_plugin"]["capabilities"] == PLOT_TYPES["test_plugin"].capabilities
        assert described["test_plugin"]["worked_example"]["tool"] == "graphhub.render_csv_graph"
        assert described["test_plugin"]["worked_example"]["arguments"]["plot_type"] == "test_plugin"
    finally:
        PLOT_TYPES.clear()
        PLOT_TYPES.update(original)


def test_describe_lists_every_registered_plot_type_with_contracts():
    surface = describe_graphhub_surface()
    described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}

    assert set(described) == set(PLOT_TYPES)
    for name, plot_type in PLOT_TYPES.items():
        assert described[name]["arg_schema"] == plot_type.arg_schema
        assert described[name]["capabilities"] == plot_type.capabilities
        assert described[name]["worked_example"]["arguments"]["plot_type"] == name


def test_described_tool_set_matches_live_tool_registry():
    surface = describe_graphhub_surface()
    described_tools = {tool["name"]: tool for tool in surface["tools"]}
    live_tools = {tool["name"]: tool for tool in list_tool_definitions()}

    assert described_tools.keys() == live_tools.keys()
    for name, tool in live_tools.items():
        assert described_tools[name]["purpose"] == tool["description"]
        assert described_tools[name]["inputSchema"] == tool["inputSchema"]
        assert described_tools[name]["outputSchema"] == tool["outputSchema"]


def test_builtin_plot_types_registered():
    assert {"bar", "line", "scatter", "xy", "heatmap", "box", "violin", "facet"}.issubset(PLOT_TYPES)


def test_distribution_plot_types_publish_contracts():
    assert PLOT_TYPES["box"].arg_schema == {
        "type": "object",
        "required": ["x_column", "y_column"],
        "properties": {
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
        },
    }
    assert PLOT_TYPES["box"].capabilities == {
        "supports_series": False,
        "supports_yerr": False,
        "supports_broken_axis": False,
        "shows_individual_points": True,
        "warns_small_n": True,
    }
    assert PLOT_TYPES["violin"].arg_schema == PLOT_TYPES["box"].arg_schema
    assert PLOT_TYPES["violin"].capabilities == {
        "supports_series": False,
        "supports_yerr": False,
        "supports_broken_axis": False,
        "shows_individual_points": True,
        "warns_small_n": True,
        "falls_back_for_small_n": True,
    }


def test_facet_plot_type_publishes_contract():
    assert PLOT_TYPES["facet"].arg_schema == {
        "type": "object",
        "required": ["facet_column"],
        "properties": {
            "facet_column": {"type": "string"},
        },
    }
    assert PLOT_TYPES["facet"].capabilities == {
        "supports_series": True,
        "supports_yerr": True,
        "supports_broken_axis": False,
        "supports_faceting": True,
        "base_plot_type": "line",
        "shares_axes": True,
    }


def test_render_csv_schema_accepts_facet_column_for_facet_plot_type():
    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "graphhub.render_csv_graph")
    assert render_tool["inputSchema"]["properties"]["facet_column"] == {"type": "string"}

    with tempfile.TemporaryDirectory(prefix="graphhub_facet_schema_") as tmpdir:
        data_path = Path(tmpdir) / "facet.csv"
        data_path.write_text("x,y,phase\n0,1,A\n1,2,A\n0,3,B\n1,4,B\n", encoding="utf-8")
        errors = _validate_tool_arguments(
            "graphhub.render_csv_graph",
            {
                "data_path": str(data_path),
                "x_column": "x",
                "y_column": "y",
                "facet_column": "phase",
                "plot_type": "facet",
            },
            definitions,
        )

    assert errors == []
