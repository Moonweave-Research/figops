import tempfile
from pathlib import Path

from matplotlib.axes import Axes

from hub_core.mcp.schemas import describe_figops_surface, list_tool_definitions
from hub_core.mcp.transport import _validate_tool_arguments
from hub_core.rendering import PLOT_TYPES, PlotType
from plotting.bridge_renderer import BridgeFigureSpec

CATEGORY_ORDER_SCHEMA = {"type": "array", "items": {"type": ["string", "number"]}}
FACET_ORDER_SCHEMA = {"type": "array", "items": {"type": "string"}}


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
        render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_graph")
        plot_type_enum = render_tool["inputSchema"]["properties"]["plot_type"]["enum"]

        assert "test_plugin" in plot_type_enum

        with tempfile.TemporaryDirectory(prefix="graphhub_plot_registry_") as tmpdir:
            data_path = Path(tmpdir) / "data.csv"
            data_path.write_text("x,y\n1,2\n", encoding="utf-8")
            errors = _validate_tool_arguments(
                "figops.render_csv_graph",
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

        surface = describe_figops_surface()
        described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}

        assert "test_plugin" in described
        assert described["test_plugin"]["arg_schema"] == PLOT_TYPES["test_plugin"].arg_schema
        assert described["test_plugin"]["capabilities"] == PLOT_TYPES["test_plugin"].capabilities
        assert described["test_plugin"]["worked_example"]["tool"] == "figops.render_csv_graph"
        assert described["test_plugin"]["worked_example"]["arguments"]["plot_type"] == "test_plugin"
    finally:
        PLOT_TYPES.clear()
        PLOT_TYPES.update(original)


def test_describe_lists_every_registered_plot_type_with_contracts():
    surface = describe_figops_surface()
    described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}

    assert set(described) == set(PLOT_TYPES)
    for name, plot_type in PLOT_TYPES.items():
        assert described[name]["arg_schema"] == plot_type.arg_schema
        assert described[name]["capabilities"] == plot_type.capabilities
        assert described[name]["worked_example"]["arguments"]["plot_type"] == name


def test_described_tool_set_matches_live_tool_registry():
    surface = describe_figops_surface()
    described_tools = {tool["name"]: tool for tool in surface["tools"]}
    live_tools = {tool["name"]: tool for tool in list_tool_definitions()}

    assert described_tools.keys() == live_tools.keys()
    for name, tool in live_tools.items():
        assert described_tools[name]["purpose"] == tool["description"]
        assert described_tools[name]["inputSchema"] == tool["inputSchema"]
        assert described_tools[name]["outputSchema"] == tool["outputSchema"]


def test_builtin_plot_types_registered():
    assert {"bar", "line", "scatter", "xy", "heatmap", "box", "violin", "facet"}.issubset(PLOT_TYPES)


def test_bar_plot_type_publishes_aggregate_contract():
    assert PLOT_TYPES["bar"].arg_schema == {
        "type": "object",
        "properties": {
            "aggregate": {"type": "string", "enum": ["mean", "median"]},
            "bar_error_column": {"type": "string"},
            "category_order": CATEGORY_ORDER_SCHEMA,
        },
    }
    assert PLOT_TYPES["bar"].capabilities["supports_replicate_aggregation"] is True
    assert PLOT_TYPES["bar"].capabilities["aggregate_methods"] == ["mean", "median"]
    assert PLOT_TYPES["bar"].capabilities["supports_category_order"] is True
    assert PLOT_TYPES["bar"].capabilities["supports_single_series_error_column"] is True


def test_describe_surfaces_bar_aggregate_arg():
    surface = describe_figops_surface()
    described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}

    assert described["bar"]["arg_schema"]["properties"]["aggregate"] == {
        "type": "string",
        "enum": ["mean", "median"],
    }
    assert described["bar"]["arg_schema"]["properties"]["bar_error_column"] == {"type": "string"}
    assert described["bar"]["arg_schema"]["properties"]["category_order"] == CATEGORY_ORDER_SCHEMA
    assert described["bar"]["capabilities"]["supports_replicate_aggregation"] is True
    assert described["bar"]["capabilities"]["supports_category_order"] is True
    assert described["bar"]["capabilities"]["supports_single_series_error_column"] is True
    assert described["bar"]["worked_example"]["arguments"]["aggregate"] == "mean"
    assert described["bar"]["worked_example"]["arguments"]["bar_error_column"] == "sem"
    assert described["bar"]["worked_example"]["arguments"]["category_order"] == ["day 0", "day 7", "day 14", "day 28"]


def test_render_csv_schema_accepts_bar_aggregate_arg():
    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_graph")
    assert render_tool["inputSchema"]["properties"]["aggregate"] == {
        "type": "string",
        "enum": ["mean", "median"],
    }
    assert render_tool["inputSchema"]["properties"]["bar_error_column"] == {"type": "string"}
    assert render_tool["inputSchema"]["properties"]["category_order"] == CATEGORY_ORDER_SCHEMA

    with tempfile.TemporaryDirectory(prefix="graphhub_bar_aggregate_schema_") as tmpdir:
        data_path = Path(tmpdir) / "bar.csv"
        data_path.write_text("x,y,sem\nA,1,0.1\nA,3,0.2\nB,2,0.3\nB,4,0.4\n", encoding="utf-8")
        errors = _validate_tool_arguments(
            "figops.render_csv_graph",
            {
                "data_path": str(data_path),
                "x_column": "x",
                "y_column": "y",
                "plot_type": "bar",
                "aggregate": "mean",
                "bar_error_column": "sem",
                "category_order": ["A", "B"],
            },
            definitions,
        )

    assert errors == []


def test_heatmap_plot_type_publishes_annotation_contract():
    assert PLOT_TYPES["heatmap"].arg_schema == {
        "type": "object",
        "required": ["z_column"],
        "properties": {"annotate_values": {"type": "boolean", "default": False}},
    }
    assert PLOT_TYPES["heatmap"].capabilities["supports_value_annotations"] is True

    surface = describe_figops_surface()
    described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}
    assert described["heatmap"]["arg_schema"]["properties"]["annotate_values"] == {
        "type": "boolean",
        "default": False,
    }
    assert described["heatmap"]["capabilities"]["supports_value_annotations"] is True
    assert described["heatmap"]["worked_example"]["arguments"]["annotate_values"] is True

    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_graph")
    assert render_tool["inputSchema"]["properties"]["annotate_values"] == {"type": "boolean", "default": False}


def test_distribution_plot_types_publish_contracts():
    assert PLOT_TYPES["box"].arg_schema == {
        "type": "object",
        "required": ["x_column", "y_column"],
        "properties": {
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
            "category_order": CATEGORY_ORDER_SCHEMA,
        },
    }
    assert PLOT_TYPES["box"].capabilities == {
        "supports_series": False,
        "supports_yerr": False,
        "supports_broken_axis": False,
        "shows_individual_points": True,
        "warns_small_n": True,
        "supports_category_order": True,
    }
    assert PLOT_TYPES["violin"].arg_schema == PLOT_TYPES["box"].arg_schema
    assert PLOT_TYPES["violin"].capabilities == {
        "supports_series": False,
        "supports_yerr": False,
        "supports_broken_axis": False,
        "shows_individual_points": True,
        "warns_small_n": True,
        "falls_back_for_small_n": True,
        "supports_category_order": True,
    }


def test_facet_plot_type_publishes_contract():
    assert PLOT_TYPES["facet"].arg_schema == {
        "type": "object",
        "required": ["facet_column"],
        "properties": {
            "facet_column": {"type": "string"},
            "facet_scales": {"type": "string", "enum": ["fixed", "free"]},
            "facet_order": FACET_ORDER_SCHEMA,
            "facet_ncols": {"type": "integer", "minimum": 1},
            "facet_nrows": {"type": "integer", "minimum": 1},
        },
    }
    assert PLOT_TYPES["facet"].capabilities == {
        "supports_series": True,
        "supports_yerr": True,
        "supports_broken_axis": False,
        "supports_faceting": True,
        "base_plot_type": "line",
        "shares_axes": True,
        "default_scales": "fixed",
        "free_scales": True,
        "supports_facet_order": True,
        "supports_facet_grid_shape": True,
    }



def test_render_csv_schema_accepts_axis_scale_series_and_annotations_args():
    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_graph")
    properties = render_tool["inputSchema"]["properties"]
    assert properties["x_scale"] == {"type": "string", "enum": ["linear", "log"], "default": "linear"}
    assert properties["y_scale"] == {"type": "string", "enum": ["linear", "log"], "default": "linear"}
    assert properties["series_column"] == {"type": "string"}
    assert properties["label_column"] == {"type": "string"}
    assert properties["point_label_options"]["additionalProperties"] is False
    point_label_props = properties["point_label_options"]["properties"]
    assert point_label_props["offset"]["required"] == ["dx", "dy"]
    assert point_label_props["fanout"] == {"type": "string", "enum": ["none", "compass"], "default": "none"}
    assert point_label_props["max_labels"] == {"type": "integer", "minimum": 1}
    assert point_label_props["priority_column"] == {"type": "string"}
    assert point_label_props["skip_column"] == {"type": "string"}
    assert properties["series_styles"]["additionalProperties"]["additionalProperties"] is False
    series_style_props = properties["series_styles"]["additionalProperties"]["properties"]
    assert "markeredgecolor" in series_style_props
    assert series_style_props["color"] == {"type": "string"}
    assert series_style_props["alpha"] == {"type": ["number", "string"]}
    assert series_style_props["size"] == {"type": ["number", "string"]}
    assert series_style_props["linewidth"] == {"type": ["number", "string"]}
    assert series_style_props["zorder"] == {"type": ["number", "string"]}
    assert series_style_props["label"] == {"type": "string"}
    annotation_branches = properties["annotations"]["items"]["anyOf"]
    assert [branch["required"] for branch in annotation_branches] == [
        ["x", "y", "text"],
        ["x", "y", "arrow_to"],
        ["region"],
        ["hspan"],
        ["vspan"],
    ]
    point_annotation_props = annotation_branches[0]["properties"]
    region_annotation_props = annotation_branches[2]["properties"]
    assert point_annotation_props["arrow_to"]["required"] == ["x", "y"]
    assert point_annotation_props["xytext_offset"]["required"] == ["dx", "dy"]
    assert point_annotation_props["placement_preset"]["enum"] == [
        "above",
        "below",
        "left",
        "right",
        "upper_left",
        "upper_right",
        "lower_left",
        "lower_right",
    ]
    assert point_annotation_props["avoid_overlap"] == {"type": "boolean", "default": False}
    assert "xytext_offset" not in region_annotation_props
    assert "placement_preset" not in region_annotation_props
    assert "avoid_overlap" not in region_annotation_props
    assert properties["guide_curves"]["items"]["anyOf"] == [{"required": ["points"]}, {"required": ["x", "y"]}]
    assert properties["fill_between"]["items"]["anyOf"] == [
        {"required": ["points"]},
        {"required": ["x_column", "y1_column", "y2_column"]},
    ]
    assert properties["yerr_column"] == {"type": "string"}
    assert properties["yerr_minus_column"] == {"type": "string"}
    assert properties["yerr_cap_width"] == {"type": "number", "minimum": 0, "default": 3.0}

    with tempfile.TemporaryDirectory(prefix="graphhub_series_annotation_schema_") as tmpdir:
        data_path = Path(tmpdir) / "series.csv"
        data_path.write_text("x,y,yerr_lo,yerr_hi,condition\n1,10,1,2,A\n2,100,3,4,B\n", encoding="utf-8")
        errors = _validate_tool_arguments(
            "figops.render_csv_graph",
            {
                "data_path": str(data_path),
                "x_column": "x",
                "y_column": "y",
                "series_column": "condition",
                "yerr_column": "yerr_hi",
                "yerr_minus_column": "yerr_lo",
                "yerr_cap_width": 2.5,
                "x_scale": "linear",
                "y_scale": "log",
                "annotations": [{"x": 2, "y": 100, "text": "callout"}],
                "guide_curves": [{"points": [{"x": 1, "y": 20}, {"x": 2, "y": 90}]}],
                "fill_between": [{"x_column": "x", "y1_column": "yerr_lo", "y2_column": "yerr_hi"}],
            },
            definitions,
        )

    assert errors == []

def test_render_csv_schema_accepts_facet_column_for_facet_plot_type():
    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_graph")
    assert render_tool["inputSchema"]["properties"]["facet_column"] == {"type": "string"}
    assert render_tool["inputSchema"]["properties"]["facet_scales"] == {
        "type": "string",
        "enum": ["fixed", "free"],
        "default": "fixed",
    }
    assert render_tool["inputSchema"]["properties"]["facet_order"] == FACET_ORDER_SCHEMA
    assert render_tool["inputSchema"]["properties"]["facet_ncols"] == {"type": "integer", "minimum": 1}
    assert render_tool["inputSchema"]["properties"]["facet_nrows"] == {"type": "integer", "minimum": 1}

    with tempfile.TemporaryDirectory(prefix="graphhub_facet_schema_") as tmpdir:
        data_path = Path(tmpdir) / "facet.csv"
        data_path.write_text("x,y,phase\n0,1,A\n1,2,A\n0,3,B\n1,4,B\n", encoding="utf-8")
        errors = _validate_tool_arguments(
            "figops.render_csv_graph",
            {
                "data_path": str(data_path),
                "x_column": "x",
                "y_column": "y",
                "facet_column": "phase",
                "facet_scales": "free",
                "facet_order": ["A", "B"],
                "facet_ncols": 2,
                "facet_nrows": 1,
                "plot_type": "facet",
            },
            definitions,
        )

    assert errors == []


def test_render_csv_multipanel_schema_accepts_panel_specs():
    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_multipanel")
    properties = render_tool["inputSchema"]["properties"]
    assert properties["panels"]["minItems"] == 1
    panel_properties = properties["panels"]["items"]["properties"]
    assert panel_properties["data_path"]["type"] == "string"
    assert panel_properties["x_scale"] == {"type": "string", "enum": ["linear", "log"], "default": "linear"}
    assert panel_properties["guide_curves"]["items"]["properties"]["points"]["items"]["required"] == ["x", "y"]
    assert panel_properties["fill_between"]["items"]["properties"]["points"]["items"]["required"] == ["x", "y1", "y2"]
    assert panel_properties["fit_line"] == {"type": "boolean"}
    assert panel_properties["ci_band"] == {"type": "boolean"}
    assert panel_properties["fit_options"]["properties"]["model"]["enum"] == ["linear"]
    assert panel_properties["significance_markers"] == {"type": "array", "items": {"type": "object"}}
    panel_annotation_branches = panel_properties["annotations"]["items"]["anyOf"]
    assert panel_annotation_branches[3]["properties"]["hspan"]["required"] == ["ymin", "ymax"]
    assert "xytext_offset" not in panel_annotation_branches[3]["properties"]
    assert panel_properties["series_styles"]["additionalProperties"]["properties"]["fill"]["enum"] == [
        "full",
        "filled",
        "none",
        "open",
    ]
    assert panel_properties["yerr_column"] == {"type": "string"}
    assert properties["compose_mode"] == {"type": "string", "enum": ["draft", "manuscript"], "default": "draft"}
    assert properties["font_scale"] == {"type": "number", "default": 1.0}

    with tempfile.TemporaryDirectory(prefix="graphhub_multipanel_schema_") as tmpdir:
        data_path = Path(tmpdir) / "panel.csv"
        data_path.write_text("x,y,sem\n1,10,1\n2,100,2\n", encoding="utf-8")
        errors = _validate_tool_arguments(
            "figops.render_csv_multipanel",
            {
                "panels": [
                    {
                        "data_path": str(data_path),
                        "x_column": "x",
                        "y_column": "y",
                        "plot_type": "scatter",
                        "x_scale": "log",
                        "yerr_column": "sem",
                        "fit_line": True,
                        "fit_options": {"model": "linear", "label": "Panel fit"},
                        "guide_curves": [{"x": [1, 2], "y": [12, 80]}],
                        "fill_between": [{"points": [{"x": 1, "y1": 9, "y2": 11}, {"x": 2, "y1": 95, "y2": 105}]}],
                    }
                ],
                "rows": 1,
                "cols": 1,
            },
            definitions,
        )

    assert errors == []


def test_xy_plot_types_publish_statistical_overlay_contracts():
    overlay_properties = {
        "fit_line": {"type": "boolean"},
        "ci_band": {"type": "boolean"},
        "fit_options": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "enum": ["linear"], "default": "linear"},
                "label": {"type": "string"},
                "color": {"type": "string"},
                "linestyle": {"type": "string"},
                "linewidth": {"type": "number", "exclusiveMinimum": 0},
                "zorder": {"type": "number"},
                "ci_alpha": {"type": "number", "minimum": 0, "maximum": 1},
                "ci_label": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "significance_markers": {"type": "array"},
    }
    for name in ("line", "scatter", "xy"):
        plot_type = PLOT_TYPES[name]
        assert plot_type.capabilities["supports_statistical_overlays"] is True
        assert plot_type.capabilities["supports_fit_line"] is True
        assert plot_type.capabilities["supports_ci_band"] is True
        assert plot_type.capabilities["supports_fit_options"] is True
        assert plot_type.capabilities["supports_significance_markers"] is True
        for key, schema in overlay_properties.items():
            assert plot_type.arg_schema["properties"][key] == schema


def test_describe_surfaces_statistical_overlay_args_for_xy_plot_types():
    surface = describe_figops_surface()
    described = {plot_type["name"]: plot_type for plot_type in surface["plot_types"]}

    for name in ("line", "scatter", "xy"):
        props = described[name]["arg_schema"]["properties"]
        assert props["fit_line"] == {"type": "boolean"}
        assert props["ci_band"] == {"type": "boolean"}
        assert props["fit_options"]["properties"]["model"]["enum"] == ["linear"]
        assert props["significance_markers"] == {"type": "array"}
        example_args = described[name]["worked_example"]["arguments"]
        assert example_args["fit_line"] is True
        assert example_args["ci_band"] is True
        assert example_args["fit_options"] == {"model": "linear", "label": "Linear fit"}
        assert example_args["significance_markers"][0]["label"] == "p<0.05"


def test_render_csv_schema_accepts_statistical_overlay_args():
    definitions = list_tool_definitions()
    render_tool = next(tool for tool in definitions if tool["name"] == "figops.render_csv_graph")
    properties = render_tool["inputSchema"]["properties"]
    assert properties["fit_line"] == {"type": "boolean"}
    assert properties["ci_band"] == {"type": "boolean"}
    assert properties["fit_options"]["properties"]["model"]["enum"] == ["linear"]
    assert properties["fit_options"]["additionalProperties"] is False
    panel_properties = next(tool for tool in definitions if tool["name"] == "figops.render_csv_multipanel")[
        "inputSchema"
    ]["properties"]["panels"]["items"]["properties"]
    assert panel_properties["fit_options"] == properties["fit_options"]
    assert properties["significance_markers"] == {"type": "array", "items": {"type": "object"}}

    with tempfile.TemporaryDirectory(prefix="graphhub_stat_overlay_schema_") as tmpdir:
        data_path = Path(tmpdir) / "overlay.csv"
        data_path.write_text("x,y\n0,1\n1,2\n2,3\n", encoding="utf-8")
        errors = _validate_tool_arguments(
            "figops.render_csv_graph",
            {
                "data_path": str(data_path),
                "x_column": "x",
                "y_column": "y",
                "plot_type": "scatter",
                "fit_line": True,
                "ci_band": True,
                "fit_options": {"model": "linear", "label": "Linear fit"},
                "significance_markers": [{"x1": 0, "x2": 2, "y": 3, "label": "p<0.05"}],
            },
            definitions,
        )

    assert errors == []
