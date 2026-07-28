"""Optional, explicitly write-gated review-recording MCP schema."""

from __future__ import annotations

from typing import Any

from .tool_schema_common import ToolDefinition, object_schema, standard_output_schema


def review_tool_definitions() -> list[dict[str, Any]]:
    definition = ToolDefinition(
        "figops.record_human_review",
        "Record one validated human-review receipt below a project's declared evidence role.",
        object_schema(
            {
                "project_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Active project path under the configured research root.",
                },
                "figure_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 256,
                    "description": "Trusted configured figure identifier bound to the review subject.",
                },
                "relative_path": {
                    "type": "string",
                    "pattern": r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$",
                    "description": "Canonical POSIX path relative to results/evidence.",
                },
                "review_receipt": {
                    "type": "object",
                    "description": "Closed figops-human-review/1 receipt; no authority is inferred from its fields.",
                },
                "expected_subject": {
                    "type": "object",
                    "description": "Optional host-supplied exact subject binding for the receipt.",
                },
            },
            required=["project_path", "figure_id", "relative_path", "review_receipt"],
        ),
        standard_output_schema(
            {
                "project_path": {"type": "string"},
                "relative_path": {"type": "string"},
                "receipt_id": {"type": "string"},
                "canonical_sha256": {"type": "string"},
                "size_bytes": {"type": "integer"},
                "review_receipt": {"type": "object"},
            }
        ),
    )
    return [definition.to_dict()]


__all__ = ["review_tool_definitions"]
