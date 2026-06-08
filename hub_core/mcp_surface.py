from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import queue
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles

from .config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS, find_config_path, validate_config
from .data_contract import _read_data_safe, _validate_semantic_constraints
from .figure_preflight import validate_figure_preflight
from .project_discovery import ProjectDiscoveryService
from .project_normalization import (
    apply_normalize_project,
    apply_scaffold_project,
    plan_normalize_project,
    plan_scaffold_project,
)
from .runtime_paths import preview_runtime_root, resolve_runtime_root, runtime_root_lookup_candidates
from .utils import ensure_local_files, get_hub_path, get_research_root

TOOL_NAMES = (
    "graphhub.health",
    "graphhub.list_styles",
    "graphhub.list_projects",
    "graphhub.inspect_project",
    "graphhub.validate_project",
    "graphhub.render_csv_graph",
    "graphhub.collect_artifacts",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
WRITE_TOOL_NAMES = (
    "graphhub.render_csv_graph",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
SUPPORTED_RENDER_PLOT_TYPES = {"bar", "line", "scatter", "xy"}
MCP_RENDER_CSV_MAX_BYTES = 64 * 1024 * 1024
MCP_RENDER_TIMEOUT_SECONDS = 120.0
MCP_RENDER_RESULT_QUEUE_TIMEOUT_SECONDS = 5.0
MCP_BATCH_MAX_PROJECTS = 50
MCP_BATCH_TIMEOUT_SECONDS = 30.0

JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_PARSE_ERROR = -32700


def _render_bridge_figure_worker(spec_payload: dict[str, Any], result_queue: multiprocessing.Queue) -> None:
    try:
        from plotting.bridge_renderer import BridgeFigureSpec, render_bridge_figure

        output_path = render_bridge_figure(BridgeFigureSpec(**spec_payload))
        result_queue.put({"status": "ok", "output_path": output_path})
    except Exception as exc:
        result_queue.put({"status": "error", "error": str(exc)})


def _batch_discovery_worker(root: str, max_depth: int, result_queue: multiprocessing.Queue) -> None:
    try:
        projects = ProjectDiscoveryService(
            root,
            include_worktrees=True,
            include_ephemeral=True,
        ).discover(max_depth=max_depth)
        result_queue.put({"status": "ok", "projects": projects})
    except Exception as exc:
        result_queue.put({"status": "error", "error": str(exc)})


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
        "manual_review_needed": {"type": "boolean"},
        "failure_stage": {"type": "string"},
        "resolution_hint": {"type": "string"},
        "manifest_path": {"type": "string"},
        "status_path": {"type": "string"},
        "latest_alias": {"type": "string"},
        "latest_dir": {"type": "string"},
    }
    properties.update(extra_properties or {})
    return _object_schema(properties)


def list_tool_definitions() -> list[dict[str, Any]]:
    root_arg = {"type": "string", "description": "Project scan root. Defaults to Graph Hub research root."}
    project_selector = {
        "project_id": {"type": "string"},
        "project_path": {"type": "string"},
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
            "graphhub.list_styles",
            "Return canonical Graph Hub target formats, output formats, profiles, and aliases.",
            _object_schema(),
            _standard_output_schema(
                {
                    "target_formats": {"type": "array", "items": {"type": "string"}},
                    "output_formats": {"type": "array", "items": {"type": "string"}},
                    "profiles": {"type": "array", "items": {"type": "string"}},
                    "profile_aliases": {"type": "object"},
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
            _standard_output_schema({"projects": {"type": "array", "items": {"type": "object"}}}),
        ),
        ToolDefinition(
            "graphhub.inspect_project",
            "Summarize one project config without running analysis, plotting, or report writers.",
            _object_schema(project_selector),
            _standard_output_schema(
                {
                    "project_metadata": {"type": "object"},
                    "folder_structure_status": {"type": "object"},
                    "data_contract_summary": {"type": "object"},
                    "pipeline_steps": {"type": "object"},
                    "figure_outputs": {"type": "array", "items": {"type": "string"}},
                    "diagram_outputs": {"type": "array", "items": {"type": "string"}},
                    "missing_inputs": {"type": "array", "items": {"type": "string"}},
                    "missing_outputs": {"type": "array", "items": {"type": "string"}},
                    "style_summary": {"type": "object"},
                    "normalization_needed": {"type": "boolean"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.validate_project",
            "Run read-only config, data contract, style, and lockfile checks without executing scripts.",
            _object_schema({**project_selector, "strict_lock": {"type": "boolean", "default": False}}),
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
                    "data_path": {"type": "string"},
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "plot_type": {"type": "string", "enum": sorted(SUPPORTED_RENDER_PLOT_TYPES), "default": "scatter"},
                    "target_format": {"type": "string", "default": "nature"},
                    "profile": {"type": "string", "default": DEFAULT_PROFILE},
                    "output_format": {"type": "string", "default": "png"},
                    "semantic_checks": {"type": "object"},
                    "dry_run": {"type": "boolean", "default": False},
                    "overwrite": {"type": "boolean", "default": False},
                    "job_id": {"type": "string"},
                    "title": {"type": "string"},
                    "x_axis_label": {"type": "string"},
                    "y_axis_label": {"type": "string"},
                    "baseline_path": {"type": "string"},
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
                    "artifact_status": {"type": "string"},
                    "baseline_comparison": {"type": "object"},
                }
            ),
        ),
        ToolDefinition(
            "graphhub.collect_artifacts",
            "Return artifact metadata for a completed MCP render job.",
            _object_schema({"job_id": {"type": "string"}, "baseline_path": {"type": "string"}}, required=["job_id"]),
            _standard_output_schema(
                {
                    "figures": {"type": "array", "items": {"type": "object"}},
                    "diagrams": {"type": "array", "items": {"type": "object"}},
                    "assemblies": {"type": "array", "items": {"type": "object"}},
                    "logs": {"type": "array", "items": {"type": "object"}},
                    "provenance": {"type": "object"},
                    "visual_preflight_status": {"type": "object"},
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
                    "target_format": {"type": "string", "default": "nature"},
                    "template": {"type": "string", "enum": ["standard", "researchos"], "default": "standard"},
                    "dry_run": {"type": "boolean", "default": True},
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
                    "plan_only": {"type": "boolean", "default": True},
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


class GraphHubMCPServer:
    """Dependency-free read-only MCP surface over Graph Hub core contracts."""

    def __init__(
        self,
        *,
        hub_path: str | os.PathLike | None = None,
        research_root: str | os.PathLike | None = None,
        runtime_root: str | os.PathLike | None = None,
    ) -> None:
        self.hub_path = Path(hub_path or get_hub_path()).expanduser().resolve()
        self.research_root = Path(research_root or get_research_root()).expanduser().resolve()
        self._runtime_root_explicit = runtime_root is not None
        self.runtime_root = self._resolve_runtime_root(runtime_root)
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "graphhub.health": self.health,
            "graphhub.list_styles": self.list_styles,
            "graphhub.list_projects": self.list_projects,
            "graphhub.inspect_project": self.inspect_project,
            "graphhub.validate_project": self.validate_project,
            "graphhub.render_csv_graph": self.render_csv_graph,
            "graphhub.collect_artifacts": self.collect_artifacts,
            "graphhub.scaffold_project": self.scaffold_project,
            "graphhub.normalize_project_structure": self.normalize_project_structure,
            "graphhub.batch_check": self.batch_check,
        }

    @staticmethod
    def _resolve_runtime_root(runtime_root: str | os.PathLike | None = None) -> Path:
        if runtime_root:
            return Path(runtime_root).expanduser().resolve()
        return Path(preview_runtime_root()).expanduser().resolve()

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown Graph Hub MCP tool: {name}")

        try:
            structured = handler(arguments)
            is_error = structured.get("status") == "error"
        except Exception as exc:
            structured = self._envelope(
                name,
                arguments,
                status="error",
                summary=f"{name} failed.",
                errors=[str(exc)],
                manual_review_needed=True,
            )
            is_error = True

        return {
            "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, sort_keys=True)}],
            "structuredContent": structured,
            "isError": is_error,
        }

    def health(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self._scan_root(arguments)
        max_depth = self._max_depth(arguments.get("max_depth", 4))
        warnings: list[str] = []
        discovery = {"project_count": 0, "valid_count": 0, "invalid_count": 0, "root": self._display_path(root)}
        if root.exists():
            projects = ProjectDiscoveryService(root).discover(max_depth=max_depth)
            discovery["project_count"] = len(projects)
            discovery["valid_count"] = sum(1 for project in projects if project.valid)
            discovery["invalid_count"] = sum(1 for project in projects if not project.valid)
        else:
            warnings.append(f"Discovery root does not exist: {self._display_path(root)}")

        return self._envelope(
            "graphhub.health",
            arguments,
            summary="Graph Hub MCP surface is available.",
            warnings=warnings,
            hub_path=str(self.hub_path),
            version=self._read_version(),
            python_executable=sys.executable,
            runtime_root=str(self.runtime_root),
            style_format_count=len(ALLOWED_TARGET_FORMATS),
            discovery_status=discovery,
            write_tools_enabled=any(name in self._handlers for name in WRITE_TOOL_NAMES),
        )

    def list_styles(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        return self._envelope(
            "graphhub.list_styles",
            arguments,
            summary=f"{len(ALLOWED_TARGET_FORMATS)} target formats and {len(list_profiles())} profiles available.",
            target_formats=sorted(ALLOWED_TARGET_FORMATS),
            output_formats=sorted(ALLOWED_OUTPUT_FORMATS),
            profiles=list_profiles(),
            profile_aliases=dict(sorted(PROFILE_ALIASES.items())),
            default_target_format="nature",
            default_profile=DEFAULT_PROFILE,
        )

    def list_projects(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self._scan_root(arguments)
        include_invalid = bool(arguments.get("include_invalid", True))
        include_worktrees = bool(arguments.get("include_worktrees", False))
        include_ephemeral = bool(arguments.get("include_ephemeral", False))
        max_depth = self._max_depth(arguments.get("max_depth", 4))

        projects = ProjectDiscoveryService(
            root,
            include_worktrees=include_worktrees,
            include_ephemeral=include_ephemeral,
        ).discover(max_depth=max_depth)
        if not include_invalid:
            projects = [project for project in projects if project.valid]

        serialized = [self._serialize_project(project) for project in projects]
        invalid_count = sum(1 for project in projects if not project.valid)
        return self._envelope(
            "graphhub.list_projects",
            arguments,
            status="warning" if invalid_count else "ok",
            summary=f"Discovered {len(serialized)} project config(s).",
            warnings=[f"{invalid_count} invalid project config(s) found."] if invalid_count else [],
            projects=serialized,
        )

    def inspect_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_path = self._resolve_project_path(arguments)
        loaded = self._load_project_config(project_path)
        if loaded["errors"]:
            return self._envelope(
                "graphhub.inspect_project",
                arguments,
                status="error",
                summary="Project config could not be inspected.",
                errors=loaded["errors"],
                manual_review_needed=True,
            )

        config = loaded["config"]
        project = config.get("project") if isinstance(config.get("project"), dict) else {}
        visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
        analysis_steps = self._list_section(config.get("pipeline", {}), "analysis")
        figures = self._list_section(config, "figures")
        diagrams = self._list_section(config, "diagrams")
        csv_checks = self._list_section(config.get("data_contract", {}), "csv_checks")
        figure_outputs = self._outputs(figures)
        diagram_outputs = self._outputs(diagrams)

        return self._envelope(
            "graphhub.inspect_project",
            arguments,
            summary=f"Inspected project config at {loaded['config_relpath']}.",
            project_metadata={
                "name": project.get("name") or project_path.name,
                "project_root": self._display_path(project_path),
                "config_path": loaded["config_relpath"],
            },
            folder_structure_status={
                "has_project_config": True,
                "has_hub_scripts": (project_path / "hub_scripts").is_dir(),
                "has_results": (project_path / "results").is_dir(),
                "uses_legacy_config_path": loaded["config_relpath"] == "scripts/project_config.yaml",
            },
            data_contract_summary={
                "csv_check_count": len(csv_checks),
                "paths": [
                    str(check.get("path")) for check in csv_checks if isinstance(check, dict) and check.get("path")
                ],
            },
            pipeline_steps={"analysis": len(analysis_steps)},
            figure_outputs=figure_outputs,
            diagram_outputs=diagram_outputs,
            missing_inputs=self._missing_inputs(project_path, analysis_steps),
            missing_outputs=self._missing_paths(project_path, figure_outputs + diagram_outputs),
            style_summary={
                "target_format": str(visual_style.get("target_format") or "nature").lower(),
                "font_scale": visual_style.get("font_scale", 1.0),
                "profile": visual_style.get("profile", DEFAULT_PROFILE),
            },
            normalization_needed=loaded["config_relpath"] == "scripts/project_config.yaml",
        )

    def validate_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_path = self._resolve_project_path(arguments)
        loaded = self._load_project_config(project_path, allow_invalid=True)
        config_errors = list(loaded["errors"])
        config = loaded["config"] if isinstance(loaded["config"], dict) else {}
        if isinstance(config, dict):
            config_errors = validate_config(config)

        data_contract_errors = [error for error in config_errors if error.startswith("data_contract.")]
        style_errors = [
            error
            for error in config_errors
            if error.startswith("Invalid visual_style") or error.startswith("visual_style.")
        ]
        lockfile_status = self._lockfile_status(project_path, config, strict=bool(arguments.get("strict_lock", False)))
        valid = not config_errors and lockfile_status["valid"]
        if valid:
            next_action = "ready_for_render"
        elif style_errors:
            next_action = "fix_style_contract"
        elif data_contract_errors:
            next_action = "fix_data_contract"
        else:
            next_action = "fix_project_config"

        return self._envelope(
            "graphhub.validate_project",
            arguments,
            status="ok" if valid else "warning",
            summary="Project config is valid." if valid else "Project config needs changes before rendering.",
            warnings=[] if valid else ["Project validation reported warnings or errors."],
            valid=valid,
            config_errors=config_errors,
            data_contract_errors=data_contract_errors,
            lockfile_status=lockfile_status,
            style_errors=style_errors,
            recommended_next_action=next_action,
        )

    def render_csv_graph(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        job_root = self._mcp_jobs_root() / job_id
        try:
            data_path = self._input_file_path(arguments.get("data_path"))
            x_column = self._required_string(arguments, "x_column")
            y_column = self._required_string(arguments, "y_column")
        except ValueError as exc:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid CSV input settings.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix data_path and CSV column inputs before rendering.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        plot_type = str(arguments.get("plot_type") or "scatter").strip().lower()
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        profile = str(arguments.get("profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
        output_format = str(arguments.get("output_format") or "png").strip().lower().lstrip(".")
        raw_semantic_checks = arguments.get("semantic_checks", {})
        semantic_checks = {} if raw_semantic_checks is None else raw_semantic_checks

        if plot_type not in SUPPORTED_RENDER_PLOT_TYPES:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid plot settings.",
                errors=[
                    f"Invalid plot_type '{plot_type}'. Supported: "
                    f"{', '.join(sorted(SUPPORTED_RENDER_PLOT_TYPES))}."
                ],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported plot_type.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        style_errors = self._render_style_errors(target_format, output_format, profile)
        if style_errors:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid style settings.",
                errors=style_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported target_format, output_format, and profile.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        if not isinstance(semantic_checks, dict):
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid data contract settings.",
                errors=["semantic_checks must be an object."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Provide semantic_checks as an object keyed by CSV column.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        config = self._render_project_config(
            target_format=target_format,
            profile=profile,
            output_format=output_format,
            x_column=x_column,
            y_column=y_column,
            semantic_checks=semantic_checks,
        )
        config_errors = validate_config(config)
        if config_errors:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid project config settings.",
                errors=config_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Fix the generated render project_config settings.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        ensure_local_files([str(data_path)])
        contract_result = self._validate_render_data_contract(
            data_path,
            required_columns=[x_column, y_column, *[str(key) for key in semantic_checks]],
            semantic_checks=semantic_checks,
        )
        contract_errors = contract_result["errors"]
        calculation_checks = contract_result["calculation_checks"]
        if contract_errors:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render data contract validation failed.",
                errors=contract_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix the CSV data contract, data_path, columns, or semantic_checks.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                calculation_checks=calculation_checks,
            )
        if dry_run:
            calculation_warnings = self._calculation_warnings(calculation_checks)
            manual_review_needed = bool(calculation_checks.get("manual_review_needed"))
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="warning" if manual_review_needed else "ok",
                summary=(
                    "Render request validated with calculation warnings in dry-run mode; no files were created."
                    if manual_review_needed
                    else "Render request validated in dry-run mode; no files were created."
                ),
                warnings=calculation_warnings,
                manual_review_needed=manual_review_needed,
                is_dry_run=True,
                job_id=job_id,
                job_root=str(job_root),
                output_path=str(job_root / "results" / "figures" / f"graph.{output_format}"),
                config_path=str(job_root / "project_config.yaml"),
                manifest_path=str(job_root / "manifest.json"),
                style_summary={"target_format": target_format, "profile": profile, "output_format": output_format},
                visual_preflight_status={"passed": None, "checks": [], "warnings": ["dry_run"]},
                failure_stage="",
                resolution_hint="",
                artifact_status="validated",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                calculation_checks=calculation_checks,
            )
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_jobs_root() / job_id
        if job_root.exists() and not overwrite:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render job already exists.",
                errors=[f"Render job already exists: {self._runtime_uri(job_root)}. Set overwrite=true to replace it."],
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                job_root=str(job_root),
                failure_stage="EXPORT",
                resolution_hint="Set overwrite=true to replace the existing MCP render job.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        if job_root.exists() and overwrite:
            shutil.rmtree(job_root)

        job_data_path = job_root / "data" / "input.csv"
        output_path = job_root / "results" / "figures" / f"graph.{output_format}"
        config_path = job_root / "project_config.yaml"
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_render"
        created_paths: list[str] = []
        try:
            job_data_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_path, job_data_path)
            created_paths.append(str(job_data_path))

            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            created_paths.append(str(config_path))

            self._run_render_bridge_figure(
                {
                    "csv_path": str(job_data_path),
                    "output_path": str(output_path),
                    "plot_type": plot_type,
                    "x_column": x_column,
                    "y_column": y_column,
                    "title": str(arguments.get("title") or "Graph Hub MCP render"),
                    "x_axis_label": str(arguments.get("x_axis_label") or x_column),
                    "y_axis_label": str(arguments.get("y_axis_label") or y_column),
                    "target_format": target_format,
                    "profile_name": profile,
                }
            )
            figures = self._rendered_figure_artifacts(output_path)
            created_paths.extend(str(figure["path"]) for figure in figures)
            preflight = self._safe_preflight(output_path, target_format)
            preflight_warnings = self._preflight_warnings(preflight)
            baseline_comparison = self._baseline_comparison(output_path, arguments.get("baseline_path"))
            baseline_warnings = self._baseline_warnings(baseline_comparison)
            calculation_warnings = self._calculation_warnings(calculation_checks)
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or bool(calculation_checks.get("manual_review_needed"))
            )
            status = "warning" if manual_review_needed else "ok"
            artifact_status = self._artifact_status(preflight, baseline_comparison)
            created_paths.extend([str(manifest_path), str(status_path)])
            manifest = {
                "job_id": job_id,
                "job_root": str(job_root),
                "source_data_path": str(data_path),
                "copied_data_path": str(job_data_path),
                "config_path": str(config_path),
                "status_path": str(status_path),
                "latest_dir": str(latest_dir),
                "latest_alias": str(latest_dir),
                "figures": figures,
                "diagrams": [],
                "assemblies": [],
                "logs": [],
                "created_paths": created_paths,
                "modified_paths": [],
                "skipped_paths": [],
                "style_summary": {
                    "target_format": target_format,
                    "profile": profile,
                    "output_format": output_format,
                },
                "visual_preflight_status": preflight,
                "failure_stage": "",
                "resolution_hint": "",
                "artifact_status": artifact_status,
                "baseline_comparison": baseline_comparison,
                "manual_review_needed": manual_review_needed,
                "calculation_checks": calculation_checks,
            }
            status_payload = self._render_status_payload(
                job_id=job_id,
                status=status,
                summary="Rendered CSV graph." if status == "ok" else "Rendered CSV graph with preflight warnings.",
                manifest_path=manifest_path,
                output_path=output_path,
                artifact_status=artifact_status,
                manual_review_needed=manual_review_needed,
                failure_stage="",
                resolution_hint="",
            )
            status_payload["calculation_checks"] = calculation_checks
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            status_path.write_text(
                json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            latest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, latest_dir / "manifest.json")
            shutil.copy2(status_path, latest_dir / "status.json")
        except Exception as exc:
            failure_stage = "TIMEOUT" if "timed out" in str(exc).lower() else "PLOT"
            resolution_hint = (
                "Increase the render timeout or simplify the figure."
                if failure_stage == "TIMEOUT"
                else "Inspect the render engine error and graph input settings."
            )
            if job_root.exists():
                baseline_comparison = self._baseline_comparison(None, arguments.get("baseline_path"))
                created_paths = self._write_render_failure_artifacts(
                    job_id=job_id,
                    job_root=job_root,
                    source_data_path=data_path,
                    copied_data_path=job_data_path,
                    config_path=config_path,
                    output_path=output_path,
                    manifest_path=manifest_path,
                    status_path=status_path,
                    latest_dir=latest_dir,
                    created_paths=created_paths,
                    failure_stage=failure_stage,
                    resolution_hint=resolution_hint,
                    baseline_comparison=baseline_comparison,
                )
            else:
                baseline_comparison = self._baseline_comparison(None, arguments.get("baseline_path"))
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render execution failed.",
                created_paths=created_paths,
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                job_root=str(job_root),
                manifest_path=str(manifest_path) if job_root.exists() else "",
                status_path=str(status_path) if job_root.exists() else "",
                latest_dir=str(latest_dir) if job_root.exists() else "",
                latest_alias=str(latest_dir) if job_root.exists() else "",
                failure_stage=failure_stage,
                resolution_hint=resolution_hint,
                artifact_status="failed",
                baseline_comparison=baseline_comparison,
            )

        return self._envelope(
            "graphhub.render_csv_graph",
            arguments,
            status=status,
            summary="Rendered CSV graph." if status == "ok" else "Rendered CSV graph with preflight warnings.",
            created_paths=created_paths,
            artifact_resources=[f"file://{figure['path']}" for figure in manifest["figures"]],
            warnings=preflight_warnings + baseline_warnings + calculation_warnings,
            manual_review_needed=manual_review_needed,
            is_dry_run=False,
            job_id=job_id,
            job_root=str(job_root),
            output_path=str(output_path),
            config_path=str(config_path),
            manifest_path=str(manifest_path),
            status_path=str(status_path),
            latest_dir=str(latest_dir),
            latest_alias=str(latest_dir),
            style_summary=manifest["style_summary"],
            visual_preflight_status=preflight,
            failure_stage="",
            resolution_hint="",
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
            calculation_checks=calculation_checks,
        )

    def _activate_runtime_root_for_runtime_access(self) -> None:
        if not self._runtime_root_explicit:
            self.runtime_root = Path(resolve_runtime_root()).expanduser().resolve()

    @staticmethod
    def _render_status_payload(
        *,
        job_id: str,
        status: str,
        summary: str,
        manifest_path: Path,
        output_path: Path,
        artifact_status: str,
        manual_review_needed: bool,
        failure_stage: str,
        resolution_hint: str,
    ) -> dict[str, Any]:
        return {
            "engine_target": "graphhub_mcp_render",
            "job_id": job_id,
            "status": status,
            "summary": summary,
            "manifest_path": str(manifest_path),
            "output_path": str(output_path),
            "artifact_status": artifact_status,
            "manual_review_needed": manual_review_needed,
            "failure_stage": failure_stage,
            "resolution_hint": resolution_hint,
        }

    def _write_render_failure_artifacts(
        self,
        *,
        job_id: str,
        job_root: Path,
        source_data_path: Path,
        copied_data_path: Path,
        config_path: Path,
        output_path: Path,
        manifest_path: Path,
        status_path: Path,
        latest_dir: Path,
        created_paths: list[str],
        failure_stage: str,
        resolution_hint: str,
        baseline_comparison: dict[str, Any],
    ) -> list[str]:
        created = list(created_paths)
        manifest = {
            "job_id": job_id,
            "job_root": str(job_root),
            "source_data_path": str(source_data_path),
            "copied_data_path": str(copied_data_path) if copied_data_path.exists() else "",
            "config_path": str(config_path) if config_path.exists() else "",
            "status_path": str(status_path),
            "latest_dir": str(latest_dir),
            "latest_alias": str(latest_dir),
            "figures": [],
            "diagrams": [],
            "assemblies": [],
            "logs": [],
            "created_paths": created,
            "modified_paths": [],
            "skipped_paths": [],
            "style_summary": {},
            "visual_preflight_status": {"passed": False, "checks": [], "warnings": ["render_execution_failed"]},
            "failure_stage": failure_stage,
            "resolution_hint": resolution_hint,
            "artifact_status": "failed",
            "baseline_comparison": baseline_comparison,
            "manual_review_needed": True,
        }
        status_payload = self._render_status_payload(
            job_id=job_id,
            status="error",
            summary="Render execution failed.",
            manifest_path=manifest_path,
            output_path=output_path,
            artifact_status="failed",
            manual_review_needed=True,
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        status_path.write_text(
            json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        for path in (manifest_path, status_path):
            path_text = str(path)
            if path_text not in created:
                created.append(path_text)
        manifest["created_paths"] = created
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        latest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest_path, latest_dir / "manifest.json")
        shutil.copy2(status_path, latest_dir / "status.json")
        return created

    @staticmethod
    def _run_render_bridge_figure(spec_payload: dict[str, Any]) -> None:
        result_queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
        process = multiprocessing.Process(
            target=_render_bridge_figure_worker,
            args=(spec_payload, result_queue),
            name="graphhub-mcp-render",
        )
        process.start()
        process.join(MCP_RENDER_TIMEOUT_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(5)
            raise TimeoutError(f"Render timed out after {MCP_RENDER_TIMEOUT_SECONDS:.1f} seconds.")
        if process.exitcode not in (0, None):
            raise RuntimeError(f"Render worker exited with code {process.exitcode}.")
        try:
            result = result_queue.get(timeout=MCP_RENDER_RESULT_QUEUE_TIMEOUT_SECONDS)
        except queue.Empty as exc:
            raise RuntimeError("Render worker exited without returning a result.") from exc
        if result.get("status") != "ok":
            raise RuntimeError(str(result.get("error") or "Render worker failed."))

    def collect_artifacts(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = self._render_job_id(arguments.get("job_id"))
        manifest_path = self._find_job_manifest_path(job_id)
        if not manifest_path.exists():
            return self._envelope(
                "graphhub.collect_artifacts",
                arguments,
                status="error",
                summary="Render job manifest was not found.",
                errors=[f"Manifest not found: {self._runtime_uri(manifest_path)}"],
                manual_review_needed=True,
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._envelope(
                "graphhub.collect_artifacts",
                arguments,
                status="error",
                summary="Render job manifest could not be read.",
                errors=[str(exc)],
                manual_review_needed=True,
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )

        preflight = manifest.get("visual_preflight_status") or {}
        figures = manifest.get("figures") if isinstance(manifest.get("figures"), list) else []
        preflight_warnings = self._preflight_warnings(preflight)
        artifact_path = (
            Path(str(figures[0]["path"]))
            if figures and isinstance(figures[0], dict) and figures[0].get("path")
            else None
        )
        baseline_comparison = (
            self._baseline_comparison(artifact_path, arguments.get("baseline_path"))
            if arguments.get("baseline_path")
            else manifest.get("baseline_comparison") or self._baseline_comparison(None, None)
        )
        baseline_warnings = self._baseline_warnings(baseline_comparison)
        persisted_artifact_status = str(manifest.get("artifact_status") or "").strip()
        persisted_failure_stage = str(manifest.get("failure_stage") or "").strip()
        persisted_resolution_hint = str(manifest.get("resolution_hint") or "").strip()
        persisted_failed = persisted_artifact_status == "failed" or bool(persisted_failure_stage)
        manual_review_needed = (
            bool(manifest.get("manual_review_needed"))
            or bool(preflight_warnings)
            or (baseline_comparison["checked"] and not baseline_comparison["matched"])
        )
        status = (
            "error"
            if persisted_failed
            else ("warning" if manual_review_needed or preflight.get("passed") is False else "ok")
        )
        artifact_status = (
            persisted_artifact_status
            if persisted_failed
            else self._artifact_status(preflight, baseline_comparison)
        )
        return self._envelope(
            "graphhub.collect_artifacts",
            arguments,
            status=status,
            summary=f"Collected artifacts for render job {job_id}.",
            artifact_resources=[f"file://{figure['path']}" for figure in figures if isinstance(figure, dict)],
            warnings=preflight_warnings + baseline_warnings,
            created_paths=self._manifest_path_list(manifest, "created_paths"),
            modified_paths=self._manifest_path_list(manifest, "modified_paths"),
            skipped_paths=self._manifest_path_list(manifest, "skipped_paths"),
            manual_review_needed=manual_review_needed,
            job_id=job_id,
            figures=figures,
            diagrams=manifest.get("diagrams") or [],
            assemblies=manifest.get("assemblies") or [],
            logs=manifest.get("logs") or [],
            manifest_path=str(manifest_path),
            status_path=str(manifest.get("status_path", "")),
            latest_dir=str(manifest.get("latest_dir", "")),
            latest_alias=str(manifest.get("latest_alias", "")),
            failure_stage=persisted_failure_stage,
            resolution_hint=persisted_resolution_hint,
            provenance={
                "job_id": job_id,
                "manifest_path": str(manifest_path),
                "status_path": str(manifest.get("status_path", "")),
                "latest_dir": str(manifest.get("latest_dir", "")),
                "latest_alias": str(manifest.get("latest_alias", "")),
                "job_root": manifest.get("job_root", ""),
            },
            visual_preflight_status=preflight,
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
        )

    def scaffold_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_name = self._required_string(arguments, "project_name")
        project_root = Path(self._required_string(arguments, "project_root"))
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        template = str(arguments.get("template") or "standard").strip().lower()
        dry_run = bool(arguments.get("dry_run", True))
        overwrite = bool(arguments.get("overwrite", False))
        manifest = plan_scaffold_project(
            project_root=project_root,
            hub_path=self.hub_path,
            project_name=project_name,
            target_format=target_format,
            template=template,
        )
        public_manifest = self._public_manifest(manifest)
        planned_paths = self._manifest_destinations(public_manifest)
        config_path = Path(str(manifest["project_root"])) / "project_config.yaml"
        style_summary = self._manifest_style_summary(manifest)
        validation = self._validation_summary(config_path)
        if dry_run:
            return self._envelope(
                "graphhub.scaffold_project",
                arguments,
                summary=f"Planned scaffold for project {project_name}.",
                is_dry_run=True,
                project_root=str(manifest["project_root"]),
                project_name=project_name,
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=str(Path(str(manifest["project_root"])) / ".graphhub_scaffold_manifest.json"),
                config_path=str(config_path),
                style_summary=style_summary,
                validation=validation,
            )
        try:
            applied = apply_scaffold_project(manifest, overwrite=overwrite)
        except FileExistsError as exc:
            return self._envelope(
                "graphhub.scaffold_project",
                arguments,
                status="error",
                summary="Scaffold destination already exists.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                project_root=str(manifest["project_root"]),
                project_name=project_name,
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=str(Path(str(manifest["project_root"])) / ".graphhub_scaffold_manifest.json"),
                config_path=str(config_path),
                style_summary=style_summary,
                validation=validation,
            )
        validation = self._validation_summary(config_path)
        return self._envelope(
            "graphhub.scaffold_project",
            arguments,
            summary=f"Created scaffold for project {project_name}.",
            created_paths=applied["created_paths"],
            modified_paths=applied["modified_paths"],
            skipped_paths=applied["skipped_paths"],
            is_dry_run=False,
            project_root=str(manifest["project_root"]),
            project_name=project_name,
            planned_paths=planned_paths,
            manifest=applied["manifest"],
            manifest_path=str(Path(str(manifest["project_root"])) / ".graphhub_scaffold_manifest.json"),
            config_path=str(config_path),
            style_summary=style_summary,
            validation=validation,
        )

    def normalize_project_structure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_path = Path(self._required_string(arguments, "project_path"))
        plan_only = bool(arguments.get("plan_only", True))
        move_policy = str(arguments.get("move_policy") or "copy").strip().lower()
        include_raw = bool(arguments.get("include_raw", False))
        overwrite = bool(arguments.get("overwrite", False))
        manifest = plan_normalize_project(project_path=project_path, move_policy=move_policy, include_raw=include_raw)
        public_manifest = self._public_manifest(manifest)
        planned_paths = self._manifest_destinations(public_manifest)
        project_root = Path(str(manifest["project_root"]))
        config_path = project_root / "project_config.yaml"
        validation = self._validation_summary(config_path)
        if plan_only:
            return self._envelope(
                "graphhub.normalize_project_structure",
                arguments,
                summary=f"Planned normalization for {project_root.name}.",
                is_dry_run=True,
                project_root=str(project_root),
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=str(project_root / ".graphhub_normalization_manifest.json"),
                config_path=str(config_path),
                style_summary=manifest["style_summary"],
                validation=validation,
            )
        try:
            applied = apply_normalize_project(manifest, hub_path=self.hub_path, overwrite=overwrite)
        except FileExistsError as exc:
            return self._envelope(
                "graphhub.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization destination already exists.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                project_root=str(project_root),
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=str(project_root / ".graphhub_normalization_manifest.json"),
                config_path=str(config_path),
                style_summary=manifest["style_summary"],
                validation=validation,
            )
        validation = self._validation_summary(config_path)
        validation_failed = validation.get("checked") is True and validation.get("valid") is False
        return self._envelope(
            "graphhub.normalize_project_structure",
            arguments,
            status="warning" if validation_failed else "ok",
            summary=(
                f"Applied normalization for {project_root.name}, but project validation still needs changes."
                if validation_failed
                else f"Applied normalization for {project_root.name}."
            ),
            created_paths=applied["created_paths"],
            modified_paths=applied["modified_paths"],
            skipped_paths=applied["skipped_paths"],
            warnings=["Normalized project config did not pass validation."] if validation_failed else [],
            manual_review_needed=validation_failed,
            is_dry_run=False,
            project_root=str(project_root),
            planned_paths=planned_paths,
            manifest=applied["manifest"],
            manifest_path=str(project_root / ".graphhub_normalization_manifest.json"),
            config_path=str(config_path),
            style_summary=applied["manifest"]["style_summary"],
            validation=validation,
        )

    def batch_check(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self._scan_root(arguments)
        max_depth = self._max_depth(arguments.get("max_depth", 4))
        max_projects = self._batch_max_projects(arguments.get("max_projects", 20))
        include_invalid = bool(arguments.get("include_invalid", False))
        include_legacy = bool(arguments.get("include_legacy", False))
        include_worktrees = bool(arguments.get("include_worktrees", False))
        include_ephemeral = bool(arguments.get("include_ephemeral", False))
        dry_run = bool(arguments.get("dry_run", True))
        batch_id = self._render_job_id(arguments.get("batch_id") or f"batch-{uuid.uuid4().hex[:12]}")
        batch_root = self._mcp_jobs_root() / batch_id
        manifest_path = batch_root / "batch_manifest.json"
        resumed_from = ""
        previously_checked = set()

        if arguments.get("resume_manifest_path"):
            resume_path = Path(self._required_string(arguments, "resume_manifest_path")).expanduser().resolve()
            resumed_from = str(resume_path)
            try:
                resume_manifest = json.loads(resume_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return self._envelope(
                    "graphhub.batch_check",
                    arguments,
                    status="error",
                    summary="Batch resume manifest could not be read.",
                    errors=[str(exc)],
                    manual_review_needed=True,
                    is_dry_run=dry_run,
                    batch_id=batch_id,
                    batch_root=str(batch_root),
                    manifest_path=str(manifest_path),
                    checked_projects=[],
                    skipped_projects=[],
                    resumed_from=resumed_from,
                    log_paths=[],
                )
            resume_root = Path(str(resume_manifest.get("root") or "")).expanduser().resolve()
            if resume_root != root:
                return self._envelope(
                    "graphhub.batch_check",
                    arguments,
                    status="error",
                    summary="Batch resume manifest does not match the requested root.",
                    errors=["Resume manifest was created for a different root."],
                    manual_review_needed=True,
                    is_dry_run=dry_run,
                    batch_id=batch_id,
                    batch_root=str(batch_root),
                    manifest_path=str(manifest_path),
                    checked_projects=[],
                    skipped_projects=[],
                    resumed_from=resumed_from,
                    log_paths=[],
                )
            previously_checked = {
                str(project.get("project_id"))
                for project in resume_manifest.get("checked_projects", [])
                if isinstance(project, dict) and project.get("project_id")
            }

        started_at = time.monotonic()
        discovered, discovery_timed_out, discovery_warnings = self._discover_batch_projects(
            root,
            max_depth=max_depth,
            timeout_seconds=MCP_BATCH_TIMEOUT_SECONDS,
        )
        checked_projects: list[dict[str, Any]] = []
        skipped_projects: list[dict[str, Any]] = []
        warnings: list[str] = list(discovery_warnings)
        timed_out = discovery_timed_out

        for project in discovered:
            if time.monotonic() - started_at >= MCP_BATCH_TIMEOUT_SECONDS:
                timed_out = True
                warnings.append(f"Batch check timed out after {MCP_BATCH_TIMEOUT_SECONDS:.1f} seconds.")
                break

            skip_reason = self._batch_skip_reason(
                project,
                include_invalid=include_invalid,
                include_legacy=include_legacy,
                include_worktrees=include_worktrees,
                include_ephemeral=include_ephemeral,
                previously_checked=previously_checked,
            )
            if skip_reason:
                skipped_projects.append(self._batch_skipped_project(project, skip_reason))
                continue

            if len(checked_projects) >= max_projects:
                skipped_projects.append(self._batch_skipped_project(project, "max_projects_exceeded"))
                continue

            checked_projects.append(self._batch_checked_project(root, project))

        manifest = {
            "batch_id": batch_id,
            "batch_root": str(batch_root),
            "root": str(root),
            "max_depth": max_depth,
            "max_projects": max_projects,
            "checked_projects": checked_projects,
            "skipped_projects": skipped_projects,
            "resumed_from": resumed_from,
            "timed_out": timed_out,
            "warnings": warnings,
        }

        created_paths: list[str] = []
        log_paths: list[str] = []
        if not dry_run:
            self._activate_runtime_root_for_runtime_access()
            batch_root = self._mcp_jobs_root() / batch_id
            manifest_path = batch_root / "batch_manifest.json"
            manifest["batch_root"] = str(batch_root)
            batch_root.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            created_paths.append(str(manifest_path))
            log_paths.append(str(manifest_path))

        status = "warning" if timed_out else "ok"
        return self._envelope(
            "graphhub.batch_check",
            arguments,
            status=status,
            summary=(
                f"Batch checked {len(checked_projects)} project(s) with timeout."
                if timed_out
                else f"Batch checked {len(checked_projects)} project(s)."
            ),
            created_paths=created_paths,
            warnings=warnings,
            manual_review_needed=timed_out,
            is_dry_run=dry_run,
            batch_id=batch_id,
            batch_root=str(batch_root),
            manifest_path=str(manifest_path),
            checked_projects=checked_projects,
            skipped_projects=skipped_projects,
            resumed_from=resumed_from,
            log_paths=log_paths,
        )

    def _find_job_manifest_path(self, job_id: str) -> Path:
        candidate_roots = [self.runtime_root]
        if not self._runtime_root_explicit:
            candidate_roots.extend(Path(path) for path in runtime_root_lookup_candidates())

        seen = set()
        for root in candidate_roots:
            manifest_path = Path(root).expanduser().resolve() / "mcp_jobs" / job_id / "manifest.json"
            key = str(manifest_path)
            if key in seen:
                continue
            seen.add(key)
            if manifest_path.exists():
                return manifest_path
        return Path(candidate_roots[0]).expanduser().resolve() / "mcp_jobs" / job_id / "manifest.json"

    @staticmethod
    def _public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        public = dict(manifest)
        public["entries"] = [GraphHubMCPServer._public_manifest_entry(entry) for entry in manifest.get("entries", [])]
        return public

    @staticmethod
    def _public_manifest_entry(entry: dict[str, Any]) -> dict[str, Any]:
        public = dict(entry)
        public.pop("content", None)
        return public

    @staticmethod
    def _manifest_destinations(manifest: dict[str, Any]) -> list[str]:
        paths = []
        for entry in manifest.get("entries", []):
            destination = entry.get("destination")
            if isinstance(destination, str) and destination:
                paths.append(destination)
        return paths

    @staticmethod
    def _manifest_style_summary(manifest: dict[str, Any]) -> dict[str, Any]:
        for entry in manifest.get("entries", []):
            if entry.get("destination") != "project_config.yaml":
                continue
            raw_config = entry.get("content")
            if not isinstance(raw_config, str):
                continue
            try:
                config = yaml.safe_load(raw_config) or {}
            except yaml.YAMLError:
                break
            visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
            presets = config.get("presets") if isinstance(config.get("presets"), dict) else {}
            return {
                "target_format": str(visual_style.get("target_format") or "nature"),
                "profile": str(visual_style.get("profile") or DEFAULT_PROFILE),
                "presets": sorted(str(key) for key in presets),
                "style_update_applied": True,
            }
        return {"target_format": "nature", "profile": DEFAULT_PROFILE, "presets": [], "style_update_applied": False}

    @staticmethod
    def _validation_summary(config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {"checked": False, "valid": None, "errors": []}
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            return {"checked": True, "valid": False, "errors": [str(exc)]}
        errors = validate_config(config)
        return {"checked": True, "valid": not errors, "errors": errors}

    @staticmethod
    def _manifest_path_list(manifest: dict[str, Any], key: str) -> list[str]:
        value = manifest.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _preflight_warnings(preflight: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        raw_warnings = preflight.get("warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(str(warning) for warning in raw_warnings)
        raw_checks = preflight.get("checks")
        if isinstance(raw_checks, list):
            for check in raw_checks:
                if isinstance(check, dict) and check.get("passed") is False:
                    detail = check.get("detail")
                    if detail:
                        warnings.append(str(detail))
        return warnings

    @staticmethod
    def _artifact_status(preflight: dict[str, Any], baseline_comparison: dict[str, Any]) -> str:
        if baseline_comparison.get("checked") and baseline_comparison.get("matched") is True:
            return "baseline_matched"
        if baseline_comparison.get("checked") and baseline_comparison.get("matched") is False:
            return "manual_review_needed"
        if preflight.get("passed") is True and not GraphHubMCPServer._preflight_warnings(preflight):
            return "preflight_passed"
        if preflight.get("passed") is None:
            return "validated"
        if preflight.get("passed") is False or GraphHubMCPServer._preflight_warnings(preflight):
            return "manual_review_needed"
        return "created"

    @staticmethod
    def _baseline_comparison(artifact_path: Path | None, raw_baseline_path: Any) -> dict[str, Any]:
        if not isinstance(raw_baseline_path, str) or not raw_baseline_path.strip():
            return {"checked": False, "matched": None, "status": "not_checked", "warnings": []}

        baseline_path = Path(raw_baseline_path).expanduser().resolve()
        warnings: list[str] = []
        if artifact_path is None:
            warnings.append("Baseline comparison requested but no artifact path was available.")
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": str(baseline_path),
                "artifact_path": "",
                "algorithm": "sha256",
                "warnings": warnings,
            }
        artifact_path = Path(artifact_path).expanduser().resolve()
        if not baseline_path.is_file():
            warnings.append("Baseline comparison requested but baseline_path is not a file.")
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": str(baseline_path),
                "artifact_path": str(artifact_path),
                "algorithm": "sha256",
                "warnings": warnings,
            }
        if not artifact_path.is_file():
            warnings.append("Baseline comparison requested but artifact file is missing.")
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": str(baseline_path),
                "artifact_path": str(artifact_path),
                "algorithm": "sha256",
                "warnings": warnings,
            }

        artifact_sha = GraphHubMCPServer._file_sha256(artifact_path)
        baseline_sha = GraphHubMCPServer._file_sha256(baseline_path)
        matched = artifact_sha == baseline_sha
        return {
            "checked": True,
            "matched": matched,
            "status": "baseline_matched" if matched else "manual_review_needed",
            "baseline_path": str(baseline_path),
            "artifact_path": str(artifact_path),
            "algorithm": "sha256",
            "artifact_sha256": artifact_sha,
            "baseline_sha256": baseline_sha,
            "warnings": [] if matched else ["Artifact does not match baseline."],
        }

    @staticmethod
    def _baseline_warnings(baseline_comparison: dict[str, Any]) -> list[str]:
        raw_warnings = baseline_comparison.get("warnings")
        return [str(warning) for warning in raw_warnings] if isinstance(raw_warnings, list) else []

    @staticmethod
    def _calculation_warnings(calculation_checks: dict[str, Any]) -> list[str]:
        warnings = []
        for check in calculation_checks.get("checks", []):
            if check.get("status") in {"warning", "skipped"} or check.get("manual_review_needed"):
                name = check.get("name", "calculation_check")
                message = check.get("message", "requires manual review")
                warnings.append(f"{name}: {message}")
        return warnings

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _envelope(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        status: str = "ok",
        summary: str,
        created_paths: list[str] | None = None,
        modified_paths: list[str] | None = None,
        skipped_paths: list[str] | None = None,
        artifact_resources: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        manual_review_needed: bool = False,
        is_dry_run: bool = True,
        **extra: Any,
    ) -> dict[str, Any]:
        operation_id = self._operation_id(tool_name, arguments)
        result = {
            "status": status,
            "operation_id": operation_id,
            "is_dry_run": is_dry_run,
            "summary": summary,
            "created_paths": created_paths or [],
            "modified_paths": modified_paths or [],
            "skipped_paths": skipped_paths or [],
            "artifact_resources": artifact_resources or [],
            "warnings": [self._sanitize_diagnostic_text(warning, arguments) for warning in (warnings or [])],
            "errors": [self._sanitize_diagnostic_text(error, arguments) for error in (errors or [])],
            "manual_review_needed": manual_review_needed,
        }
        result.update(extra)
        return result

    @staticmethod
    def _operation_id(tool_name: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps(
            {"tool": tool_name, "arguments": arguments},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
        return f"{tool_name}:{digest}"

    def _scan_root(self, arguments: dict[str, Any]) -> Path:
        root = arguments.get("root") or self.research_root
        return Path(root).expanduser().resolve()

    @staticmethod
    def _max_depth(value: Any) -> int:
        try:
            depth = int(value)
        except (TypeError, ValueError):
            depth = 4
        return min(12, max(1, depth))

    @staticmethod
    def _batch_max_projects(value: Any) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 20
        return min(MCP_BATCH_MAX_PROJECTS, max(1, count))

    @staticmethod
    def _discover_batch_projects(
        root: Path,
        *,
        max_depth: int,
        timeout_seconds: float,
    ) -> tuple[list[Any], bool, list[str]]:
        result_queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
        process = multiprocessing.Process(
            target=_batch_discovery_worker,
            args=(str(root), max_depth, result_queue),
            name="graphhub-mcp-batch-discovery",
        )
        process.start()
        process.join(max(0.0, timeout_seconds))
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(5)
            return [], True, [f"Batch discovery timed out after {timeout_seconds:.1f} seconds."]
        if process.exitcode not in (0, None):
            return [], True, [f"Batch discovery worker exited with code {process.exitcode}."]
        try:
            result = result_queue.get(timeout=MCP_RENDER_RESULT_QUEUE_TIMEOUT_SECONDS)
        except queue.Empty:
            return [], True, ["Batch discovery worker exited without returning a result."]
        if result.get("status") != "ok":
            return [], True, [str(result.get("error") or "Batch discovery failed.")]
        projects = result.get("projects")
        return (projects if isinstance(projects, list) else []), False, []

    def _read_version(self) -> str:
        pyproject = self.hub_path / "pyproject.toml"
        try:
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            return "unknown"
        return "unknown"

    def _serialize_project(self, project: Any) -> dict[str, Any]:
        config_data = self._load_project_config(
            Path(project.config_path).parent,
            config_path=Path(project.config_path),
            allow_invalid=True,
        )
        config = config_data["config"] if isinstance(config_data["config"], dict) else {}
        figures = self._list_section(config, "figures")
        diagrams = self._list_section(config, "diagrams")
        return {
            "project_id": project.project_id,
            "project_root": project.path,
            "config_path": project.config,
            "status": self._project_status(project),
            "errors": list(project.errors),
            "declared_figures": len(figures),
            "declared_diagrams": len(diagrams),
            "target_format": project.target_format,
        }

    @staticmethod
    def _batch_skip_reason(
        project: Any,
        *,
        include_invalid: bool,
        include_legacy: bool,
        include_worktrees: bool,
        include_ephemeral: bool,
        previously_checked: set[str],
    ) -> str:
        if project.project_id in previously_checked:
            return "already_checked"
        if project.classification == "ephemeral":
            if project.path.startswith(".worktrees/"):
                return "" if include_worktrees else "ephemeral_project"
            return "" if include_ephemeral else "ephemeral_project"
        if project.classification == "legacy" and not include_legacy:
            return "legacy_project"
        if not project.valid and not include_invalid:
            return "invalid_config"
        return ""

    def _batch_checked_project(self, root: Path, project: Any) -> dict[str, Any]:
        project_path = (root / project.path).resolve()
        validation = self.validate_project({"project_path": str(project_path)})
        errors = []
        for key in ("config_errors", "data_contract_errors", "style_errors"):
            value = validation.get(key)
            if isinstance(value, list):
                errors.extend(str(item) for item in value)
        return {
            "project_id": project.project_id,
            "project_root": project.path,
            "classification": project.classification,
            "target_format": project.target_format,
            "valid": bool(validation.get("valid")),
            "status": validation.get("status", "error"),
            "errors": errors,
        }

    @staticmethod
    def _batch_skipped_project(project: Any, reason: str) -> dict[str, Any]:
        return {
            "project_id": project.project_id,
            "project_root": project.path,
            "classification": project.classification,
            "target_format": project.target_format,
            "valid": bool(project.valid),
            "reason": reason,
            "errors": list(project.errors),
        }

    @staticmethod
    def _project_status(project: Any) -> str:
        if not project.valid:
            return "invalid"
        if project.classification in {"legacy", "ephemeral"}:
            return project.classification
        return "valid"

    def _resolve_project_path(self, arguments: dict[str, Any]) -> Path:
        project_path = arguments.get("project_path")
        if project_path:
            return Path(project_path).expanduser().resolve()

        project_id = arguments.get("project_id")
        if not project_id:
            raise ValueError("project_id or project_path is required.")

        root = self._scan_root(arguments)
        service = ProjectDiscoveryService(
            root,
            include_worktrees=bool(arguments.get("include_worktrees", False)),
            include_ephemeral=bool(arguments.get("include_ephemeral", False)),
        )
        for project in service.discover(max_depth=self._max_depth(arguments.get("max_depth", 4))):
            if project.project_id == project_id:
                return (root / project.path).resolve()
        raise ValueError(f"Project id not found: {project_id}")

    @staticmethod
    def _load_project_config(
        project_path: Path,
        *,
        config_path: Path | None = None,
        allow_invalid: bool = False,
    ) -> dict[str, Any]:
        discovered_config_path = find_config_path(str(project_path))
        config_path = config_path or (Path(discovered_config_path) if discovered_config_path else None)
        if config_path is None:
            return {
                "config": None,
                "config_path": None,
                "config_relpath": "",
                "errors": [f"project_config.yaml not found in {project_path}"],
            }
        try:
            raw_text = config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            return {
                "config": None,
                "config_path": str(config_path),
                "config_relpath": "",
                "errors": [f"Invalid YAML: {exc}"],
            }
        except OSError as exc:
            return {
                "config": None,
                "config_path": str(config_path),
                "config_relpath": "",
                "errors": [f"Failed to read config: {exc}"],
            }

        errors = validate_config(config)
        if errors and not allow_invalid:
            return {
                "config": config,
                "config_path": str(config_path),
                "config_relpath": os.path.relpath(config_path, project_path),
                "errors": errors,
            }
        return {
            "config": config,
            "config_path": str(config_path),
            "config_relpath": os.path.relpath(config_path, project_path),
            "errors": errors if allow_invalid else [],
        }

    @staticmethod
    def _list_section(config: Any, section_name: str) -> list[dict[str, Any]]:
        if not isinstance(config, dict):
            return []
        section = config.get(section_name, [])
        if isinstance(section, list):
            return [item for item in section if isinstance(item, dict)]
        return []

    @staticmethod
    def _outputs(items: list[dict[str, Any]]) -> list[str]:
        return [str(item["output"]) for item in items if isinstance(item.get("output"), str) and item["output"].strip()]

    @staticmethod
    def _missing_paths(project_path: Path, paths: list[str]) -> list[str]:
        return [path for path in paths if not (project_path / path).exists()]

    @staticmethod
    def _missing_inputs(project_path: Path, analysis_steps: list[dict[str, Any]]) -> list[str]:
        missing: list[str] = []
        for step in analysis_steps:
            inputs = step.get("inputs") or []
            if not isinstance(inputs, list):
                continue
            for path in inputs:
                if isinstance(path, str) and path.strip() and not (project_path / path).exists():
                    missing.append(path)
        return missing

    @staticmethod
    def _lockfile_status(project_path: Path, config: dict[str, Any], *, strict: bool) -> dict[str, Any]:
        environment = config.get("environment") if isinstance(config.get("environment"), dict) else {}
        python_lock = environment.get("python_lock")
        r_lock = environment.get("r_lock")
        required = [item for item in (python_lock, r_lock) if isinstance(item, str) and item.strip()]
        missing = [item for item in required if not (project_path / item).exists()]
        return {
            "strict": strict,
            "checked": bool(required),
            "missing": missing,
            "valid": not strict or not missing,
        }

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.research_root).as_posix()
        except ValueError:
            return str(path)

    def _runtime_uri(self, path: Path) -> str:
        try:
            rel_path = path.resolve().relative_to(self.runtime_root).as_posix()
        except ValueError:
            return self._display_path(path)
        return f"runtime://{rel_path}"

    def _sanitize_diagnostic_text(self, text: Any, arguments: dict[str, Any]) -> str:
        sanitized = str(text)
        replacements = self._diagnostic_path_replacements(arguments)
        for root_text, label in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
            child_label = label if label.endswith("/") else f"{label}/"
            sanitized = sanitized.replace(f"{root_text}{os.sep}", child_label)
            sanitized = sanitized.replace(root_text, label)
        return sanitized

    def _diagnostic_path_replacements(self, arguments: dict[str, Any]) -> list[tuple[str, str]]:
        replacements = [
            (str(self.runtime_root), "runtime://"),
            (str(self.research_root), "research://"),
            (str(self.hub_path), "hub://"),
        ]
        data_path = arguments.get("data_path")
        if isinstance(data_path, str) and data_path.strip():
            expanded_path = Path(data_path).expanduser()
            replacements.append((str(expanded_path), "input://data_path"))
            replacements.append((str(expanded_path.resolve()), "input://data_path"))

        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for root_text, label in replacements:
            if not root_text:
                continue
            key = (root_text, label)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped

    def _mcp_jobs_root(self) -> Path:
        return self.runtime_root / "mcp_jobs"

    @staticmethod
    def _render_job_id(raw_job_id: Any = None) -> str:
        if raw_job_id is None or not str(raw_job_id).strip():
            return f"job-{uuid.uuid4().hex[:12]}"
        text = str(raw_job_id).strip()
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
        safe = safe.strip("-_")
        if not safe:
            raise ValueError("job_id must contain at least one alphanumeric character.")
        return safe[:80]

    @staticmethod
    def _required_string(arguments: dict[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required.")
        return value.strip()

    @staticmethod
    def _input_file_path(raw_path: Any) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("data_path is required.")
        path = Path(os.path.abspath(os.fspath(Path(raw_path).expanduser())))
        if not path.is_file():
            raise ValueError("data_path is not a file.")
        if path.suffix.lower() != ".csv":
            raise ValueError("data_path must point to a CSV file.")
        file_size = path.stat().st_size
        max_bytes = GraphHubMCPServer._render_csv_max_bytes()
        if file_size > max_bytes:
            limit_mb = max_bytes / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            raise ValueError(f"data_path exceeds MCP CSV size limit: {actual_mb:.1f} MB > {limit_mb:.1f} MB.")
        return path

    @staticmethod
    def _render_csv_max_bytes() -> int:
        raw_value = os.environ.get("GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES")
        if raw_value is None:
            return MCP_RENDER_CSV_MAX_BYTES
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return MCP_RENDER_CSV_MAX_BYTES
        return value if value > 0 else MCP_RENDER_CSV_MAX_BYTES

    @staticmethod
    def _render_style_errors(target_format: str, output_format: str, profile: str) -> list[str]:
        errors = []
        if target_format not in ALLOWED_TARGET_FORMATS:
            errors.append(f"Invalid target_format: {target_format}. Allowed: {sorted(ALLOWED_TARGET_FORMATS)}")
        if output_format not in ALLOWED_OUTPUT_FORMATS:
            errors.append(f"Invalid output_format: {output_format}. Allowed: {sorted(ALLOWED_OUTPUT_FORMATS)}")
        profile_keys = set(list_profiles()) | set(PROFILE_ALIASES)
        if profile.strip().lower() not in profile_keys:
            errors.append(f"Invalid profile: {profile}. Allowed: {sorted(list_profiles())}")
        return errors

    @staticmethod
    def _rendered_figure_artifacts(output_path: Path) -> list[dict[str, str]]:
        artifacts: list[dict[str, str]] = []
        for candidate in sorted(output_path.parent.glob(f"{output_path.stem}.*")):
            if candidate.suffix.lower().lstrip(".") in ALLOWED_OUTPUT_FORMATS:
                artifacts.append({"path": str(candidate), "format": candidate.suffix.lower().lstrip(".")})
        if not artifacts:
            artifacts.append({"path": str(output_path), "format": output_path.suffix.lower().lstrip(".")})
        return artifacts

    @staticmethod
    def _validate_render_data_contract(
        data_path: Path,
        *,
        required_columns: list[str],
        semantic_checks: dict[str, Any],
    ) -> dict[str, Any]:
        calculation_checks: list[dict[str, Any]] = []
        empty_summary = {"checks": [], "quality_passed": True, "manual_review_needed": False}
        try:
            import pandas as pd

            df = _read_data_safe(str(data_path), pd)
        except Exception as exc:
            return {
                "errors": [f"Failed to read render data contract input: {exc}"],
                "calculation_checks": empty_summary,
            }

        stripped_to_actual = {}
        for actual_col in df.columns:
            stripped_col = str(actual_col).strip()
            if stripped_col in stripped_to_actual and stripped_to_actual[stripped_col] != actual_col:
                return {
                    "errors": [
                        "Ambiguous columns after strip normalization: "
                        f"'{stripped_to_actual[stripped_col]}' and '{actual_col}'"
                    ],
                    "calculation_checks": empty_summary,
                }
            stripped_to_actual[stripped_col] = actual_col

        missing = [col for col in required_columns if str(col).strip() not in stripped_to_actual]
        if missing:
            return {"errors": [f"Missing required columns: {missing}"], "calculation_checks": empty_summary}

        semantic_errors, _row_violations = _validate_semantic_constraints(
            df,
            semantic_checks,
            stripped_to_actual,
            calculation_checks=calculation_checks,
            csv_rel_path=str(data_path),
            source_config_path="project_config.yaml",
        )
        return {
            "errors": list(semantic_errors),
            "calculation_checks": {
                "checks": calculation_checks,
                "quality_passed": not any(
                    check.get("status") in {"warning", "failed", "skipped"} for check in calculation_checks
                ),
                "manual_review_needed": any(bool(check.get("manual_review_needed")) for check in calculation_checks),
            },
        }

    @staticmethod
    def _render_project_config(
        *,
        target_format: str,
        profile: str,
        output_format: str,
        x_column: str,
        y_column: str,
        semantic_checks: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "project": {"name": "Graph Hub MCP Render Job"},
            "visual_style": {
                "target_format": target_format,
                "font_scale": 1.0,
                "profile": profile,
            },
            "language_policy": {"analysis_lang": "r", "plot_lang": "python", "allow_nonstandard": False},
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "data/input.csv",
                        "required_columns": [x_column, y_column],
                        "semantic_checks": semantic_checks,
                    }
                ]
            },
            "figures": [
                {
                    "id": "Graph",
                    "script": "bridge_renderer",
                    "inputs": ["data/input.csv"],
                    "output": f"results/figures/graph.{output_format}",
                }
            ],
        }

    @staticmethod
    def _safe_preflight(output_path: Path, target_format: str) -> dict[str, Any]:
        journal = target_format if target_format in {"nature", "science", "acs", "rsc", "elsevier"} else "nature"
        try:
            return validate_figure_preflight(output_path, journal)
        except Exception as exc:
            return {
                "passed": False,
                "checks": [],
                "warnings": [str(exc)],
            }


def run_stdio_server(
    server: GraphHubMCPServer | None = None,
    *,
    input_stream: Any | None = None,
    output_stream: Any | None = None,
) -> int:
    """Run a Content-Length framed JSON-RPC stdio MCP server."""
    active_server = server or GraphHubMCPServer()
    in_stream = input_stream or sys.stdin.buffer
    out_stream = output_stream or sys.stdout.buffer

    while True:
        try:
            request = _read_stdio_message(in_stream)
            if request is None:
                break
            response = _handle_json_rpc(active_server, request)
        except json.JSONDecodeError as exc:
            response = _json_rpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}")
        except Exception as exc:
            response = _json_rpc_error(None, JSONRPC_INTERNAL_ERROR, str(exc))
        if response is not None:
            _write_stdio_message(out_stream, response)
    return 0


def _handle_json_rpc(server: GraphHubMCPServer, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "graph-making-hub", "version": server._read_version()},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list_tool_definitions()}}
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(tool_name, str) or tool_name not in server._handlers:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Tool arguments must be an object.")
        argument_errors = _validate_tool_arguments(tool_name, arguments)
        if argument_errors:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "; ".join(argument_errors))
        return {"jsonrpc": "2.0", "id": request_id, "result": server.call_tool(tool_name, arguments)}
    return _json_rpc_error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")


def _validate_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> list[str]:
    for definition in list_tool_definitions():
        if definition["name"] != tool_name:
            continue
        schema = definition.get("inputSchema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        errors = [
            f"Missing required tool argument(s): {key}"
            for key in required
            if key not in arguments or not isinstance(arguments.get(key), str) or not arguments.get(key).strip()
        ]
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                errors.append(f"Unknown tool argument(s): {', '.join(unknown)}")
        for key, value in arguments.items():
            prop_schema = properties.get(key)
            if isinstance(prop_schema, dict):
                expected_type = prop_schema.get("type")
                if not _matches_json_schema_type(value, expected_type):
                    errors.append(f"Tool argument '{key}' must be {expected_type}.")
        return errors
    return []


def _matches_json_schema_type(value: Any, expected_type: Any) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type is None:
        return True
    return True


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _read_stdio_message(stream: Any) -> dict[str, Any] | None:
    first_line = stream.readline()
    if first_line == b"" or first_line == "":
        return None
    if isinstance(first_line, str):
        first_line = first_line.encode("utf-8")

    if first_line.lstrip().startswith(b"{"):
        return json.loads(first_line.decode("utf-8"))

    headers = _read_headers(stream, first_line)
    content_length = headers.get("content-length")
    if content_length is None:
        raise ValueError("Missing Content-Length header.")
    try:
        expected_size = int(content_length)
    except ValueError as exc:
        raise ValueError(f"Invalid Content-Length header: {content_length}") from exc
    body = stream.read(expected_size)
    if isinstance(body, str):
        body = body.encode("utf-8")
    if len(body) != expected_size:
        raise ValueError(f"Incomplete MCP message body: expected {expected_size} bytes, got {len(body)}.")
    return json.loads(body.decode("utf-8"))


def _read_headers(stream: Any, first_line: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    line = first_line
    while line not in (b"", b"\n", b"\r\n"):
        text = line.decode("ascii", errors="replace").strip()
        if ":" in text:
            key, value = text.split(":", 1)
            headers[key.lower()] = value.strip()
        line = stream.readline()
        if isinstance(line, str):
            line = line.encode("utf-8")
    return headers


def _write_stdio_message(stream: Any, response: dict[str, Any]) -> None:
    body = json.dumps(response, ensure_ascii=False).encode("utf-8")
    payload = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    stream.write(payload)
    if hasattr(stream, "flush"):
        stream.flush()
