"""Closed MCP response schemas for Phase 2 project-render metadata."""

from __future__ import annotations

from hub_core.mcp.tool_schema_common import object_schema

RESOLVED_POLICY_SET_SCHEMA = object_schema(
    {
        "schema_version": {"type": "string", "const": "figops-resolved-policy-set/1"},
        "parameters": {"type": "object", "maxProperties": 64},
    },
    required=["schema_version", "parameters"],
)

RENDER_POLICY_SCHEMA = object_schema(
    {
        "id": {"type": "string"},
        "version": {"type": "string"},
        "source": {"type": "string"},
        "parameters": {"type": "object", "maxProperties": 32},
    },
    required=["id", "version", "source", "parameters"],
)

RENDER_POLICY_CONTEXT_SCHEMA = object_schema(
    {
        "schema_version": {"type": "string", "const": "figops-render-policy-context/1"},
        "source": {
            "type": "string",
            "enum": ["explicit-render-policy", "compatibility-default", "v2-default"],
        },
        "validation_source": {
            "type": "string",
            "enum": ["explicit-validation-target", "compatibility-target-inference", "none"],
        },
        "policy_set_sha256": {"type": "string", "pattern": "^[0-9a-fA-F]{64}$"},
        "policy_set": RESOLVED_POLICY_SET_SCHEMA,
        "render_policy": RENDER_POLICY_SCHEMA,
        "validation_target": {"type": ["string", "null"]},
    },
    required=[
        "schema_version",
        "source",
        "validation_source",
        "policy_set_sha256",
        "policy_set",
        "render_policy",
        "validation_target",
    ],
)

WORKFLOW_INTENT_SCHEMA = object_schema(
    {
        "schema_version": {"type": "string", "const": "figops-workflow-intent/1"},
        "intent": {"type": ["string", "null"], "enum": ["exploration", "execution", "review", "promotion", None]},
        "source": {
            "type": ["string", "null"],
            "enum": ["explicit", "orchestrator", "mcp", "direct_csv", "read_only", "readiness", "legacy", None],
        },
        "provenance": object_schema(
            {
                "active": {"type": "boolean"},
                "step": {"type": ["string", "null"]},
                "tool_name": {"type": "string"},
                "requested_intent": {
                    "type": ["string", "null"],
                    "enum": ["exploration", "execution", "review", "promotion", None],
                },
                "requested_source": {
                    "type": ["string", "null"],
                    "enum": ["explicit", "orchestrator", "mcp", "direct_csv", "read_only", "readiness", "legacy", None],
                },
                "project_status": {"type": "string"},
                "config_source": {"type": "string"},
            },
            required=[
                "active",
                "step",
                "tool_name",
                "requested_intent",
                "requested_source",
                "project_status",
                "config_source",
            ],
        ),
        "fail_closed": {"type": "boolean"},
        "legacy": {"type": "boolean"},
        "execution_allowed": {"type": "boolean"},
        "promotion_allowed": {"type": "boolean"},
        "read_only": {"type": "boolean"},
        "promotable": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}, "maxItems": 64},
    },
    required=[
        "schema_version",
        "intent",
        "source",
        "provenance",
        "fail_closed",
        "legacy",
        "execution_allowed",
        "promotion_allowed",
        "read_only",
        "promotable",
        "issues",
    ],
)

__all__ = ["RENDER_POLICY_CONTEXT_SCHEMA", "WORKFLOW_INTENT_SCHEMA"]
