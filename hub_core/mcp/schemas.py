from __future__ import annotations

from typing import Any

from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, PUBLIC_TARGET_FORMATS
from hub_core.domain_analysis import list_domain_helper_descriptions
from hub_core.mcp import tool_schema_common as _schema_common
from hub_core.mcp.discovery_schemas import list_prompt_definitions as _list_prompt_definitions
from hub_core.mcp.discovery_schemas import list_resource_definitions as _list_resource_definitions
from hub_core.mcp.discovery_schemas import list_resource_templates as _list_resource_templates
from hub_core.mcp.render_geometry_schemas import GEOMETRY_DIAGNOSTICS_SCHEMA as _GEOMETRY_DIAGNOSTICS_SCHEMA
from hub_core.mcp.render_geometry_schemas import GEOMETRY_METRIC_NAMES as _GEOMETRY_METRIC_NAMES  # noqa: F401
from hub_core.mcp.render_geometry_schemas import LAYOUT_REPORT_SCHEMA as _LAYOUT_REPORT_SCHEMA
from hub_core.mcp.render_input_schemas import ANNOTATIONS_SCHEMA as _ANNOTATIONS_SCHEMA
from hub_core.mcp.render_input_schemas import AXIS_LIMITS_SCHEMA as _AXIS_LIMITS_SCHEMA
from hub_core.mcp.render_input_schemas import FILL_BETWEEN_OVERLAYS_SCHEMA as _FILL_BETWEEN_OVERLAYS_SCHEMA
from hub_core.mcp.render_input_schemas import FIT_OPTIONS_SCHEMA as _FIT_OPTIONS_SCHEMA
from hub_core.mcp.render_input_schemas import GUIDE_CURVES_SCHEMA as _GUIDE_CURVES_SCHEMA
from hub_core.mcp.render_input_schemas import LEGEND_LAYOUT_SCHEMA as _LEGEND_LAYOUT_SCHEMA
from hub_core.mcp.render_input_schemas import LEGEND_OPTIONS_SCHEMA as _LEGEND_OPTIONS_SCHEMA
from hub_core.mcp.render_input_schemas import MULTIPANEL_LAYOUT_OPTIONS_SCHEMA as _MULTIPANEL_LAYOUT_OPTIONS_SCHEMA
from hub_core.mcp.render_input_schemas import POINT_LABEL_OPTIONS_SCHEMA as _POINT_LABEL_OPTIONS_SCHEMA
from hub_core.mcp.render_input_schemas import SECONDARY_Y_SCHEMA as _SECONDARY_Y_SCHEMA
from hub_core.mcp.render_input_schemas import SERIES_STYLES_SCHEMA as _SERIES_STYLES_SCHEMA
from hub_core.mcp.render_input_schemas import SHARED_LEGEND_OPTIONS_SCHEMA as _SHARED_LEGEND_OPTIONS_SCHEMA
from hub_core.mcp.render_input_schemas import TICK_STYLE_SCHEMA as _TICK_STYLE_SCHEMA
from hub_core.mcp.structure_schemas import (
    build_normalize_project_structure_definition,
    build_project_structure_schemas,
)
from hub_core.mcp.surface_profiles import select_tool_definitions
from hub_core.mcp.surface_schemas import list_plot_type_descriptions, list_semantic_check_descriptions
from hub_core.mcp.surface_schemas import supported_render_plot_types as _supported_render_plot_types
from hub_core.mcp.v2_tool_schemas import build_v2_tool_definitions
from themes.style_profiles import DEFAULT_PROFILE, PUBLIC_PROFILE_ALIASES, list_public_profiles

LEGACY_TOOL_NAMES = _schema_common.LEGACY_TOOL_NAMES
TOOL_HANDLER_NAMES = _schema_common.TOOL_HANDLER_NAMES
TOOL_NAMES = _schema_common.TOOL_NAMES
ToolDefinition = _schema_common.ToolDefinition
get_tool_handlers = _schema_common.get_tool_handlers
_RENDER_ARTIFACT_RESOURCE_SCHEMA = _schema_common.RENDER_ARTIFACT_RESOURCE_SCHEMA
_RENDER_PREVIEW_RESOURCE_SCHEMA = _schema_common.RENDER_PREVIEW_RESOURCE_SCHEMA
_object_schema = _schema_common.object_schema
_open_object_schema = _schema_common.open_object_schema
_standard_output_schema = _schema_common.standard_output_schema
_tool_annotations = _schema_common.tool_annotations
__all__ = [
    "LEGACY_TOOL_NAMES", "MCP_BATCH_MAX_PROJECTS", "TOOL_HANDLER_NAMES", "TOOL_NAMES",
    "describe_figops_surface", "describe_graphhub_surface", "get_tool_handlers", "list_tool_definitions",
    "list_plot_type_descriptions", "list_semantic_check_descriptions", "list_prompt_definitions",
    "list_resource_definitions", "list_resource_templates", "_open_object_schema", "_tool_annotations"]

_SIGNIFICANCE_MARKER_SCHEMA = {
    "type": "object",
    "properties": {
        "x1": {"type": "number"},
        "x2": {"type": "number"},
        "y": {"type": "number"},
        "h": {"type": "number"},
        "label": {"type": "string"},
        "color": {"type": "string"},
        "calculation_evidence_id": {"type": "string", "minLength": 1},
        "analysis_artifact_sha256": {"type": "string", "pattern": "^[0-9a-fA-F]{64}$"},
        "test_metadata": {
            "type": "object",
            "properties": {
                "test_name": {"type": "string", "minLength": 1},
                "model": {"type": "string", "minLength": 1},
            },
            "required": ["test_name", "model"],
            "additionalProperties": False,
        },
    },
    "required": [
        "x1",
        "x2",
        "y",
        "label",
        "calculation_evidence_id",
        "analysis_artifact_sha256",
        "test_metadata",
    ],
    "additionalProperties": False,
}

MCP_BATCH_MAX_PROJECTS = 50


def describe_figops_surface() -> dict[str, Any]:
    return {
        "plot_types": list_plot_type_descriptions(),
        "tools": [
            {
                "name": tool["name"],
                "purpose": tool["description"],
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool["outputSchema"],
            }
            for tool in list_tool_definitions()
        ],
        "semantic_checks": list_semantic_check_descriptions(),
        "domain_helpers": list_domain_helper_descriptions(),
    }


describe_graphhub_surface = describe_figops_surface


def list_tool_definitions(
    *, profile: str | None = None, write_tools_enabled: bool | None = None
) -> list[dict[str, Any]]:
    supported_render_plot_types = _supported_render_plot_types()
    root_arg = {"type": "string", "description": "Project scan root. Defaults to FigOps research root."}
    project_id_arg = {
        "type": "string",
        "description": "Discovered project ID; mutually exclusive with project_path, supply exactly one.",
    }
    project_path_arg = {
        "type": "string",
        "description": "Project path; mutually exclusive with project_id, supply exactly one.",
    }
    data_path_arg = {"type": "string", "description": "CSV input path under an allowed data root."}
    semantic_checks_arg = {
        "type": "object",
        "description": "Optional per-column semantic constraints keyed by CSV column name.",
    }
    baseline_path_arg = {
        "type": "string",
        "description": "Optional baseline figure path to compare the rendered output against.",
    }
    job_id_arg = {"type": "string", "description": "Stable render job ID; auto-generated when omitted."}
    listed_project_schema, project_metadata_schema, project_status_schema, structure_audit_schema = (
        build_project_structure_schemas()
    )
    selector_one_of = [{"required": ["project_id"]}, {"required": ["project_path"]}]
    project_selector = {
        "project_id": project_id_arg,
        "project_path": project_path_arg,
        "root": root_arg,
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
    }
    definitions = [
        ToolDefinition(
            "figops.health",
            "Return FigOps server health and discovery status.",
            _object_schema(
                {
                    "root": root_arg,
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                }
            ),
            _standard_output_schema(
                {
                    "hub_path": {"type": "string"},
                    "version": {"type": "string"},
                    "python_executable": {"type": "string"},
                    "runtime_root": {"type": "string"},
                    "style_format_count": {"type": "integer"},
                    "discovery_status": {"type": "object"},
                    "write_tools_enabled": {"type": "boolean"},
                    "surface_profile": {"type": "string"},
                    "exposed_tool_count": {"type": "integer"},
                    "preview_worker_limits": {
                        "type": "object",
                        "properties": {
                            "memory_limit_bytes": {"type": "integer"},
                            "memory_limit_enforced": {"type": "boolean"},
                            "memory_limit_limitation": {"type": ["string", "null"]},
                            "timeout_seconds": {"type": "number"},
                            "source_byte_limit": {"type": "integer"},
                            "raw_output_byte_limit": {"type": "integer"},
                            "base64_output_byte_limit": {"type": "integer"},
                            "pixel_limit": {"type": "integer"},
                            "edge_limit": {"type": "integer"},
                            "cpu_limit_enforced": {"type": "boolean"},
                            "file_size_limit_enforced": {"type": "boolean"},
                            "process_tree_containment": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                }
            ),
        ),
        ToolDefinition(
            "figops.describe",
            "Describe registered FigOps tools, plot types, semantic checks, and render examples.",
            _object_schema(),
            _standard_output_schema(
                {
                    "plot_types": {"type": "array", "items": {"type": "object"}},
                    "tools": {"type": "array", "items": {"type": "object"}},
                    "semantic_checks": {"type": "array", "items": {"type": "object"}},
                    "domain_helpers": {"type": "array", "items": {"type": "object"}},
                }
            ),
        ),
        ToolDefinition(
            "figops.list_styles",
            "Return canonical FigOps target formats, output formats, profiles, and aliases.",
            _object_schema(),
            _standard_output_schema(
                {
                    "target_formats": {"type": "array", "items": {"type": "string"}},
                    "output_formats": {"type": "array", "items": {"type": "string"}},
                    "profiles": {"type": "array", "items": {"type": "string"}},
                    "profile_aliases": {"type": "object"},
                    "style_packs": {"type": "array", "items": {"type": "object"}},
                    "default_target_format": {"type": "string"},
                    "default_profile": {"type": "string"},
                }
            ),
        ),
        ToolDefinition(
            "figops.list_projects",
            "Discover FigOps project configs without executing scripts or writing files.",
            _object_schema(
                {
                    "root": root_arg,
                    "include_invalid": {"type": "boolean", "default": True},
                    "include_worktrees": {"type": "boolean", "default": False},
                    "include_ephemeral": {"type": "boolean", "default": False},
                    "include_quarantine": {"type": "boolean", "default": False},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                }
            ),
            _standard_output_schema({"projects": {"type": "array", "items": listed_project_schema}}),
        ),
        ToolDefinition(
            "figops.inspect_project",
            "Summarize one project config without running analysis, plotting, or report writers.",
            {
                **_object_schema(
                    {**project_selector, "include_naming_lint": {"type": "boolean", "default": False}}
                ),
                "oneOf": selector_one_of,
            },
            _standard_output_schema(
                {
                    "project_metadata": project_metadata_schema,
                    "folder_structure_status": {"type": "object"},
                    "data_contract_summary": {"type": "object"},
                    "pipeline_steps": {"type": "object"},
                    "figure_outputs": {"type": "array", "items": {"type": "string"}},
                    "diagram_outputs": {"type": "array", "items": {"type": "string"}},
                    "figure_traceability_matrix": {"type": "array", "items": {"type": "object"}},
                    "missing_inputs": {"type": "array", "items": {"type": "string"}},
                    "missing_outputs": {"type": "array", "items": {"type": "string"}},
                    "style_summary": {"type": "object"},
                    "folder_role_summary": {"type": "object"},
                    "experimental_conditions_summary": {"type": "object"},
                    "sample_registry_summary": {"type": "object"},
                    "raw_integrity_status": {"type": "object"},
                    "naming_lint": {"type": "object"},
                    "canonical_docs_registry": {"type": "object"},
                    "placeholder_report": {"type": "object"},
                    "structure_audit": structure_audit_schema,
                    "normalization_needed": {"type": "boolean"},
                }
            ),
        ),
        ToolDefinition(
            "figops.validate_project",
            "Run read-only config, data contract, style, and lockfile checks without executing scripts.",
            {
                **_object_schema(
                    {
                        **project_selector,
                        "strict_lock": {"type": "boolean", "default": False},
                        "include_naming_lint": {"type": "boolean", "default": False},
                    }
                ),
                "oneOf": selector_one_of,
            },
            _standard_output_schema(
                {
                    "valid": {"type": "boolean"},
                    "config_errors": {"type": "array", "items": {"type": "string"}},
                    "data_contract_errors": {"type": "array", "items": {"type": "string"}},
                    "lockfile_status": {"type": "object"},
                    "style_errors": {"type": "array", "items": {"type": "string"}},
                    "raw_integrity_status": {"type": "object"},
                    "naming_lint": {"type": "object"},
                    "canonical_docs_registry": {"type": "object"},
                    "placeholder_report": {"type": "object"},
                    "project_status": project_status_schema,
                    "recommended_next_action": {"type": "string"},
                }
            ),
        ),
        ToolDefinition(
            "figops.render_csv_graph",
            "Render a CSV-backed graph in an isolated runtime-root MCP job workspace.",
            _object_schema(
                {
                    "data_path": data_path_arg,
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "z_column": {"type": "string"},
                    "facet_column": {"type": "string"},
                    "series_column": {"type": "string"},
                    "label_column": {"type": "string"},
                    "label_map": {"type": "object", "additionalProperties": {"type": "string"}},
                    "label_transform": {
                        "type": "string",
                        "enum": ["raw", "legacy_compress"],
                        "default": "raw",
                    },
                    "compliance_mode": {
                        "type": "string",
                        "enum": ["validate", "clamp"],
                        "default": "validate",
                    },
                    "declutter_mode": {
                        "type": "string",
                        "enum": ["none", "declutter"],
                        "default": "none",
                    },
                    "point_label_options": _POINT_LABEL_OPTIONS_SCHEMA,
                    "series_styles": _SERIES_STYLES_SCHEMA,
                    "secondary_y": _SECONDARY_Y_SCHEMA,
                    "x_scale": {"type": "string", "enum": ["linear", "log"], "default": "linear"},
                    "y_scale": {"type": "string", "enum": ["linear", "log"], "default": "linear"},
                    "legend_layout": _LEGEND_LAYOUT_SCHEMA,
                    "legend_options": _LEGEND_OPTIONS_SCHEMA,
                    "axis_limits": _AXIS_LIMITS_SCHEMA,
                    "tick_style": _TICK_STYLE_SCHEMA,
                    "annotations": _ANNOTATIONS_SCHEMA,
                    "guide_curves": _GUIDE_CURVES_SCHEMA,
                    "fill_between": _FILL_BETWEEN_OVERLAYS_SCHEMA,
                    "facet_scales": {"type": "string", "enum": ["fixed", "free"], "default": "fixed"},
                    "category_order": {"type": "array", "items": {"type": ["string", "number"]}},
                    "facet_order": {"type": "array", "items": {"type": "string"}},
                    "facet_ncols": {"type": "integer", "minimum": 1},
                    "facet_nrows": {"type": "integer", "minimum": 1},
                    "aggregate": {"type": "string", "enum": ["mean", "median"]},
                    "bar_error_column": {"type": "string"},
                    "yerr_column": {"type": "string"},
                    "yerr_minus_column": {"type": "string"},
                    "yerr_cap_width": {"type": "number", "minimum": 0, "default": 3.0},
                    "annotate_values": {"type": "boolean", "default": False},
                    "fit_line": {"type": "boolean"},
                    "ci_band": {"type": "boolean"},
                    "fit_options": _FIT_OPTIONS_SCHEMA,
                    "significance_markers": {"type": "array", "items": _SIGNIFICANCE_MARKER_SCHEMA},
                    "calculation_evidence_path": data_path_arg,
                    "calculation_evidence_paths": {
                        "type": "array",
                        "items": data_path_arg,
                        "maxItems": 32,
                    },
                    "plot_type": {"type": "string", "enum": supported_render_plot_types, "default": "scatter"},
                    "target_format": {"type": "string", "enum": sorted(PUBLIC_TARGET_FORMATS), "default": "nature"},
                    "profile": {
                        "type": "string",
                        "enum": sorted(set(list_public_profiles()) | set(PUBLIC_PROFILE_ALIASES)),
                        "default": DEFAULT_PROFILE,
                    },
                    "output_format": {"type": "string", "enum": sorted(ALLOWED_OUTPUT_FORMATS), "default": "png"},
                    "semantic_checks": semantic_checks_arg,
                    "dry_run": {"type": "boolean", "default": False},
                    "overwrite": {"type": "boolean", "default": False},
                    "job_id": job_id_arg,
                    "title": {"type": "string"},
                    "x_axis_label": {"type": "string"},
                    "y_axis_label": {"type": "string"},
                    "baseline_path": baseline_path_arg,
                },
                required=["data_path", "x_column", "y_column"],
            ),
            _standard_output_schema(
                {
                    "artifact_resources": _RENDER_ARTIFACT_RESOURCE_SCHEMA,
                    "preview_resources": _RENDER_PREVIEW_RESOURCE_SCHEMA,
                    "job_id": {"type": "string"},
                    "job_root": {"type": "string"},
                    "output_path": {"type": "string"},
                    "config_path": {"type": "string"},
                    "style_summary": {"type": "object"},
                    "visual_preflight_status": {"type": "object"},
                    "geometry_diagnostics": _GEOMETRY_DIAGNOSTICS_SCHEMA,
                    "layout_report": _LAYOUT_REPORT_SCHEMA,
                    "calculation_checks": {"type": "object"},
                    "calculation_evidence": {"type": "array", "items": {"type": "object"}},
                    "statistical_claims": {"type": "array", "items": {"type": "object"}},
                    "descriptive_overlays": {"type": "array", "items": {"type": "object"}},
                    "claim_candidates": {"type": "array", "items": {"type": "object"}},
                    "label_transformations": {"type": "object"},
                    "mutation_ledger": {"type": "array", "items": {"type": "object"}},
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                    "evidence": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "figops.render_csv_multipanel",
            "Render a multi-panel CSV-backed composite figure in an isolated runtime-root MCP job workspace.",
            _object_schema(
                {
                    "panels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "data_path": data_path_arg,
                                "x_column": {"type": "string"},
                                "y_column": {"type": "string"},
                                "z_column": {"type": "string"},
                                "facet_column": {"type": "string"},
                                "series_column": {"type": "string"},
                                "label_column": {"type": "string"},
                                "label_map": {"type": "object", "additionalProperties": {"type": "string"}},
                                "label_transform": {
                                    "type": "string",
                                    "enum": ["raw", "legacy_compress"],
                                    "default": "raw",
                                },
                                "compliance_mode": {
                                    "type": "string",
                                    "enum": ["validate", "clamp"],
                                    "default": "validate",
                                },
                                "declutter_mode": {
                                    "type": "string",
                                    "enum": ["none", "declutter"],
                                    "default": "none",
                                },
                                "point_label_options": _POINT_LABEL_OPTIONS_SCHEMA,
                                "series_styles": _SERIES_STYLES_SCHEMA,
                                "secondary_y": _SECONDARY_Y_SCHEMA,
                                "x_scale": {"type": "string", "enum": ["linear", "log"], "default": "linear"},
                                "y_scale": {"type": "string", "enum": ["linear", "log"], "default": "linear"},
                                "legend_layout": _LEGEND_LAYOUT_SCHEMA,
                                "legend_options": _LEGEND_OPTIONS_SCHEMA,
                                "axis_limits": _AXIS_LIMITS_SCHEMA,
                                "tick_style": _TICK_STYLE_SCHEMA,
                                "annotations": _ANNOTATIONS_SCHEMA,
                                "guide_curves": _GUIDE_CURVES_SCHEMA,
                                "fill_between": _FILL_BETWEEN_OVERLAYS_SCHEMA,
                                "yerr_column": {"type": "string"},
                                "yerr_minus_column": {"type": "string"},
                                "yerr_cap_width": {"type": "number", "minimum": 0, "default": 3.0},
                                "fit_line": {"type": "boolean"},
                                "ci_band": {"type": "boolean"},
                                "fit_options": _FIT_OPTIONS_SCHEMA,
                                "significance_markers": {"type": "array", "items": _SIGNIFICANCE_MARKER_SCHEMA},
                                "calculation_evidence_path": data_path_arg,
                                "calculation_evidence_paths": {
                                    "type": "array",
                                    "items": data_path_arg,
                                    "maxItems": 32,
                                },
                                "plot_type": {
                                    "type": "string",
                                    "enum": supported_render_plot_types,
                                    "default": "scatter",
                                },
                                "title": {"type": "string"},
                                "x_axis_label": {"type": "string"},
                                "y_axis_label": {"type": "string"},
                            },
                            "required": ["data_path", "x_column", "y_column"],
                            "additionalProperties": False,
                        },
                        "minItems": 1,
                    },
                    "rows": {"type": "integer", "minimum": 1},
                    "cols": {"type": "integer", "minimum": 1},
                    "column_width": {"type": "string", "default": "double"},
                    "panel_height_mm": {"type": "number", "minimum": 1, "default": 65.0},
                    "panel_labels": {"type": "boolean", "default": True},
                    "font_scale": {"type": "number", "default": 1.0},
                    "compose_mode": {"type": "string", "enum": ["draft", "manuscript"], "default": "draft"},
                    "layout_options": _MULTIPANEL_LAYOUT_OPTIONS_SCHEMA,
                    "shared_legend": {"type": "boolean", "default": False},
                    "shared_legend_options": _SHARED_LEGEND_OPTIONS_SCHEMA,
                    "target_format": {"type": "string", "enum": sorted(PUBLIC_TARGET_FORMATS), "default": "nature"},
                    "profile": {
                        "type": "string",
                        "enum": sorted(set(list_public_profiles()) | set(PUBLIC_PROFILE_ALIASES)),
                        "default": DEFAULT_PROFILE,
                    },
                    "output_format": {"type": "string", "enum": sorted(ALLOWED_OUTPUT_FORMATS), "default": "png"},
                    "dry_run": {"type": "boolean", "default": False},
                    "overwrite": {"type": "boolean", "default": False},
                    "job_id": job_id_arg,
                    "baseline_path": baseline_path_arg,
                },
                required=["panels"],
            ),
            _standard_output_schema(
                {
                    "artifact_resources": _RENDER_ARTIFACT_RESOURCE_SCHEMA,
                    "preview_resources": _RENDER_PREVIEW_RESOURCE_SCHEMA,
                    "job_id": {"type": "string"},
                    "job_root": {"type": "string"},
                    "output_path": {"type": "string"},
                    "config_path": {"type": "string"},
                    "style_summary": {"type": "object"},
                    "visual_preflight_status": {"type": "object"},
                    "geometry_diagnostics": _GEOMETRY_DIAGNOSTICS_SCHEMA,
                    "layout_report": _LAYOUT_REPORT_SCHEMA,
                    "calculation_checks": {"type": "object"},
                    "calculation_evidence": {"type": "array", "items": {"type": "object"}},
                    "statistical_claims": {"type": "array", "items": {"type": "object"}},
                    "descriptive_overlays": {"type": "array", "items": {"type": "object"}},
                    "claim_candidates": {"type": "array", "items": {"type": "object"}},
                    "label_transformations": {"type": "object"},
                    "mutation_ledger": {"type": "array", "items": {"type": "object"}},
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                    "provenance": {"type": "object"},
                    "evidence": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "figops.render_project_figure",
            "Render one configured project figure in an isolated runtime-root MCP job workspace.",
            {
                **_object_schema(
                    {
                        "project_id": project_id_arg,
                        "project_path": project_path_arg,
                        "root": root_arg,
                        "figure_id": {"type": "string"},
                        "figure_output": {"type": "string"},
                        "target_format": {"type": "string", "enum": sorted(PUBLIC_TARGET_FORMATS)},
                        "profile": {
                            "type": "string",
                            "enum": sorted(set(list_public_profiles()) | set(PUBLIC_PROFILE_ALIASES)),
                        },
                        "output_format": {"type": "string", "enum": sorted(ALLOWED_OUTPUT_FORMATS)},
                        "dry_run": {"type": "boolean", "default": False},
                        "overwrite": {"type": "boolean", "default": False},
                        "job_id": job_id_arg,
                        "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                        "baseline_path": baseline_path_arg,
                    }
                ),
                "oneOf": selector_one_of,
            },
            _standard_output_schema(
                {
                    "artifact_resources": _RENDER_ARTIFACT_RESOURCE_SCHEMA,
                    "preview_resources": _RENDER_PREVIEW_RESOURCE_SCHEMA,
                    "job_id": {"type": "string"},
                    "project_id": {"type": "string"},
                    "source_project_path": {"type": "string"},
                    "job_root": {"type": "string"},
                    "snapshot_project_path": {"type": "string"},
                    "selected_figure": {"type": "object"},
                    "output_path": {"type": "string"},
                    "config_path": {"type": "string"},
                    "style_summary": {"type": "object"},
                    "visual_preflight_status": {"type": "object"},
                    "geometry_diagnostics": _GEOMETRY_DIAGNOSTICS_SCHEMA,
                    "layout_report": _LAYOUT_REPORT_SCHEMA,
                    "figure_metadata": {"type": "object"},
                    "claim_inventory": {"type": "object"},
                    "publication_status": {"type": "string", "enum": ["verified", "unverified"]},
                    "promotion_eligible": {"type": "boolean"},
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                    "provenance": {"type": "object"},
                    "evidence": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "figops.collect_artifacts",
            "Return artifact metadata for a completed MCP render job.",
            _object_schema(
                {
                    "job_id": {"type": "string", "description": "Render job ID returned by a prior render call."},
                    "baseline_path": baseline_path_arg,
                },
                required=["job_id"],
            ),
            _standard_output_schema(
                {
                    "figures": {"type": "array", "items": {"type": "object"}},
                    "diagrams": {"type": "array", "items": {"type": "object"}},
                    "assemblies": {"type": "array", "items": {"type": "object"}},
                    "logs": {"type": "array", "items": {"type": "object"}},
                    "provenance": {"type": "object"},
                    "visual_preflight_status": {"type": "object"},
                    "layout_report": _LAYOUT_REPORT_SCHEMA,
                    "figure_metadata": {"type": "object"},
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "figops.evaluate_publication_readiness",
            "Evaluate an existing render job manifest into a read-only publication-readiness report.",
            _object_schema(
                {
                    "job_id": {
                        "type": "string",
                        "pattern": "^[A-Za-z0-9_-]{1,80}$",
                        "description": "Existing render job ID whose bounded manifest evidence will be evaluated.",
                    }
                },
                required=["job_id"],
            ),
            _standard_output_schema({"readiness_report": {"type": "object"}}),
        ),
        ToolDefinition(
            "figops.scaffold_project",
            "Plan or create a standard FigOps project scaffold.",
            _object_schema(
                {
                    "project_name": {"type": "string"},
                    "project_root": {"type": "string"},
                    "target_format": {"type": "string", "enum": sorted(PUBLIC_TARGET_FORMATS), "default": "nature"},
                    "template": {"type": "string", "enum": ["standard", "researchos"], "default": "standard"},
                    "dry_run": {
                        "type": "boolean",
                        "default": True,
                        "description": (
                            "Preview without writing files. Defaults True like normalize_project_structure and "
                            "batch_check; the two render tools default dry_run False."
                        ),
                    },
                    "overwrite": {"type": "boolean", "default": False},
                },
                required=["project_name", "project_root"],
            ),
            _standard_output_schema(
                {
                    "project_root": {"type": "string"},
                    "project_name": {"type": "string"},
                    "planned_paths": {"type": "array", "items": {"type": "string"}},
                    "manifest": {"type": "object"},
                    "config_path": {"type": "string"},
                    "style_summary": {"type": "object"},
                    "validation": {"type": "object"},
                }
            ),
        ),
        build_normalize_project_structure_definition(),
        ToolDefinition(
            "figops.batch_check",
            "Run a bounded project discovery and validation batch check with optional runtime manifest logging.",
            _object_schema(
                {
                    "root": root_arg,
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                    "max_projects": {"type": "integer", "minimum": 1, "maximum": MCP_BATCH_MAX_PROJECTS, "default": 20},
                    "include_invalid": {"type": "boolean", "default": False},
                    "include_legacy": {"type": "boolean", "default": False},
                    "include_worktrees": {"type": "boolean", "default": False},
                    "include_ephemeral": {"type": "boolean", "default": False},
                    "include_quarantine": {"type": "boolean", "default": False},
                    "dry_run": {"type": "boolean", "default": True},
                    "batch_id": {"type": "string"},
                    "resume_manifest_path": {"type": "string"},
                }
            ),
            _standard_output_schema(
                {
                    "batch_id": {"type": "string"},
                    "batch_root": {"type": "string"},
                    "checked_projects": {"type": "array", "items": {"type": "object"}},
                    "skipped_projects": {"type": "array", "items": {"type": "object"}},
                    "resumed_from": {"type": "string"},
                    "log_paths": {"type": "array", "items": {"type": "string"}},
                }
            ),
        ),
        *build_v2_tool_definitions(
            project_id_arg=project_id_arg,
            project_path_arg=project_path_arg,
            selector_one_of=selector_one_of,
        ),
    ]
    serialized = [definition.to_dict() for definition in definitions]
    if profile is None:
        return serialized
    return select_tool_definitions(serialized, profile=profile, write_tools_enabled=bool(write_tools_enabled))


def list_resource_definitions() -> list[dict[str, str]]:
    """Compatibility wrapper for static MCP resource definitions."""

    return _list_resource_definitions()


def list_resource_templates() -> list[dict[str, str]]:
    """Compatibility wrapper for static MCP resource-template definitions."""

    return _list_resource_templates()


def list_prompt_definitions() -> list[dict[str, Any]]:
    """Compatibility wrapper that supplies the live plot-type list to prompts."""

    return _list_prompt_definitions(_supported_render_plot_types())
