from __future__ import annotations

from typing import Any


def object_schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def open_object_schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
    }
    if required:
        schema["required"] = required
    return schema


NUMBER_OR_STRING_SCHEMA = {"type": ["number", "string"]}


OVERLAY_POINT_SCHEMA = open_object_schema(
    {
        "x": NUMBER_OR_STRING_SCHEMA,
        "y": NUMBER_OR_STRING_SCHEMA,
    },
    required=["x", "y"],
)

FILL_BETWEEN_POINT_SCHEMA = open_object_schema(
    {
        "x": NUMBER_OR_STRING_SCHEMA,
        "y1": NUMBER_OR_STRING_SCHEMA,
        "y2": NUMBER_OR_STRING_SCHEMA,
    },
    required=["x", "y1", "y2"],
)

ARROW_TARGET_SCHEMA = open_object_schema(
    {
        "x": NUMBER_OR_STRING_SCHEMA,
        "y": NUMBER_OR_STRING_SCHEMA,
    },
    required=["x", "y"],
)

REGION_ANNOTATION_BOUNDS_SCHEMA = open_object_schema(
    {
        "xmin": NUMBER_OR_STRING_SCHEMA,
        "xmax": NUMBER_OR_STRING_SCHEMA,
        "ymin": NUMBER_OR_STRING_SCHEMA,
        "ymax": NUMBER_OR_STRING_SCHEMA,
    },
    required=["xmin", "xmax", "ymin", "ymax"],
)

HSPAN_ANNOTATION_BOUNDS_SCHEMA = open_object_schema(
    {
        "ymin": NUMBER_OR_STRING_SCHEMA,
        "ymax": NUMBER_OR_STRING_SCHEMA,
    },
    required=["ymin", "ymax"],
)

VSPAN_ANNOTATION_BOUNDS_SCHEMA = open_object_schema(
    {
        "xmin": NUMBER_OR_STRING_SCHEMA,
        "xmax": NUMBER_OR_STRING_SCHEMA,
    },
    required=["xmin", "xmax"],
)

SERIES_STYLE_SCHEMA = object_schema(
    {
        "marker": {"type": "string"},
        "fill": {"type": "string", "enum": ["full", "filled", "none", "open"]},
        "facecolor": {"type": "string"},
        "edgecolor": {"type": "string"},
        "markerfacecolor": {"type": "string"},
        "markeredgecolor": {"type": "string"},
        "linestyle": {"type": "string"},
        "hatch": {"type": "string"},
        "color": {"type": "string"},
        "alpha": NUMBER_OR_STRING_SCHEMA,
        "size": NUMBER_OR_STRING_SCHEMA,
        "linewidth": NUMBER_OR_STRING_SCHEMA,
        "zorder": NUMBER_OR_STRING_SCHEMA,
        "label": {"type": "string"},
    }
)

SERIES_STYLES_SCHEMA = {
    "type": "object",
    "additionalProperties": SERIES_STYLE_SCHEMA,
    "description": "Per-series style overrides keyed by exact series label.",
}

SECONDARY_Y_SCHEMA = object_schema(
    {
        "enabled": {"type": "boolean", "default": True},
        "column": {"type": "string"},
        "axis_label": {"type": "string"},
        "scale": {"type": "string", "enum": ["linear", "log"], "default": "linear"},
        "series_label": {"type": "string"},
        "limits": object_schema({"min": NUMBER_OR_STRING_SCHEMA, "max": NUMBER_OR_STRING_SCHEMA}),
    }
)

CALLOUT_OFFSET_SCHEMA = open_object_schema(
    {"dx": NUMBER_OR_STRING_SCHEMA, "dy": NUMBER_OR_STRING_SCHEMA},
    required=["dx", "dy"],
)
CALLOUT_PLACEMENT_PRESET_SCHEMA = {
    "type": "string",
    "enum": [
        "above",
        "below",
        "left",
        "right",
        "upper_left",
        "upper_right",
        "lower_left",
        "lower_right",
    ],
}
POINT_LABEL_OPTIONS_SCHEMA = object_schema(
    {
        "offset": CALLOUT_OFFSET_SCHEMA,
        "fanout": {"type": "string", "enum": ["none", "compass"], "default": "none"},
        "max_labels": {"type": "integer", "minimum": 1},
        "priority_column": {"type": "string"},
        "skip_column": {"type": "string"},
    }
)
POINT_ANNOTATION_PROPERTIES = {
    "x": NUMBER_OR_STRING_SCHEMA,
    "y": NUMBER_OR_STRING_SCHEMA,
    "text": {"type": "string"},
    "arrow_to": ARROW_TARGET_SCHEMA,
    "arrowstyle": {"type": "string", "default": "->"},
    "connectionstyle": {"type": "string"},
    "xytext_offset": CALLOUT_OFFSET_SCHEMA,
    "placement_preset": CALLOUT_PLACEMENT_PRESET_SCHEMA,
    "avoid_overlap": {"type": "boolean", "default": False},
    "color": {"type": "string", "default": "black"},
}
REGION_ANNOTATION_PROPERTIES = {
    "region": REGION_ANNOTATION_BOUNDS_SCHEMA,
    "text": {"type": "string"},
    "color": {"type": "string", "default": "black"},
    "alpha": NUMBER_OR_STRING_SCHEMA,
}
HSPAN_ANNOTATION_PROPERTIES = {
    "hspan": HSPAN_ANNOTATION_BOUNDS_SCHEMA,
    "text": {"type": "string"},
    "color": {"type": "string", "default": "black"},
    "alpha": NUMBER_OR_STRING_SCHEMA,
}
VSPAN_ANNOTATION_PROPERTIES = {
    "vspan": VSPAN_ANNOTATION_BOUNDS_SCHEMA,
    "text": {"type": "string"},
    "color": {"type": "string", "default": "black"},
    "alpha": NUMBER_OR_STRING_SCHEMA,
}
ANNOTATION_SCHEMA = {
    "anyOf": [
        open_object_schema(POINT_ANNOTATION_PROPERTIES, required=["x", "y", "text"]),
        open_object_schema(POINT_ANNOTATION_PROPERTIES, required=["x", "y", "arrow_to"]),
        open_object_schema(REGION_ANNOTATION_PROPERTIES, required=["region"]),
        open_object_schema(HSPAN_ANNOTATION_PROPERTIES, required=["hspan"]),
        open_object_schema(VSPAN_ANNOTATION_PROPERTIES, required=["vspan"]),
    ],
}

ANNOTATIONS_SCHEMA = {
    "type": "array",
    "items": ANNOTATION_SCHEMA,
    "description": "Point text/callout annotations plus rectangular region, hspan, and vspan overlays.",
}
LEGEND_LAYOUT_SCHEMA = {
    "type": "string",
    "enum": ["auto", "smart", "standard", "best", "top_outside", "right_outside"],
    "default": "auto",
}

LEGEND_OPTIONS_SCHEMA = object_schema(
    {
        "title": {"type": "string"},
        "order": {"type": "array", "items": {"type": "string"}},
        "ncol": {"type": "integer", "minimum": 1, "maximum": 8},
    }
)

AXIS_LIMIT_PAIR_SCHEMA = object_schema(
    {
        "min": {"type": "number"},
        "max": {"type": "number"},
    }
)

AXIS_LIMITS_SCHEMA = object_schema(
    {
        "x": AXIS_LIMIT_PAIR_SCHEMA,
        "y": AXIS_LIMIT_PAIR_SCHEMA,
    }
)

TICK_STYLE_SCHEMA = object_schema(
    {
        "rotation": {"type": "number"},
        "format": {"type": "string", "enum": ["default", "plain", "scientific", "compact"]},
        "max_label_chars": {"type": "integer", "minimum": 4},
    }
)

MULTIPANEL_LAYOUT_OPTIONS_SCHEMA = object_schema(
    {
        "wspace": {"type": "number", "minimum": 0},
        "hspace": {"type": "number", "minimum": 0},
        "gutter_h_mm": {"type": "number", "minimum": 0},
        "gutter_v_mm": {"type": "number", "minimum": 0},
        "width_ratios": {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0}, "minItems": 1},
        "height_ratios": {"type": "array", "items": {"type": "number", "exclusiveMinimum": 0}, "minItems": 1},
    }
)

SHARED_LEGEND_OPTIONS_SCHEMA = object_schema(
    {
        "title": {"type": "string"},
        "order": {"type": "array", "items": {"type": "string"}},
        "ncol": {"type": "integer", "minimum": 1, "maximum": 8},
        "position": {"type": "string", "enum": ["top", "bottom", "right"], "default": "top"},
    }
)


GUIDE_CURVE_SCHEMA = {
    **open_object_schema(
        {
            "points": {"type": "array", "items": OVERLAY_POINT_SCHEMA, "minItems": 2},
            "x": {"type": "array", "items": NUMBER_OR_STRING_SCHEMA, "minItems": 2},
            "y": {"type": "array", "items": NUMBER_OR_STRING_SCHEMA, "minItems": 2},
            "color": {"type": "string", "default": "black"},
            "linestyle": {"type": "string"},
            "linewidth": NUMBER_OR_STRING_SCHEMA,
            "label": {"type": "string"},
            "zorder": NUMBER_OR_STRING_SCHEMA,
        }
    ),
    "anyOf": [{"required": ["points"]}, {"required": ["x", "y"]}],
}

GUIDE_CURVES_SCHEMA = {
    "type": "array",
    "items": GUIDE_CURVE_SCHEMA,
    "description": "Manual guide curves from point objects or parallel x/y arrays.",
}

FIT_OPTIONS_SCHEMA = object_schema(
    {
        "model": {"type": "string", "enum": ["linear"], "default": "linear"},
        "label": {"type": "string"},
        "color": {"type": "string"},
        "linestyle": {"type": "string"},
        "linewidth": {"type": "number", "exclusiveMinimum": 0},
        "zorder": {"type": "number"},
        "ci_alpha": {"type": "number", "minimum": 0, "maximum": 1},
        "ci_label": {"type": "string"},
    }
)

FILL_BETWEEN_SCHEMA = {
    **open_object_schema(
        {
            "points": {"type": "array", "items": FILL_BETWEEN_POINT_SCHEMA, "minItems": 2},
            "x_column": {"type": "string"},
            "y1_column": {"type": "string"},
            "y2_column": {"type": "string"},
            "color": {"type": "string"},
            "alpha": {"type": ["number", "string"], "default": 0.2},
            "label": {"type": "string"},
            "zorder": NUMBER_OR_STRING_SCHEMA,
        }
    ),
    "anyOf": [{"required": ["points"]}, {"required": ["x_column", "y1_column", "y2_column"]}],
}

FILL_BETWEEN_OVERLAYS_SCHEMA = {
    "type": "array",
    "items": FILL_BETWEEN_SCHEMA,
    "description": "Manual filled bands from point triplets or CSV x/y1/y2 columns.",
}
