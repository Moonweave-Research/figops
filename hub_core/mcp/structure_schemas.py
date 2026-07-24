"""Project discovery and structure-normalization MCP schemas."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from hub_core.config_parser import ALLOWED_PROJECT_STATUSES
from hub_core.mcp.tool_schema_common import ToolDefinition, object_schema, standard_output_schema

PROJECT_ROLE_SCHEMA = {"type": "string", "enum": ["master", "module"]}
PROJECT_STATUS_SCHEMA = {"type": "string", "enum": sorted(ALLOWED_PROJECT_STATUSES)}
DISCOVERY_CLASSIFICATION_SCHEMA = {
    "type": "string",
    "enum": ["ephemeral", "folder_role", "invalid", "legacy", "official", "quarantine", "unclassified"],
}
DISCOVERY_ROLE_SCHEMA = {
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
LISTED_PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string"},
        "project_root": {"type": "string"},
        "config_path": {"type": "string"},
        "role": DISCOVERY_ROLE_SCHEMA,
        "status": {"type": "string"},
        "project_status": PROJECT_STATUS_SCHEMA,
        "classification": DISCOVERY_CLASSIFICATION_SCHEMA,
        "errors": {"type": "array", "items": {"type": "string"}},
        "declared_figures": {"type": "integer"},
        "declared_diagrams": {"type": "integer"},
        "target_format": {"type": "string"},
    },
}
PROJECT_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "role": PROJECT_ROLE_SCHEMA,
        "status": PROJECT_STATUS_SCHEMA,
        "project_root": {"type": "string"},
        "config_path": {"type": "string"},
    },
}
STRUCTURE_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "status_code": {"type": "string"},
        "roles": {"type": "object"},
        "graph": {"type": "object"},
        "findings": {"type": "array", "items": {"type": "object"}},
        "unknowns": {"type": "array", "items": {"type": "object"}},
        "proposed_changes": {"type": "array", "items": {"type": "object"}},
    },
    "required": [
        "schema_version",
        "status_code",
        "roles",
        "graph",
        "findings",
        "unknowns",
        "proposed_changes",
    ],
    "additionalProperties": False,
}


def build_project_structure_schemas() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    """Return fresh project schemas while preserving their shared references."""

    return deepcopy(
        (LISTED_PROJECT_SCHEMA, PROJECT_METADATA_SCHEMA, PROJECT_STATUS_SCHEMA, STRUCTURE_AUDIT_SCHEMA)
    )


def build_normalize_project_structure_definition(*, include_host_approval: bool = False) -> ToolDefinition:
    """Build the stable normalization tool contract."""

    input_properties: dict[str, Any] = {
        "project_path": {"type": "string"},
        "dry_run": {
            "type": "boolean",
            "default": True,
            "description": (
                "Preview without writing files. Defaults True like scaffold_project and "
                "batch_check; the two render tools default dry_run False."
            ),
        },
        "move_policy": {
            "type": "string",
            "enum": ["adopt", "copy", "move", "symlink"],
            "default": "adopt",
            "description": (
                "adopt returns read-only proposals; copy requires approved_mappings. "
                "move and symlink remain accepted only to return a stable deprecation error."
            ),
        },
        "include_raw": {"type": "boolean", "default": False},
        "overwrite": {
            "type": "boolean",
            "default": False,
            "description": "Deprecated compatibility argument; true always fails closed.",
        },
        "approved_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["source", "destination", "role"],
                "additionalProperties": False,
            },
            "description": "Explicit mappings accepted by the user after reviewing an adopt proposal.",
        },
        "config_diff": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Reviewed typed project_config.yaml compare-and-swap edits.",
        },
        "hardcoded_unresolved_references": {
            "type": "array",
            "items": {},
            "description": "Unresolved dependencies that intentionally block apply.",
        },
        "confirmation_token": {
            "type": "string",
            "description": "Exact token returned by the reviewed copy-only dry-run.",
        },
    }
    output_properties: dict[str, Any] = {
        "project_root": {"type": "string"},
        "planned_paths": {"type": "array", "items": {"type": "string"}},
        "manifest": {"type": "object"},
        "config_path": {"type": "string"},
        "style_summary": {"type": "object"},
        "validation": {"type": "object"},
        "proposed_mappings": {"type": "array", "items": {"type": "object"}},
        "unresolved_proposals": {"type": "array", "items": {"type": "object"}},
        "plan_digest": {"type": "string"},
        "confirmation_token": {"type": "string"},
        "originals_preserved": {"type": "boolean"},
        "rollback_journal": {"type": "object"},
        "provenance_receipt": {"type": "object"},
    }
    if include_host_approval:
        input_properties["approval_receipt_id"] = {
            "type": "string",
            "description": (
                "Host-issued approval receipt id resolved out-of-band from the trusted authority root. "
                "Never provide approval JSON or reviewer fields in tool arguments."
            ),
        }
        output_properties.update(
            {
                "approval_receipt_id": {"type": ["string", "null"]},
                "host_approval_required": {"type": "boolean"},
                "approval_status": {
                    "type": "string",
                    "enum": ["not_required", "required", "verified", "rejected"],
                },
            }
        )
    return ToolDefinition(
        "figops.normalize_project_structure",
        "Propose migration mappings or apply an explicitly reviewed copy-only structure plan.",
        object_schema(input_properties, required=["project_path"]),
        standard_output_schema(output_properties),
    )
