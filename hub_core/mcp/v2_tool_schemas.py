"""Focused schema definitions for the compact AI-native MCP v2 tools."""

from __future__ import annotations

from typing import Any

from hub_core.artifact_audit import SUPPORTED_POLICY_PACKS
from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, PUBLIC_TARGET_FORMATS
from hub_core.journal_specs import list_supported_preflight_targets
from hub_core.mcp.phase2_render_schemas import RENDER_POLICY_CONTEXT_SCHEMA, WORKFLOW_INTENT_SCHEMA
from hub_core.mcp.tool_schema_common import ToolDefinition, object_schema


def build_v2_tool_definitions(
    *,
    project_id_arg: dict[str, Any],
    project_path_arg: dict[str, Any],
    selector_one_of: list[dict[str, Any]],
) -> list[ToolDefinition]:
    runtime_artifact = object_schema(
        {
            "status": {"type": "string", "enum": ["created", "unavailable"]},
            "uri": {"type": ["string", "null"]},
            "relative_path": {"type": ["string", "null"]},
            "project_relative_path": {"type": ["string", "null"]},
            "sha256": {"type": ["string", "null"], "pattern": "^[0-9a-fA-F]{64}$"},
            "source": {"type": "string", "enum": ["runtime_snapshot"]},
        }
    )
    durable_result = object_schema(
        {
            "status": {"type": "string", "enum": ["promoted", "not_promoted"]},
            "relative_path": {"type": ["string", "null"]},
            "reason_code": {"type": ["string", "null"]},
            "reason": {"type": ["string", "null"]},
            "source": {"type": "string", "enum": ["durable_project_result"]},
        }
    )
    render_output = object_schema(
        {
            "schema_version": {"type": "string"},
            "status": {"type": "string", "enum": ["ok", "warning", "error"]},
            "tool": {"type": "string"},
            "job_id": {"type": "string"},
            "summary": {"type": "string"},
            "artifact": {"type": ["object", "null"]},
            "manifest_uri": {"type": ["string", "null"]},
            "preview_uri": {"type": ["string", "null"]},
            "evidence": {"type": ["object", "null"]},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "errors": {"type": "array", "items": {"type": "string"}},
            "manual_review_needed": {"type": "boolean"},
            "failure_stage": {"type": ["string", "null"]},
            "resolution_hint": {"type": ["string", "null"]},
        }
    )
    project_render_output = {
        **render_output,
        "properties": {
            **render_output["properties"],
            "runtime_availability": {"type": "object"},
            "promotion_eligible": {"type": "boolean"},
            "runtime_artifact": {"anyOf": [runtime_artifact, {"type": "null"}]},
            "durable_result": {"anyOf": [durable_result, {"type": "null"}]},
            "promotion_status": {
                "type": ["string", "null"],
                "enum": ["promoted", "not_promoted", None],
            },
            "promotion_reason": {"type": ["string", "null"]},
            "source_unchanged": {"type": "boolean"},
            "overwrite_scope": {"type": "string", "enum": ["job_workspace_only"]},
            "policy_context": RENDER_POLICY_CONTEXT_SCHEMA,
            "workflow_intent": WORKFLOW_INTENT_SCHEMA,
        },
    }
    return [
        ToolDefinition(
            "figops.inspect_data",
            (
                "Inspect an allowed CSV or TSV under declared sensitivity policy; undeclared, unspecified, "
                "and restricted data return metadata only."
            ),
            object_schema(
                {
                    "data_path": {"type": "string", "minLength": 1, "maxLength": 4096},
                    "external_raw_id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128,
                        "description": (
                            "Required for value samples from a declared external_raw source; "
                            "must match the descriptor id bound to its launcher-approved root."
                        ),
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 512},
                        "maxItems": 256,
                    },
                    "include_samples": {"type": "boolean", "default": False},
                    "sample_rows": {"type": "integer", "minimum": 0, "maximum": 20, "default": 0},
                },
                required=["data_path"],
            ),
            object_schema(
                {
                    "schema_version": {"type": "string"},
                    "status": {"type": "string", "enum": ["available", "unavailable"]},
                    "status_code": {"type": "string"},
                    "availability": {"type": "object"},
                    "access_policy": {
                        "type": "object",
                        "properties": {
                            "classification": {
                                "type": "string",
                                "enum": ["public", "internal", "restricted", "unspecified", "unknown"],
                            },
                            "declaration_source": {"type": "string"},
                            "mode": {"type": "string", "enum": ["metadata_only", "bounded_values"]},
                            "samples_requested": {"type": "boolean"},
                            "samples_allowed": {"type": "boolean"},
                            "reason_code": {"type": "string"},
                            "external_raw_identity": {"type": "object"},
                            "materialized_sha256_verified": {"type": "boolean"},
                        },
                        "required": [
                            "classification",
                            "declaration_source",
                            "mode",
                            "samples_requested",
                            "samples_allowed",
                            "reason_code",
                        ],
                        "additionalProperties": False,
                    },
                    "source": {"type": "object"},
                    "scan": {"type": ["object", "null"]},
                    "columns": {"type": "array", "items": {"type": "object"}},
                    "sample_columns": {"type": "array", "items": {"type": "string"}},
                    "samples": {"type": "array", "items": {"type": "array"}},
                    "truncation": {"type": "object"},
                    "warnings": {"type": "array", "items": {"type": "object"}},
                    "limits": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "figops.render_basic_csv",
            "Render one quick CSV chart with raw labels and no statistics DSL.",
            object_schema(
                {
                    "data_path": {"type": "string", "minLength": 1, "maxLength": 4096},
                    "x": {"type": "string", "minLength": 1, "maxLength": 512},
                    "y": {"type": "string", "minLength": 1, "maxLength": 512},
                    "plot_type": {"type": "string", "enum": ["scatter", "line", "bar"], "default": "scatter"},
                    "series": {"type": "string", "minLength": 1, "maxLength": 512},
                    "facet": {"type": "string", "minLength": 1, "maxLength": 512},
                    "labels": object_schema(
                        {
                            "title": {"type": "string", "maxLength": 512},
                            "x_axis": {"type": "string", "maxLength": 512},
                            "y_axis": {"type": "string", "maxLength": 512},
                        }
                    ),
                    "style_policy": {
                        "type": "string",
                        "enum": sorted(PUBLIC_TARGET_FORMATS),
                        "default": "neutral",
                    },
                    "validation_target": {
                        "type": "string",
                        "enum": sorted(
                            set(list_supported_preflight_targets()) & PUBLIC_TARGET_FORMATS
                        ),
                    },
                    "output_format": {
                        "type": "string",
                        "enum": sorted(ALLOWED_OUTPUT_FORMATS),
                        "default": "png",
                    },
                    "job_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,80}$", "maxLength": 80},
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Replace the existing isolated MCP job workspace only; "
                            "never overwrite the durable project output."
                        ),
                    },
                },
                required=["data_path", "x", "y"],
            ),
            render_output,
        ),
        ToolDefinition(
            "figops.render_project_script",
            "Render one configured project-local .py or .R figure; code and command strings are forbidden.",
            {
                **object_schema(
                    {
                        "project_id": project_id_arg,
                        "project_path": project_path_arg,
                        "figure_id": {"type": "string", "minLength": 1, "maxLength": 512},
                        "figure_output": {"type": "string", "minLength": 1, "maxLength": 4096},
                        "style_policy": {
                            "type": "string",
                            "enum": sorted(PUBLIC_TARGET_FORMATS),
                            "default": "neutral",
                        },
                        "validation_target": {
                            "type": "string",
                            "enum": sorted(
                                set(list_supported_preflight_targets()) & PUBLIC_TARGET_FORMATS
                            ),
                        },
                        "job_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,80}$", "maxLength": 80},
                        "overwrite": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Replace the existing isolated MCP job workspace only; "
                                "never overwrite the durable project output."
                            ),
                        },
                    }
                ),
                "oneOf": selector_one_of,
            },
            project_render_output,
        ),
        ToolDefinition(
            "figops.audit_artifact",
            (
                "Audit validated completed-job evidence with zero or more explicit policy packs. "
                "The public publication-readiness-v1 pack projects internally to "
                "publication-readiness-v2; v2 is not a public enum value. "
                "Required geometry marked not_applicable remains unresolved and requires review."
            ),
            object_schema(
                {
                    "job_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,80}$", "maxLength": 80},
                    "policy_packs": {
                        "type": "array",
                        "description": (
                            "Public policy-pack identifiers only. publication-readiness-v1 is "
                            "projected internally to publication-readiness-v2; the internal id "
                            "must not be supplied by callers."
                        ),
                        "items": {"type": "string", "enum": sorted(SUPPORTED_POLICY_PACKS)},
                        "maxItems": len(SUPPORTED_POLICY_PACKS),
                        "uniqueItems": True,
                        "default": [],
                    },
                },
                required=["job_id"],
            ),
            object_schema(
                {
                    "schema_version": {"type": "string"},
                    "status": {"type": "string", "enum": ["blocked", "needs_revision", "needs_review"]},
                    "job_id": {"type": "string"},
                    "artifact": {"type": ["object", "null"]},
                    "manifest_uri": {"type": "string"},
                    "preview_uri": {"type": ["string", "null"]},
                    "audit": {"type": "object"},
                }
            ),
        ),
    ]


__all__ = ["build_v2_tool_definitions"]
