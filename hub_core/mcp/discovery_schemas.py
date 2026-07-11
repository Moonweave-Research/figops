"""Static MCP resource, template, and prompt discovery definitions.

Tool schemas remain in :mod:`hub_core.mcp.schemas`. Keeping discovery metadata
here prevents static definitions from inflating the live tool registry module
while callers continue to use its compatibility wrappers.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def list_resource_definitions() -> list[dict[str, str]]:
    """Return static MCP resource descriptors."""

    return [
        {
            "uri": "figops://styles",
            "name": "FigOps Styles",
            "description": "Canonical target formats, output formats, profiles, and aliases.",
            "mimeType": "application/json",
        },
        {
            "uri": "figops://profiles",
            "name": "FigOps Style Profiles",
            "description": "Available style profiles and profile aliases.",
            "mimeType": "application/json",
        },
        {
            "uri": "figops://projects",
            "name": "FigOps Projects",
            "description": "Discovered FigOps project metadata using default discovery rules.",
            "mimeType": "application/json",
        },
    ]


def list_resource_templates() -> list[dict[str, str]]:
    """Return static MCP resource-template descriptors."""

    return [
        {
            "uriTemplate": "figops://projects/{project_id}/config",
            "name": "FigOps Project Config",
            "description": "Project configuration YAML resolved by discovered project ID.",
            "mimeType": "application/x-yaml",
        },
        {
            "uriTemplate": "figops://jobs/{job_id}/manifest",
            "name": "FigOps Render Job Manifest",
            "description": "Sanitized render job manifest resolved by job ID.",
            "mimeType": "application/json",
        },
    ]


def list_prompt_definitions(supported_render_plot_types: Iterable[str]) -> list[dict[str, Any]]:
    """Return MCP prompt definitions using the supplied live plot-type names."""

    plot_type_description = ", ".join(supported_render_plot_types)
    return [
        {
            "name": "make_publication_graph_from_csv",
            "description": "Workflow for rendering a publication-style graph from structured CSV data.",
            "arguments": [
                {"name": "data_path", "description": "CSV input path.", "required": True},
                {"name": "x_column", "description": "CSV x-axis column.", "required": True},
                {"name": "y_column", "description": "CSV y-axis column.", "required": True},
                {"name": "target_format", "description": "FigOps target format.", "required": False},
                {"name": "plot_type", "description": plot_type_description, "required": False},
            ],
        },
        {
            "name": "inspect_graph_project_quality",
            "description": "Workflow for inspecting a graph project without executing scripts.",
            "arguments": [
                {"name": "project_id", "description": "Discovered FigOps project ID.", "required": False},
                {"name": "project_path", "description": "Project path.", "required": False},
            ],
        },
        {
            "name": "standardize_existing_graph_project",
            "description": "Workflow for planning safe FigOps project normalization.",
            "arguments": [
                {"name": "project_path", "description": "Existing graph project path.", "required": True},
                {"name": "move_policy", "description": "copy, move, or symlink.", "required": False},
            ],
        },
        {
            "name": "render_project_figure",
            "description": "Workflow for rendering one configured project figure through FigOps MCP.",
            "arguments": [
                {"name": "project_id", "description": "Discovered FigOps project ID.", "required": False},
                {"name": "project_path", "description": "Project path.", "required": False},
                {"name": "figure_id", "description": "Configured figures[].id.", "required": False},
                {"name": "figure_output", "description": "Configured figures[].output.", "required": False},
            ],
        },
    ]
