from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS
from hub_core.data_contract import SEMANTIC_CHECK_DEFINITIONS
from hub_core.domain_analysis import list_domain_helper_descriptions
from hub_core.rendering import PLOT_TYPES
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles

TOOL_NAMES = (
    "graphhub.health",
    "graphhub.describe",
    "graphhub.list_styles",
    "graphhub.list_projects",
    "graphhub.inspect_project",
    "graphhub.validate_project",
    "graphhub.render_csv_graph",
    "graphhub.render_project_figure",
    "graphhub.collect_artifacts",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
MCP_BATCH_MAX_PROJECTS = 50
_GEOMETRY_METRIC_NAMES = (
    "tick_label_overlaps",
    "tick_label_crowding",
    "artists_outside_axes",
    "artists_outside_figure",
    "legend_data_collision",
    "axis_label_title_overlap",
    "colorbar_overlap",
    "blank_area_ratio",
    "point_annotation_overlaps",
    "artist_overlaps",
    "legend_internal_overlaps",
    "marker_marker_overlaps",
    "text_axis_edge_proximity",
    "legend_marker_consistency",
    "label_offset_consistency",
    "font_size_token_drift",
    "journal_compliance",
)
_GEOMETRY_DIAGNOSTICS_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "passed": {"type": ["boolean", "null"]},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": list(_GEOMETRY_METRIC_NAMES)},
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

_LAYOUT_REPORT_SCHEMA = {
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


TOOL_HANDLER_NAMES = {
    "graphhub.health": "health",
    "graphhub.describe": "describe",
    "graphhub.list_styles": "list_styles",
    "graphhub.list_projects": "list_projects",
    "graphhub.inspect_project": "inspect_project",
    "graphhub.validate_project": "validate_project",
    "graphhub.render_csv_graph": "render_csv_graph",
    "graphhub.render_project_figure": "render_project_figure",
    "graphhub.collect_artifacts": "collect_artifacts",
    "graphhub.scaffold_project": "scaffold_project",
    "graphhub.normalize_project_structure": "normalize_project_structure",
    "graphhub.batch_check": "batch_check",
}


def get_tool_handlers(server: Any) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {name: getattr(server, handler_name) for name, handler_name in TOOL_HANDLER_NAMES.items()}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }


def _object_schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _standard_output_schema(extra_properties: dict[str, Any] | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "status": {"type": "string", "enum": ["ok", "warning", "error"]},
        "operation_id": {"type": "string"},
        "is_dry_run": {"type": "boolean"},
        "summary": {"type": "string"},
        "created_paths": {"type": "array", "items": {"type": "string"}},
        "modified_paths": {"type": "array", "items": {"type": "string"}},
        "skipped_paths": {"type": "array", "items": {"type": "string"}},
        "artifact_resources": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "errors": {"type": "array", "items": {"type": "string"}},
        "script_output": {"type": "array", "items": {"type": "string"}},
        "manual_review_needed": {"type": "boolean"},
        "error_category": {"type": "string", "enum": ["validation", "not_found", "internal", "disabled"]},
        "error_code": {"type": "string"},
        "jsonrpc_code": {"type": "integer"},
        "failure_stage": {"type": "string"},
        "resolution_hint": {"type": "string"},
        "manifest_path": {"type": "string"},
        "status_path": {"type": "string"},
        "latest_alias": {"type": "string"},
        "latest_dir": {"type": "string"},
    }
    properties.update(extra_properties or {})
    return _object_schema(properties)


def _supported_render_plot_types() -> list[str]:
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
    if "category_order" in arg_schema.get("properties", {}):
        arguments["category_order"] = ["day 0", "day 7", "day 14", "day 28"]
    if "facet_order" in arg_schema.get("properties", {}):
        arguments["facet_order"] = ["control", "treated"]
    if "facet_ncols" in arg_schema.get("properties", {}):
        arguments["facet_ncols"] = 2
    if "aggregate" in arg_schema.get("properties", {}):
        arguments["aggregate"] = "mean"
    if "bar_error_column" in arg_schema.get("properties", {}):
        arguments["bar_error_column"] = "sem"
    if "annotate_values" in arg_schema.get("properties", {}):
        arguments["annotate_values"] = True
    if "fit_line" in arg_schema.get("properties", {}):
        arguments["fit_line"] = True
        arguments["ci_band"] = True
        arguments["significance_markers"] = [{"x1": 0, "x2": 1, "y": 2, "label": "p<0.05"}]
    return {"tool": "graphhub.render_csv_graph", "arguments": arguments}


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


def describe_graphhub_surface() -> dict[str, Any]:
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


def list_tool_definitions() -> list[dict[str, Any]]:
    supported_render_plot_types = _supported_render_plot_types()
    root_arg = {"type": "string", "description": "Project scan root. Defaults to Graph Hub research root."}
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
    project_role_schema = {"type": "string", "enum": ["master", "module"]}
    discovery_role_schema = {
        "type": "string",
        "enum": [
            "archive",
            "docs",
            "exploratory",
            "master",
            "module",
            "raw_reservoir",
            "reference",
            "support",
            "theory",
            "unclassified",
        ],
    }
    listed_project_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "project_root": {"type": "string"},
            "config_path": {"type": "string"},
            "role": discovery_role_schema,
            "status": {"type": "string"},
            "errors": {"type": "array", "items": {"type": "string"}},
            "declared_figures": {"type": "integer"},
            "declared_diagrams": {"type": "integer"},
            "target_format": {"type": "string"},
        },
    }
    project_metadata_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "role": project_role_schema,
            "project_root": {"type": "string"},
            "config_path": {"type": "string"},
        },
    }
    selector_one_of = [{"required": ["project_id"]}, {"required": ["project_path"]}]
    project_selector = {
        "project_id": project_id_arg,
        "project_path": project_path_arg,
        "root": root_arg,
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
    }
    definitions = [
        ToolDefinition(
            "graphhub.health",
            "Return Graph Hub server health and discovery status.",
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
                }
            ),
        ),
        ToolDefinition(
            "graphhub.describe",
            "Describe registered Graph Hub tools, plot types, semantic checks, and render examples.",
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
            "graphhub.list_styles",
            "Return canonical Graph Hub target formats, output formats, profiles, and aliases.",
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
            "graphhub.list_projects",
            "Discover Graph Hub project configs without executing scripts or writing files.",
            _object_schema(
                {
                    "root": root_arg,
                    "include_invalid": {"type": "boolean", "default": True},
                    "include_worktrees": {"type": "boolean", "default": False},
                    "include_ephemeral": {"type": "boolean", "default": False},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                }
            ),
            _standard_output_schema({"projects": {"type": "array", "items": listed_project_schema}}),
        ),
        ToolDefinition(
            "graphhub.inspect_project",
            "Summarize one project config without running analysis, plotting, or report writers.",
            {**_object_schema(project_selector), "oneOf": selector_one_of},
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
                    "normalization_needed": {"type": "boolean"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.validate_project",
            "Run read-only config, data contract, style, and lockfile checks without executing scripts.",
            {
                **_object_schema({**project_selector, "strict_lock": {"type": "boolean", "default": False}}),
                "oneOf": selector_one_of,
            },
            _standard_output_schema(
                {
                    "valid": {"type": "boolean"},
                    "config_errors": {"type": "array", "items": {"type": "string"}},
                    "data_contract_errors": {"type": "array", "items": {"type": "string"}},
                    "lockfile_status": {"type": "object"},
                    "style_errors": {"type": "array", "items": {"type": "string"}},
                    "recommended_next_action": {"type": "string"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.render_csv_graph",
            "Render a CSV-backed graph in an isolated runtime-root MCP job workspace.",
            _object_schema(
                {
                    "data_path": data_path_arg,
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "z_column": {"type": "string"},
                    "facet_column": {"type": "string"},
                    "facet_scales": {"type": "string", "enum": ["fixed", "free"], "default": "fixed"},
                    "category_order": {"type": "array", "items": {"type": ["string", "number"]}},
                    "facet_order": {"type": "array", "items": {"type": "string"}},
                    "facet_ncols": {"type": "integer", "minimum": 1},
                    "facet_nrows": {"type": "integer", "minimum": 1},
                    "aggregate": {"type": "string", "enum": ["mean", "median"]},
                    "bar_error_column": {"type": "string"},
                    "annotate_values": {"type": "boolean", "default": False},
                    "fit_line": {"type": "boolean"},
                    "ci_band": {"type": "boolean"},
                    "significance_markers": {"type": "array", "items": {"type": "object"}},
                    "plot_type": {"type": "string", "enum": supported_render_plot_types, "default": "scatter"},
                    "target_format": {"type": "string", "enum": sorted(ALLOWED_TARGET_FORMATS), "default": "nature"},
                    "profile": {
                        "type": "string",
                        "enum": sorted(set(list_profiles()) | set(PROFILE_ALIASES)),
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
                    "job_id": {"type": "string"},
                    "job_root": {"type": "string"},
                    "output_path": {"type": "string"},
                    "config_path": {"type": "string"},
                    "style_summary": {"type": "object"},
                    "visual_preflight_status": {"type": "object"},
                    "geometry_diagnostics": _GEOMETRY_DIAGNOSTICS_SCHEMA,
                    "layout_report": _LAYOUT_REPORT_SCHEMA,
                    "calculation_checks": {"type": "object"},
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.render_project_figure",
            "Render one configured project figure in an isolated runtime-root MCP job workspace.",
            {
                **_object_schema(
                    {
                        "project_id": project_id_arg,
                        "project_path": project_path_arg,
                        "root": root_arg,
                        "figure_id": {"type": "string"},
                        "figure_output": {"type": "string"},
                        "target_format": {"type": "string", "enum": sorted(ALLOWED_TARGET_FORMATS)},
                        "profile": {"type": "string", "enum": sorted(set(list_profiles()) | set(PROFILE_ALIASES))},
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
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                    "provenance": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.collect_artifacts",
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
            "graphhub.scaffold_project",
            "Plan or create a standard Graph Hub project scaffold.",
            _object_schema(
                {
                    "project_name": {"type": "string"},
                    "project_root": {"type": "string"},
                    "target_format": {"type": "string", "enum": sorted(ALLOWED_TARGET_FORMATS), "default": "nature"},
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
        ToolDefinition(
            "graphhub.normalize_project_structure",
            "Plan or apply migration of an existing graph folder into standard Graph Hub structure.",
            _object_schema(
                {
                    "project_path": {"type": "string"},
                    "dry_run": {
                        "type": "boolean",
                        "default": True,
                        "description": (
                            "Preview without writing files. Defaults True like scaffold_project and "
                            "batch_check; the two render tools default dry_run False."
                        ),
                    },
                    "move_policy": {"type": "string", "enum": ["copy", "move", "symlink"], "default": "copy"},
                    "include_raw": {"type": "boolean", "default": False},
                    "overwrite": {"type": "boolean", "default": False},
                },
                required=["project_path"],
            ),
            _standard_output_schema(
                {
                    "project_root": {"type": "string"},
                    "planned_paths": {"type": "array", "items": {"type": "string"}},
                    "manifest": {"type": "object"},
                    "config_path": {"type": "string"},
                    "style_summary": {"type": "object"},
                    "validation": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.batch_check",
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
    ]
    return [definition.to_dict() for definition in definitions]


def list_resource_definitions() -> list[dict[str, str]]:
    return [
        {
            "uri": "graphhub://styles",
            "name": "Graph Hub Styles",
            "description": "Canonical target formats, output formats, profiles, and aliases.",
            "mimeType": "application/json",
        },
        {
            "uri": "graphhub://profiles",
            "name": "Graph Hub Style Profiles",
            "description": "Available style profiles and profile aliases.",
            "mimeType": "application/json",
        },
        {
            "uri": "graphhub://projects",
            "name": "Graph Hub Projects",
            "description": "Discovered Graph Hub project metadata using default discovery rules.",
            "mimeType": "application/json",
        },
    ]


def list_resource_templates() -> list[dict[str, str]]:
    return [
        {
            "uriTemplate": "graphhub://projects/{project_id}/config",
            "name": "Graph Hub Project Config",
            "description": "Project configuration YAML resolved by discovered project ID.",
            "mimeType": "application/x-yaml",
        },
        {
            "uriTemplate": "graphhub://jobs/{job_id}/manifest",
            "name": "Graph Hub Render Job Manifest",
            "description": "Sanitized render job manifest resolved by job ID.",
            "mimeType": "application/json",
        },
    ]


def list_prompt_definitions() -> list[dict[str, Any]]:
    supported_render_plot_types = _supported_render_plot_types()
    return [
        {
            "name": "make_publication_graph_from_csv",
            "description": "Workflow for rendering a publication-style graph from structured CSV data.",
            "arguments": [
                {"name": "data_path", "description": "CSV input path.", "required": True},
                {"name": "x_column", "description": "CSV x-axis column.", "required": True},
                {"name": "y_column", "description": "CSV y-axis column.", "required": True},
                {"name": "target_format", "description": "Graph Hub target format.", "required": False},
                {"name": "plot_type", "description": ", ".join(supported_render_plot_types), "required": False},
            ],
        },
        {
            "name": "inspect_graph_project_quality",
            "description": "Workflow for inspecting a graph project without executing scripts.",
            "arguments": [
                {"name": "project_id", "description": "Discovered Graph Hub project ID.", "required": False},
                {"name": "project_path", "description": "Project path.", "required": False},
            ],
        },
        {
            "name": "standardize_existing_graph_project",
            "description": "Workflow for planning safe Graph Hub project normalization.",
            "arguments": [
                {"name": "project_path", "description": "Existing graph project path.", "required": True},
                {"name": "move_policy", "description": "copy, move, or symlink.", "required": False},
            ],
        },
        {
            "name": "render_project_figure",
            "description": "Workflow for rendering one configured project figure through Graph Hub MCP.",
            "arguments": [
                {"name": "project_id", "description": "Discovered Graph Hub project ID.", "required": False},
                {"name": "project_path", "description": "Project path.", "required": False},
                {"name": "figure_id", "description": "Configured figures[].id.", "required": False},
                {"name": "figure_output", "description": "Configured figures[].output.", "required": False},
            ],
        },
    ]
