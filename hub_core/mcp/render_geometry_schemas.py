from __future__ import annotations

from typing import Any

GEOMETRY_METRIC_NAMES = (
    "tick_label_overlaps",
    "artists_outside_axes",
    "artists_outside_figure",
    "legend_data_collision",
    "colorbar_overlap",
    "blank_area_ratio",
    "label_offset_consistency",
    "style_geometry_observations",
    "text_axis_edge_distances",
    "artist_pair_iou",
    "annotation_overlay_contrast_ratios",
)

LEGACY_GEOMETRY_METRIC_NAMES = (
    "tick_label_overlaps", "tick_label_crowding", "artists_outside_axes",
    "artists_outside_figure", "legend_data_collision", "axis_label_title_overlap",
    "figure_title_panel_title_overlap", "colorbar_overlap", "blank_area_ratio",
    "point_annotation_overlaps", "artist_overlaps", "legend_internal_overlaps",
    "marker_marker_overlaps", "text_axis_edge_proximity", "legend_marker_consistency",
    "label_offset_consistency", "point_label_skips", "annotation_overlay_contrast",
    "font_size_token_drift", "journal_compliance",
)


GEOMETRY_DIAGNOSTICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"const": "geometry_diagnostics/2"},
        "measurements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric_id": {"type": "string", "minLength": 1},
                    "availability": {"enum": ["available", "unavailable"]},
                    "value": {
                        "type": ["object", "array", "string", "number", "integer", "boolean", "null"]
                    },
                    "unit": {"type": "string", "minLength": 1},
                    "scope": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["metric_id", "availability", "unit", "scope"],
                "allOf": [
                    {
                        "if": {"properties": {"availability": {"const": "available"}}},
                        "then": {"required": ["value"], "not": {"required": ["reason"]}},
                        "else": {"required": ["reason"], "not": {"required": ["value"]}},
                    }
                ],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["schema_version", "measurements", "warnings"],
    "additionalProperties": False,
}


LAYOUT_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "passed": {"type": ["boolean", "null"]},
        "overlaps": {"type": "array", "items": {"type": "object"}},
        "clipped": {"type": "array", "items": {"type": "object"}},
        "font_roles": {"type": "object"},
        "placement_consistency": {"type": "array", "items": {"type": "object"}},
        "density": {"type": "object"},
        "render_errors": {"type": "array", "items": {"type": "object"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "schema_version",
        "passed",
        "overlaps",
        "clipped",
        "font_roles",
        "placement_consistency",
        "density",
        "render_errors",
        "warnings",
    ],
}
