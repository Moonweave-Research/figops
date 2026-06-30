from __future__ import annotations

from typing import Any

GEOMETRY_METRIC_NAMES = (
    "tick_label_overlaps",
    "tick_label_crowding",
    "artists_outside_axes",
    "artists_outside_figure",
    "legend_data_collision",
    "axis_label_title_overlap",
    "figure_title_panel_title_overlap",
    "colorbar_overlap",
    "blank_area_ratio",
    "point_annotation_overlaps",
    "artist_overlaps",
    "legend_internal_overlaps",
    "marker_marker_overlaps",
    "text_axis_edge_proximity",
    "legend_marker_consistency",
    "label_offset_consistency",
    "point_label_skips",
    "annotation_overlay_contrast",
    "font_size_token_drift",
    "journal_compliance",
)


GEOMETRY_DIAGNOSTICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "passed": {"type": ["boolean", "null"]},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": list(GEOMETRY_METRIC_NAMES)},
                    "passed": {"type": ["boolean", "null"]},
                    "detail": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["name", "passed", "detail"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["schema_version", "passed", "checks", "warnings"],
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
