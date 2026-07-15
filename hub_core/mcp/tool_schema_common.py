"""Shared MCP tool registry and compact schema construction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hub_core.mcp.security import is_write_tool_name

TOOL_NAMES = (
    "figops.health",
    "figops.describe",
    "figops.list_styles",
    "figops.list_projects",
    "figops.inspect_project",
    "figops.validate_project",
    "figops.render_csv_graph",
    "figops.render_csv_multipanel",
    "figops.render_project_figure",
    "figops.collect_artifacts",
    "figops.scaffold_project",
    "figops.normalize_project_structure",
    "figops.batch_check",
    "figops.evaluate_publication_readiness",
    "figops.inspect_data",
    "figops.render_basic_csv",
    "figops.render_project_script",
    "figops.audit_artifact",
)
LEGACY_TOOL_NAMES = tuple(name.replace("figops.", "graphhub.", 1) for name in TOOL_NAMES[:13])

TOOL_HANDLER_NAMES = {
    "figops.health": "health",
    "figops.describe": "describe",
    "figops.list_styles": "list_styles",
    "figops.list_projects": "list_projects",
    "figops.inspect_project": "inspect_project",
    "figops.validate_project": "validate_project",
    "figops.render_csv_graph": "render_csv_graph",
    "figops.render_csv_multipanel": "render_csv_multipanel",
    "figops.render_project_figure": "render_project_figure",
    "figops.collect_artifacts": "collect_artifacts",
    "figops.scaffold_project": "scaffold_project",
    "figops.normalize_project_structure": "normalize_project_structure",
    "figops.batch_check": "batch_check",
    "figops.evaluate_publication_readiness": "evaluate_publication_readiness",
    "figops.inspect_data": "inspect_data",
    "figops.render_basic_csv": "render_basic_csv",
    "figops.render_project_script": "render_project_script",
    "figops.audit_artifact": "audit_artifact",
}
TOOL_HANDLER_NAMES.update(
    {
        legacy_name: TOOL_HANDLER_NAMES[primary_name]
        for primary_name, legacy_name in zip(TOOL_NAMES[:13], LEGACY_TOOL_NAMES, strict=True)
    }
)


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
            "annotations": tool_annotations(self.name),
        }


def tool_annotations(name: str) -> dict[str, bool]:
    writes = is_write_tool_name(name)
    return {
        "readOnlyHint": not writes,
        "destructiveHint": writes,
        "idempotentHint": not writes,
        "openWorldHint": False,
    }


def object_schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def open_object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        schema["required"] = required
    return schema


def standard_output_schema(extra_properties: dict[str, Any] | None = None) -> dict[str, Any]:
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
    return object_schema(properties)


RENDER_ARTIFACT_RESOURCE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "string",
        "maxLength": 256,
        "pattern": r"^figops://jobs/[A-Za-z0-9_-]{1,80}/artifacts/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
    },
    "maxItems": 256,
}
RENDER_PREVIEW_RESOURCE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "string",
        "maxLength": 256,
        "pattern": r"^figops://jobs/[A-Za-z0-9_-]{1,80}/previews/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
    },
    "maxItems": 256,
}


__all__ = [
    "LEGACY_TOOL_NAMES",
    "RENDER_ARTIFACT_RESOURCE_SCHEMA",
    "RENDER_PREVIEW_RESOURCE_SCHEMA",
    "TOOL_HANDLER_NAMES",
    "TOOL_NAMES",
    "ToolDefinition",
    "get_tool_handlers",
    "object_schema",
    "open_object_schema",
    "standard_output_schema",
    "tool_annotations",
]
