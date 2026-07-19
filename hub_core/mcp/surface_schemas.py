"""Public FigOps discovery metadata derived from live registries."""

from __future__ import annotations

from typing import Any

from hub_core.data_contract import SEMANTIC_CHECK_DEFINITIONS
from hub_core.rendering import PLOT_TYPES
from themes.style_profiles import DEFAULT_PROFILE


def supported_render_plot_types() -> list[str]:
    return sorted(PLOT_TYPES)


def _plot_type_example(name: str, arg_schema: dict[str, Any]) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "data_path": "/path/to/data.csv",
        "x_column": "x",
        "y_column": "y",
        "plot_type": name,
        "target_format": "nature",
        "profile": DEFAULT_PROFILE,
        "output_format": "png",
        "job_id": f"example-{name}",
    }
    if "z_column" in arg_schema.get("required", []):
        arguments["z_column"] = "z"
    if "facet_column" in arg_schema.get("required", []):
        arguments["facet_column"] = "facet"
    if "facet_order" in arg_schema.get("properties", {}):
        arguments["facet_order"] = ["control", "treated"]
    if "facet_ncols" in arg_schema.get("properties", {}):
        arguments["facet_ncols"] = 2
    if "annotate_values" in arg_schema.get("properties", {}):
        arguments["annotate_values"] = True
    return {"tool": "figops.render_csv_graph", "arguments": arguments}


def list_plot_type_descriptions() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "arg_schema": dict(plot_type.arg_schema),
            "capabilities": dict(plot_type.capabilities),
            "worked_example": _plot_type_example(name, plot_type.arg_schema),
        }
        for name, plot_type in sorted(PLOT_TYPES.items())
    ]


def list_semantic_check_descriptions() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "purpose": definition["purpose"],
            "schema": definition["schema"],
            "example": definition["example"],
        }
        for name, definition in sorted(SEMANTIC_CHECK_DEFINITIONS.items())
    ]
