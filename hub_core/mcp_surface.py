from __future__ import annotations

import fnmatch
import hashlib
import json
import multiprocessing
import os
import queue
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

import yaml

from themes.style_packs import list_style_packs
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
    "graphhub.render_project_figure",
    "graphhub.collect_artifacts",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
WRITE_TOOL_NAMES = (
    "graphhub.render_csv_graph",
    "graphhub.render_project_figure",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)
SUPPORTED_RENDER_PLOT_TYPES = {"bar", "line", "scatter", "xy", "heatmap"}
MCP_RENDER_CSV_MAX_BYTES = 64 * 1024 * 1024
MCP_MAX_MESSAGE_BYTES = 16 * 1024 * 1024
MCP_RENDER_TIMEOUT_SECONDS = 120.0
MCP_RENDER_RESULT_QUEUE_TIMEOUT_SECONDS = 5.0
MCP_BATCH_MAX_PROJECTS = 50
MCP_BATCH_TIMEOUT_SECONDS = 30.0

JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_PARSE_ERROR = -32700
JSONRPC_RESOURCE_NOT_FOUND = -32002
_STRICT_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

GEOMETRY_DIAGNOSTICS_SCHEMA_VERSION = "geometry_diagnostics/1"
LAYOUT_REPORT_SCHEMA_VERSION = "layout_report/1"
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
)
_GEOMETRY_WARNING_ELIGIBLE = frozenset(
    {
        "tick_label_overlaps",
        "tick_label_crowding",
        "artists_outside_axes",
        "artists_outside_figure",
        "axis_label_title_overlap",
        "colorbar_overlap",
        "point_annotation_overlaps",
        "artist_overlaps",
        "legend_internal_overlaps",
        "marker_marker_overlaps",
        "text_axis_edge_proximity",
        "legend_marker_consistency",
        "label_offset_consistency",
        "font_size_token_drift",
    }
)
SCRIPT_OUTPUT_TAIL_LINES = 40


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


def _geometry_stub(reason: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    stub: dict[str, Any] = {
        "schema_version": GEOMETRY_DIAGNOSTICS_SCHEMA_VERSION,
        "passed": None,
        "checks": [],
        "warnings": [reason],
    }
    if data is not None:
        stub["data"] = data
    return stub


def _read_geometry_sidecar(job_root: Path) -> dict[str, Any]:
    sidecar = job_root / "geometry_diagnostics.json"
    try:
        text = sidecar.read_text(encoding="utf-8")
    except OSError:
        return _geometry_stub(
            "geometry_diagnostics_unavailable: no sidecar emitted",
            data={"reason": "no_sidecar"},
        )
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return _geometry_stub(
            "geometry_diagnostics_unavailable: unreadable sidecar",
            data={"reason": "no_sidecar"},
        )
    if not isinstance(loaded, dict):
        return _geometry_stub(
            "geometry_diagnostics_unavailable: malformed sidecar",
            data={"reason": "no_sidecar"},
        )
    return loaded


def _geometry_warnings(diagnostics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    raw_warnings = diagnostics.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(warning) for warning in raw_warnings)
    raw_checks = diagnostics.get("checks")
    if isinstance(raw_checks, list):
        for check in raw_checks:
            if (
                isinstance(check, dict)
                and check.get("name") in _GEOMETRY_WARNING_ELIGIBLE
                and check.get("passed") is False
            ):
                detail = check.get("detail")
                if detail:
                    warnings.append(str(detail))
    return warnings


def _layout_report_from_geometry(
    diagnostics: dict[str, Any],
    *,
    failure_stage: str = "",
    script_output: list[str] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": LAYOUT_REPORT_SCHEMA_VERSION,
        "passed": diagnostics.get("passed") if isinstance(diagnostics, dict) else None,
        "overlaps": [],
        "clipped": [],
        "font_roles": {},
        "placement_consistency": [],
        "density": {},
        "render_errors": [],
        "warnings": [],
    }
    if failure_stage:
        report["passed"] = False
        tail = [str(line) for line in (script_output or [])][-SCRIPT_OUTPUT_TAIL_LINES:]
        report["render_errors"].append({"stage": failure_stage, "script_output_tail": tail})

    raw_warnings = diagnostics.get("warnings") if isinstance(diagnostics, dict) else None
    if isinstance(raw_warnings, list):
        report["warnings"].extend(str(warning) for warning in raw_warnings)

    checks = diagnostics.get("checks") if isinstance(diagnostics, dict) else None
    if not isinstance(checks, list):
        return report

    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "")
        data = check.get("data") if isinstance(check.get("data"), dict) else {}
        if name in {"artist_overlaps", "legend_internal_overlaps", "marker_marker_overlaps"}:
            report["overlaps"].extend(_layout_overlap_items(name, data))
        elif name == "text_axis_edge_proximity":
            report["clipped"].extend(_layout_clipped_items(data))
        elif name == "label_offset_consistency":
            report["placement_consistency"].extend(_layout_placement_items(data))
        elif name == "font_size_token_drift":
            report["font_roles"] = _layout_font_roles(data, check)
        elif name == "legend_marker_consistency" and check.get("passed") is False:
            detail = check.get("detail")
            if detail:
                report["warnings"].append(str(detail))
        elif (
            name in {"point_annotation_overlaps", "artists_outside_axes", "artists_outside_figure"}
            and check.get("passed") is False
        ):
            detail = check.get("detail")
            if detail:
                report["warnings"].append(str(detail))

    density = _layout_density(checks)
    if density:
        report["density"] = density
    return report


def _layout_overlap_items(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_overlaps = data.get("overlaps")
    if not isinstance(raw_overlaps, list):
        return []
    items: list[dict[str, Any]] = []
    for overlap in raw_overlaps:
        if not isinstance(overlap, dict):
            continue
        a = str(overlap.get("a", ""))
        b = str(overlap.get("b", ""))
        kind = str(overlap.get("kind") or _layout_overlap_kind(name, a, b))
        items.append(
            {
                "axes": int(overlap.get("axes", data.get("axis_index", 0))),
                "a": a,
                "b": b,
                "kind": kind,
                "iou": float(overlap.get("iou", 0.0)),
                "severity": str(overlap.get("severity") or _layout_overlap_severity(float(overlap.get("iou", 0.0)))),
            }
        )
    return items


def _layout_overlap_kind(name: str, a: str, b: str) -> str:
    if name == "legend_internal_overlaps":
        return "legend-internal"
    if name == "marker_marker_overlaps":
        return "marker-marker"
    labels = (a, b)
    if any(label.startswith("marker:") for label in labels) and any(
        label.startswith(("text:", "annotation:", "title:")) for label in labels
    ):
        return "text-marker"
    if all(label.startswith(("text:", "annotation:", "title:")) for label in labels):
        return "text-text"
    if any(label == "legend" or label.startswith("legend") for label in labels):
        return "legend-data"
    return "artist-artist"


def _layout_overlap_severity(iou: float) -> str:
    if iou >= 0.50:
        return "high"
    if iou >= 0.20:
        return "medium"
    if iou > 0:
        return "low"
    return "none"


def _layout_clipped_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list):
        return []
    items: list[dict[str, Any]] = []
    for finding in raw_findings:
        if not isinstance(finding, dict):
            continue
        edges = finding.get("edges") if isinstance(finding.get("edges"), list) else []
        items.append(
            {
                "axes": int(finding.get("axes", data.get("axis_index", 0))),
                "artist": str(finding.get("artist", "")),
                "edge": str(edges[0]) if edges else "",
                "edges": [str(edge) for edge in edges],
                "clipped": bool(finding.get("clipped")),
                "min_distance_px": float(finding.get("min_distance_px", 0.0)),
            }
        )
    return items


def _layout_placement_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = data.get("inconsistencies")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        placements = item.get("placements") if isinstance(item.get("placements"), list) else []
        panels = {
            str(placement.get("axis_index")): str(placement.get("direction"))
            for placement in placements
            if isinstance(placement, dict)
        }
        items.append(
            {
                "entity": str(item.get("label", "")),
                "directions": [str(direction) for direction in item.get("directions", [])],
                "panels": panels,
                "placements": placements,
            }
        )
    return items


def _layout_font_roles(data: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": bool(check.get("passed")),
        "token_sizes": data.get("token_sizes", []),
        "offenders": data.get("offenders", []),
        "role_size_counts": data.get("role_size_counts", {}),
        "warn": str(check.get("detail", "")) if check.get("passed") is False else "",
    }


def _layout_density(checks: list[Any]) -> dict[str, Any]:
    text_counts: dict[int, int] = {}
    repeated_labels = 0
    for check in checks:
        if not isinstance(check, dict) or check.get("name") != "label_offset_consistency":
            continue
        data = check.get("data") if isinstance(check.get("data"), dict) else {}
        raw_items = data.get("inconsistencies")
        if isinstance(raw_items, list):
            repeated_labels = len(raw_items)
    if repeated_labels:
        return {
            "repeated_label_inconsistency_count": int(repeated_labels),
            "warn": "repeated labels across sibling axes may be reducible with label-once/dedup placement",
        }
    return text_counts


class ProjectRenderExportError(RuntimeError):
    """Project render setup/export failed before a plotting script completed successfully."""

    def __init__(self, message: str, *, script_output: list[str] | None = None) -> None:
        super().__init__(message)
        self.script_output = script_output or []


class ProjectRenderScriptError(RuntimeError):
    """The selected project plotting script ran and exited unsuccessfully."""

    def __init__(self, message: str, *, returncode: int | None, script_output: list[str] | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.script_output = script_output or []


def _render_bridge_figure_worker(spec_payload: dict[str, Any], result_queue: multiprocessing.Queue) -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        with redirect_stdout(sys.stderr):
            from plotting.bridge_renderer import BridgeFigureSpec, render_bridge_figure

            output_path = render_bridge_figure(BridgeFigureSpec(**spec_payload))
        result_queue.put({"status": "ok", "output_path": output_path})
    except Exception as exc:
        result_queue.put({"status": "error", "error": str(exc), "traceback": traceback.format_exc().splitlines()})


def _batch_discovery_worker(root: str, max_depth: int, result_queue: multiprocessing.Queue) -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        with redirect_stdout(sys.stderr):
            projects = ProjectDiscoveryService(
                root,
                include_worktrees=True,
                include_ephemeral=True,
            ).discover(max_depth=max_depth)
        result_queue.put({"status": "ok", "projects": projects})
    except Exception as exc:
        result_queue.put({"status": "error", "error": str(exc), "traceback": traceback.format_exc().splitlines()})


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
                    "z_column": {"type": "string"},
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
            _object_schema(
                {
                    "project_id": {"type": "string"},
                    "project_path": {"type": "string"},
                    "root": root_arg,
                    "figure_id": {"type": "string"},
                    "figure_output": {"type": "string"},
                    "target_format": {"type": "string"},
                    "profile": {"type": "string"},
                    "output_format": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": False},
                    "overwrite": {"type": "boolean", "default": False},
                    "job_id": {"type": "string"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 4},
                    "baseline_path": {"type": "string"},
                }
            ),
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
            _object_schema({"job_id": {"type": "string"}, "baseline_path": {"type": "string"}}, required=["job_id"]),
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
    return [
        {
            "name": "make_publication_graph_from_csv",
            "description": "Workflow for rendering a publication-style graph from structured CSV data.",
            "arguments": [
                {"name": "data_path", "description": "CSV input path.", "required": True},
                {"name": "x_column", "description": "CSV x-axis column.", "required": True},
                {"name": "y_column", "description": "CSV y-axis column.", "required": True},
                {"name": "target_format", "description": "Graph Hub target format.", "required": False},
                {"name": "plot_type", "description": "bar, line, scatter, xy, or heatmap.", "required": False},
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


class GraphHubMCPServer:
    """Dependency-free MCP surface over Graph Hub core contracts."""

    def __init__(
        self,
        *,
        hub_path: str | os.PathLike | None = None,
        research_root: str | os.PathLike | None = None,
        runtime_root: str | os.PathLike | None = None,
        write_tools_enabled: bool | None = None,
    ) -> None:
        self.hub_path = Path(hub_path or get_hub_path()).expanduser().resolve()
        self.research_root = Path(research_root or get_research_root()).expanduser().resolve()
        self._runtime_root_explicit = runtime_root is not None
        self.runtime_root = self._resolve_runtime_root(runtime_root)
        self.allowed_data_roots = self._allowed_data_roots()
        self.write_tools_enabled = self._resolve_write_tools_enabled(write_tools_enabled)
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "graphhub.health": self.health,
            "graphhub.list_styles": self.list_styles,
            "graphhub.list_projects": self.list_projects,
            "graphhub.inspect_project": self.inspect_project,
            "graphhub.validate_project": self.validate_project,
            "graphhub.render_csv_graph": self.render_csv_graph,
            "graphhub.render_project_figure": self.render_project_figure,
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

    @staticmethod
    def _resolve_write_tools_enabled(write_tools_enabled: bool | None) -> bool:
        if write_tools_enabled is not None:
            return bool(write_tools_enabled)
        raw = os.environ.get("GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED")
        if raw is None:
            # Fail closed: write/exec tools require explicit opt-in via constructor arg or env var.
            return False
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _allowed_data_roots(self) -> tuple[Path, ...]:
        roots = [self.research_root, self.runtime_root]
        raw_extra = os.environ.get("GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS", "")
        for item in raw_extra.split(os.pathsep):
            if item.strip():
                roots.append(Path(item).expanduser().resolve())
        deduped: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root)
            if key not in seen:
                seen.add(key)
                deduped.append(root)
        return tuple(deduped)

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _resolve_under_root(self, raw_path: Any, *, field_name: str, root: Path | None = None) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{field_name} is required.")
        raw = Path(raw_path).expanduser()
        trusted_root_raw = Path(root or self.research_root).expanduser()
        if not trusted_root_raw.is_absolute():
            trusted_root_raw = trusted_root_raw.resolve()
        raw_absolute = raw if raw.is_absolute() else trusted_root_raw / raw
        trusted_root = trusted_root_raw.resolve()
        path = raw_absolute.resolve()
        if not self._is_relative_to(path, trusted_root):
            raise ValueError(f"{field_name} must stay under {trusted_root}.")
        current = Path(raw_absolute.anchor)
        for part in raw_absolute.parts[1:]:
            current = current / part
            if current.is_symlink():
                target = current.resolve()
                if target == trusted_root or self._is_relative_to(target, trusted_root):
                    raise ValueError(f"{field_name} must not include symlinked path components.")
                if not self._is_relative_to(trusted_root, target):
                    raise ValueError(f"{field_name} must not include symlinked path components.")
        return path

    def _resolve_allowed_data_path(self, raw_path: Any, *, field_name: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{field_name} is required.")
        raw = Path(raw_path).expanduser()
        raw_absolute = raw if raw.is_absolute() else self.research_root / raw
        path = raw_absolute.resolve()
        if not any(self._is_relative_to(path, root) for root in self.allowed_data_roots):
            allowed = ", ".join(str(root) for root in self.allowed_data_roots)
            raise ValueError(f"{field_name} must stay under an allowed data root: {allowed}.")
        current = Path(raw_absolute.anchor)
        for part in raw_absolute.parts[1:]:
            current = current / part
            if current.is_symlink():
                target = current.resolve()
                parent = current.parent.resolve()
                for root in self.allowed_data_roots:
                    if self._is_relative_to(parent, root) and self._is_relative_to(target, root):
                        raise ValueError(f"{field_name} must not include symlinked path components.")
        return path

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown Graph Hub MCP tool: {name}")
        if name in WRITE_TOOL_NAMES and not self.write_tools_enabled:
            structured = self._envelope(
                name,
                arguments,
                status="error",
                summary=f"{name} is disabled by the Graph Hub MCP write-tool guard.",
                errors=["Write tools are disabled for this Graph Hub MCP server."],
                manual_review_needed=True,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, sort_keys=True)}],
                "structuredContent": structured,
                "isError": True,
            }

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
            write_tools_enabled=self.write_tools_enabled,
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
            style_packs=list_style_packs(),
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

        render_environment_warnings = self._project_context_render_warnings(project_path)
        warnings = [] if valid else ["Project validation reported warnings or errors."]
        warnings.extend(render_environment_warnings)
        status = "warning" if warnings else "ok"
        if valid and render_environment_warnings:
            summary = "Project config is valid with render environment warnings."
        elif valid:
            summary = "Project config is valid."
        else:
            summary = "Project config needs changes before rendering."

        return self._envelope(
            "graphhub.validate_project",
            arguments,
            status=status,
            summary=summary,
            warnings=warnings,
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
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_jobs_root() / job_id
        try:
            data_path = self._input_file_path(arguments.get("data_path"))
            x_column = self._required_string(arguments, "x_column")
            y_column = self._required_string(arguments, "y_column")
            z_column = str(arguments.get("z_column") or "").strip()
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
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
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
                    f"Invalid plot_type '{plot_type}'. Supported: {', '.join(sorted(SUPPORTED_RENDER_PLOT_TYPES))}."
                ],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported plot_type.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
            )
        if plot_type == "heatmap" and not z_column:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid plot settings.",
                errors=["plot_type 'heatmap' requires a z_column."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide z_column for heatmap plot_type.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
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
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
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
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
            )
        config = self._render_project_config(
            target_format=target_format,
            profile=profile,
            output_format=output_format,
            x_column=x_column,
            y_column=y_column,
            z_column=z_column,
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
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
            )
        with redirect_stdout(sys.stderr):
            ensure_local_files([str(data_path)])
        contract_result = self._validate_render_data_contract(
            data_path,
            required_columns=[
                x_column,
                y_column,
                *([z_column] if z_column else []),
                *[str(key) for key in semantic_checks],
            ],
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
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
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
                geometry_diagnostics=_geometry_stub("dry_run"),
                layout_report=_layout_report_from_geometry(_geometry_stub("dry_run")),
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
                geometry_diagnostics=_geometry_stub("no figure"),
                layout_report=_layout_report_from_geometry(_geometry_stub("no figure")),
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

            with self._geometry_diagnostics_env(job_root):
                self._run_render_bridge_figure(
                    {
                        "csv_path": str(job_data_path),
                        "output_path": str(output_path),
                        "plot_type": plot_type,
                        "x_column": x_column,
                        "y_column": y_column,
                        "z_column": z_column,
                        "title": str(arguments.get("title") or "Graph Hub MCP render"),
                        "x_axis_label": str(arguments.get("x_axis_label") or x_column),
                        "y_axis_label": str(arguments.get("y_axis_label") or y_column),
                        "target_format": target_format,
                        "profile_name": profile,
                    }
                )
            geometry_diagnostics = _read_geometry_sidecar(job_root)
            geometry_warnings = _geometry_warnings(geometry_diagnostics)
            layout_report = _layout_report_from_geometry(geometry_diagnostics)
            figures = self._rendered_figure_artifacts(output_path)
            created_paths.extend(str(figure["path"]) for figure in figures)
            preflight = self._visual_preflight_with_geometry_overlaps(output_path, target_format, geometry_diagnostics)
            preflight_warnings = self._preflight_warnings(preflight)
            baseline_comparison = self._baseline_comparison(output_path, arguments.get("baseline_path"))
            baseline_warnings = self._baseline_warnings(baseline_comparison)
            calculation_warnings = self._calculation_warnings(calculation_checks)
            provenance = self._mcp_render_provenance(
                job_id=job_id,
                source_data_path=data_path,
                copied_data_path=job_data_path,
                config_path=config_path,
                output_path=output_path,
                target_format=target_format,
                profile=profile,
                output_format=output_format,
            )
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or bool(calculation_checks.get("manual_review_needed"))
                or geometry_diagnostics.get("passed") is False
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
                "geometry_diagnostics": geometry_diagnostics,
                "layout_report": layout_report,
                "failure_stage": "",
                "resolution_hint": "",
                "artifact_status": artifact_status,
                "baseline_comparison": baseline_comparison,
                "manual_review_needed": manual_review_needed,
                "calculation_checks": calculation_checks,
                "provenance": provenance,
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
            status_payload["provenance"] = provenance
            status_payload["layout_report"] = layout_report
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
                geometry_diagnostics=_geometry_stub("render_execution_failed"),
                layout_report=_layout_report_from_geometry(
                    _geometry_stub("render_execution_failed"),
                    failure_stage=failure_stage,
                ),
            )

        return self._envelope(
            "graphhub.render_csv_graph",
            arguments,
            status=status,
            summary="Rendered CSV graph." if status == "ok" else "Rendered CSV graph with preflight warnings.",
            created_paths=created_paths,
            artifact_resources=[f"file://{figure['path']}" for figure in manifest["figures"]],
            warnings=preflight_warnings + baseline_warnings + calculation_warnings + geometry_warnings,
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
            geometry_diagnostics=geometry_diagnostics,
            layout_report=layout_report,
            failure_stage="",
            resolution_hint="",
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
            calculation_checks=calculation_checks,
        )

    def render_project_figure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_project_jobs_root() / job_id
        try:
            project_path = self._resolve_project_render_path(arguments)
            loaded = self._load_project_config(project_path, allow_invalid=True)
            config = loaded["config"] if isinstance(loaded["config"], dict) else {}
            config_errors = validate_config(config) if isinstance(config, dict) else list(loaded["errors"])
            if config_errors:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project config is not valid for rendering.",
                    errors=config_errors,
                    failure_stage="CONFIG",
                    resolution_hint="Fix project_config.yaml before rendering this project figure.",
                )
            figures = self._project_figure_entries(config)
            selected, selection_errors = self._select_project_figure(
                figures,
                figure_id=arguments.get("figure_id"),
                figure_output=arguments.get("figure_output"),
            )
            if selection_errors or selected is None:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project figure selection is ambiguous or invalid.",
                    errors=selection_errors,
                    failure_stage="CONTRACT",
                    resolution_hint=f"Select one of: {self._figure_selector_summary(figures)}",
                )
            output_relpath = self._project_relative_path(selected.get("output"), "figures[].output").as_posix()
            style_summary = self._selected_figure_style_summary(config, selected, arguments)
            style_errors = self._render_style_errors(
                style_summary["target_format"],
                style_summary["output_format"],
                style_summary["profile"],
            )
            if style_errors:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project figure style settings are invalid.",
                    errors=style_errors,
                    failure_stage="CONFIG",
                    resolution_hint="Use a supported target_format, output_format, and profile.",
                    selected_figure=self._public_selected_figure(selected),
                )
        except ValueError as exc:
            return self._project_render_error(
                arguments,
                dry_run=dry_run,
                job_id=job_id,
                job_root=job_root,
                summary="Project render request is invalid.",
                errors=[str(exc)],
                failure_stage="CONTRACT",
                resolution_hint="Provide a valid project_id or project_path and figure selector.",
            )

        config_relpath = str(loaded["config_relpath"] or "project_config.yaml")
        source_project_path = self._public_project_path(project_path)
        selected_public = self._public_selected_figure(selected)
        snapshot_project_path = job_root / "project"
        output_path = snapshot_project_path / output_relpath
        config_path = snapshot_project_path / config_relpath
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_project_render"
        project_id = self._stable_project_id_for_path(project_path)

        if dry_run:
            return self._envelope(
                "graphhub.render_project_figure",
                arguments,
                summary="Project figure render validated in dry-run mode; no files were created.",
                is_dry_run=True,
                job_id=job_id,
                project_id=project_id,
                source_project_path=source_project_path,
                job_root=str(job_root),
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
                manifest_path=str(manifest_path),
                status_path=str(status_path),
                latest_dir=str(latest_dir),
                latest_alias=str(latest_dir),
                style_summary=style_summary,
                visual_preflight_status={"passed": None, "checks": [], "warnings": ["dry_run"]},
                geometry_diagnostics=_geometry_stub("dry_run"),
                layout_report=_layout_report_from_geometry(_geometry_stub("dry_run")),
                artifact_status="validated",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                provenance={},
                failure_stage="",
                resolution_hint="",
            )

        job_root = self._mcp_project_jobs_root() / job_id
        snapshot_project_path = job_root / "project"
        output_path = snapshot_project_path / output_relpath
        config_path = snapshot_project_path / config_relpath
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_project_render"

        if job_root.exists() and not overwrite:
            return self._project_render_error(
                arguments,
                dry_run=False,
                job_id=job_id,
                job_root=job_root,
                summary="Project render job already exists.",
                errors=[
                    f"Project render job already exists: {self._runtime_uri(job_root)}. "
                    "Set overwrite=true to replace it."
                ],
                failure_stage="EXPORT",
                resolution_hint="Set overwrite=true to replace the existing MCP project render job.",
                project_id=project_id,
                source_project_path=source_project_path,
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
            )
        if job_root.exists() and overwrite:
            shutil.rmtree(job_root)

        created_paths: list[str] = []
        try:
            created_paths = self._copy_project_snapshot(
                source_project=project_path,
                snapshot_project=snapshot_project_path,
                config_relpath=config_relpath,
                selected_figure=selected,
            )
            self._run_project_figure_script(
                snapshot_project_path=snapshot_project_path,
                selected_figure=selected,
                style_summary=style_summary,
            )
            geometry_diagnostics = _read_geometry_sidecar(job_root)
            geometry_warnings = _geometry_warnings(geometry_diagnostics)
            layout_report = _layout_report_from_geometry(geometry_diagnostics)
            if not output_path.is_file():
                raise ProjectRenderExportError(
                    f"Selected figure output was not created: {output_relpath}",
                    script_output=self._read_project_script_output(job_root),
                )
            figures_out = self._rendered_figure_artifacts(output_path)
            figure_metadata = self._project_figure_metadata(
                output_path,
                selected,
                project_path=snapshot_project_path,
                figures=figures,
            )
            figure_format_warnings = [
                *list(figure_metadata.get("canonical_check", {}).get("warnings", [])),
                *list(figure_metadata.get("family_check", {}).get("warnings", [])),
            ]
            for figure in figures_out:
                path_text = str(figure["path"])
                if path_text not in created_paths:
                    created_paths.append(path_text)
            preflight = self._visual_preflight_with_geometry_overlaps(
                output_path,
                style_summary["target_format"],
                geometry_diagnostics,
            )
            preflight_warnings = self._preflight_warnings(preflight)
            baseline_comparison = self._baseline_comparison(output_path, arguments.get("baseline_path"))
            baseline_warnings = self._baseline_warnings(baseline_comparison)
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or geometry_diagnostics.get("passed") is False
                or bool(figure_format_warnings)
            )
            status = "warning" if manual_review_needed else "ok"
            artifact_status = self._artifact_status(preflight, baseline_comparison)
            provenance = self._mcp_project_render_provenance(
                job_id=job_id,
                project_path=project_path,
                snapshot_project_path=snapshot_project_path,
                config_path=config_path,
                output_path=output_path,
                selected_figure=selected,
                style_summary=style_summary,
            )
            created_paths.extend([str(manifest_path), str(status_path)])
            manifest = {
                "job_id": job_id,
                "project_id": project_id,
                "source_project_path": source_project_path,
                "job_root": str(job_root),
                "snapshot_project_path": str(snapshot_project_path),
                "config_path": str(config_path),
                "status_path": str(status_path),
                "latest_dir": str(latest_dir),
                "latest_alias": str(latest_dir),
                "selected_figure": selected_public,
                "figures": figures_out,
                "diagrams": [],
                "assemblies": [],
                "logs": [],
                "created_paths": created_paths,
                "modified_paths": [],
                "skipped_paths": [],
                "style_summary": style_summary,
                "visual_preflight_status": preflight,
                "geometry_diagnostics": geometry_diagnostics,
                "layout_report": layout_report,
                "figure_metadata": figure_metadata,
                "failure_stage": "",
                "resolution_hint": "",
                "artifact_status": artifact_status,
                "baseline_comparison": baseline_comparison,
                "manual_review_needed": manual_review_needed,
                "provenance": provenance,
            }
            status_payload = self._render_status_payload(
                job_id=job_id,
                status=status,
                summary=(
                    "Rendered project figure." if status == "ok" else "Rendered project figure with preflight warnings."
                ),
                manifest_path=manifest_path,
                output_path=output_path,
                artifact_status=artifact_status,
                manual_review_needed=manual_review_needed,
                failure_stage="",
                resolution_hint="",
            )
            status_payload["provenance"] = provenance
            status_payload["layout_report"] = layout_report
            status_payload["figure_metadata"] = figure_metadata
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
            if isinstance(exc, TimeoutError):
                failure_stage = "TIMEOUT"
            elif isinstance(exc, ProjectRenderExportError):
                failure_stage = "EXPORT"
            elif isinstance(exc, ProjectRenderScriptError):
                failure_stage = "PLOT"
            else:
                failure_stage = "PLOT"
            resolution_hint = (
                "Increase the render timeout or simplify the figure."
                if failure_stage == "TIMEOUT"
                else (
                    "Fix the selected figure script, declared inputs, and output path."
                    if failure_stage == "EXPORT"
                    else "Inspect the selected figure script error."
                )
            )
            baseline_comparison = self._baseline_comparison(None, arguments.get("baseline_path"))
            script_output = self._project_failure_script_output(exc, job_root)
            failure_geometry = (
                _read_geometry_sidecar(job_root) if job_root.exists() else _geometry_stub("render_execution_failed")
            )
            failure_layout_report = _layout_report_from_geometry(
                failure_geometry,
                failure_stage=failure_stage,
                script_output=script_output,
            )
            if job_root.exists():
                created_paths = self._write_project_render_failure_artifacts(
                    job_id=job_id,
                    job_root=job_root,
                    snapshot_project_path=snapshot_project_path,
                    selected_figure=selected_public,
                    manifest_path=manifest_path,
                    status_path=status_path,
                    latest_dir=latest_dir,
                    created_paths=created_paths,
                    failure_stage=failure_stage,
                    resolution_hint=resolution_hint,
                    baseline_comparison=baseline_comparison,
                    script_output=script_output,
                    layout_report=failure_layout_report,
                )
            return self._envelope(
                "graphhub.render_project_figure",
                arguments,
                status="error",
                summary="Project figure render execution failed.",
                created_paths=created_paths,
                errors=self._exception_error_lines(exc),
                script_output=script_output,
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                project_id=project_id,
                source_project_path=source_project_path,
                job_root=str(job_root),
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
                manifest_path=str(manifest_path) if job_root.exists() else "",
                status_path=str(status_path) if job_root.exists() else "",
                latest_dir=str(latest_dir) if job_root.exists() else "",
                latest_alias=str(latest_dir) if job_root.exists() else "",
                style_summary=style_summary,
                visual_preflight_status={"passed": False, "checks": [], "warnings": ["render_execution_failed"]},
                geometry_diagnostics=failure_geometry,
                layout_report=failure_layout_report,
                artifact_status="failed",
                baseline_comparison=baseline_comparison,
                provenance={},
                failure_stage=failure_stage,
                resolution_hint=resolution_hint,
            )

        return self._envelope(
            "graphhub.render_project_figure",
            arguments,
            status=status,
            summary=(
                "Rendered project figure." if status == "ok" else "Rendered project figure with preflight warnings."
            ),
            created_paths=created_paths,
            artifact_resources=[f"file://{figure['path']}" for figure in manifest["figures"]],
            warnings=preflight_warnings + baseline_warnings + geometry_warnings + figure_format_warnings,
            manual_review_needed=manual_review_needed,
            is_dry_run=False,
            job_id=job_id,
            project_id=project_id,
            source_project_path=source_project_path,
            job_root=str(job_root),
            snapshot_project_path=str(snapshot_project_path),
            selected_figure=selected_public,
            output_path=str(output_path),
            config_path=str(config_path),
            manifest_path=str(manifest_path),
            status_path=str(status_path),
            latest_dir=str(latest_dir),
            latest_alias=str(latest_dir),
            style_summary=style_summary,
            visual_preflight_status=preflight,
            geometry_diagnostics=geometry_diagnostics,
            layout_report=layout_report,
            figure_metadata=figure_metadata,
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
            provenance=provenance,
            failure_stage="",
            resolution_hint="",
        )

    def _activate_runtime_root_for_runtime_access(self) -> None:
        if not self._runtime_root_explicit:
            self.runtime_root = Path(resolve_runtime_root()).expanduser().resolve()
            self.allowed_data_roots = self._allowed_data_roots()

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
        layout_report = _layout_report_from_geometry(
            _geometry_stub("render_execution_failed"),
            failure_stage=failure_stage,
        )
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
            "layout_report": layout_report,
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
        status_payload["layout_report"] = layout_report
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
    @contextmanager
    def _geometry_diagnostics_env(job_root: Path):
        """Set GEOMETRY_DIAGNOSTICS_OUT/_DEADLINE for the spawn-child render, then restore.

        Both vars mutate the parent os.environ so the spawn child inherits them; the finally
        restores/pops them so a stale path/deadline never redirects the next in-process render.
        The deadline is an absolute epoch (time.time()), cross-process comparable; the child
        reads it against a fixed floor (see themes.journal_theme.DIAG_BUDGET_FLOOR_SECONDS).
        """
        prior_out = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
        prior_deadline = os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE")
        os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(job_root / "geometry_diagnostics.json")
        os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + MCP_RENDER_TIMEOUT_SECONDS)
        try:
            yield
        finally:
            for key, prior in (
                ("GEOMETRY_DIAGNOSTICS_OUT", prior_out),
                ("GEOMETRY_DIAGNOSTICS_DEADLINE", prior_deadline),
            ):
                if prior is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = prior

    @staticmethod
    def _run_render_bridge_figure(spec_payload: dict[str, Any]) -> None:
        result_queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
        process = multiprocessing.Process(
            target=_render_bridge_figure_worker,
            args=(spec_payload, result_queue),
            name="graphhub-mcp-render",
        )
        try:
            process.start()
            try:
                result = result_queue.get(timeout=MCP_RENDER_TIMEOUT_SECONDS)
            except queue.Empty as exc:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                    if process.is_alive():
                        process.kill()
                        process.join(5)
                    raise TimeoutError(f"Render timed out after {MCP_RENDER_TIMEOUT_SECONDS:.1f} seconds.") from exc
                if process.exitcode not in (0, None):
                    raise RuntimeError(f"Render worker exited with code {process.exitcode}.") from exc
                raise RuntimeError("Render worker exited without returning a result.") from exc
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                raise TimeoutError("Render worker returned a result but did not exit cleanly.")
            if process.exitcode not in (0, None):
                raise RuntimeError(f"Render worker exited with code {process.exitcode}.")
            if result.get("status") != "ok":
                trace = result.get("traceback") if isinstance(result.get("traceback"), list) else []
                message = "\n".join(str(line) for line in trace[-SCRIPT_OUTPUT_TAIL_LINES:]) or str(
                    result.get("error") or "Render worker failed."
                )
                raise RuntimeError(message)
        finally:
            close_queue = getattr(result_queue, "close", None)
            if close_queue is not None:
                close_queue()
            join_queue_thread = getattr(result_queue, "join_thread", None)
            if join_queue_thread is not None:
                join_queue_thread()

    def _project_render_error(
        self,
        arguments: dict[str, Any],
        *,
        dry_run: bool,
        job_id: str,
        job_root: Path,
        summary: str,
        errors: list[str],
        failure_stage: str,
        resolution_hint: str,
        **extra: Any,
    ) -> dict[str, Any]:
        geometry_diagnostics = extra.pop("geometry_diagnostics", _geometry_stub("no figure"))
        return self._envelope(
            "graphhub.render_project_figure",
            arguments,
            status="error",
            summary=summary,
            errors=errors,
            manual_review_needed=True,
            is_dry_run=dry_run,
            job_id=job_id,
            job_root=str(job_root),
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            provenance={},
            geometry_diagnostics=geometry_diagnostics,
            layout_report=extra.pop(
                "layout_report",
                _layout_report_from_geometry(geometry_diagnostics, failure_stage=failure_stage),
            ),
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
            **extra,
        )

    def _resolve_project_render_path(self, arguments: dict[str, Any]) -> Path:
        project_path_value = arguments.get("project_path")
        project_id_value = arguments.get("project_id")
        if project_path_value and project_id_value:
            project_path = self._resolve_under_root(project_path_value, field_name="project_path")
            id_project_path = self._resolve_project_path(
                {key: value for key, value in arguments.items() if key != "project_path"}
            )
            if project_path != id_project_path:
                raise ValueError("project_id and project_path resolve to different projects.")
            return project_path
        if project_path_value:
            return self._resolve_under_root(project_path_value, field_name="project_path")
        return self._resolve_project_path(arguments)

    @staticmethod
    def _project_figure_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
        return GraphHubMCPServer._list_section(config, "figures")

    @staticmethod
    def _select_project_figure(
        figures: list[dict[str, Any]],
        *,
        figure_id: Any,
        figure_output: Any,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        if not figures:
            return None, ["Project config has no figures[] entries."]
        id_text = str(figure_id).strip() if isinstance(figure_id, str) and figure_id.strip() else ""
        output_text = str(figure_output).strip() if isinstance(figure_output, str) and figure_output.strip() else ""
        if id_text and output_text:
            matches = [
                figure
                for figure in figures
                if str(figure.get("id") or "") == id_text and str(figure.get("output") or "") == output_text
            ]
            return (
                (matches[0], [])
                if len(matches) == 1
                else (None, ["figure_id and figure_output did not match one figure."])
            )
        if id_text:
            matches = [figure for figure in figures if str(figure.get("id") or "") == id_text]
            return (matches[0], []) if len(matches) == 1 else (None, [f"figure_id not found or ambiguous: {id_text}"])
        if output_text:
            matches = [figure for figure in figures if str(figure.get("output") or "") == output_text]
            return (
                (matches[0], [])
                if len(matches) == 1
                else (None, [f"figure_output not found or ambiguous: {output_text}"])
            )
        if len(figures) == 1:
            return figures[0], []
        return None, ["Project has multiple figures; provide figure_id or figure_output."]

    @staticmethod
    def _figure_selector_summary(figures: list[dict[str, Any]]) -> str:
        selectors = []
        for figure in figures:
            figure_id = str(figure.get("id") or "").strip()
            output = str(figure.get("output") or "").strip()
            selector = ", ".join(part for part in (f"figure_id={figure_id}" if figure_id else "", output) if part)
            if selector:
                selectors.append(selector)
        return "; ".join(selectors) if selectors else "<no configured figures>"

    @staticmethod
    def _public_selected_figure(figure: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(figure.get("id") or ""),
            "script": str(figure.get("script") or ""),
            "output": str(figure.get("output") or ""),
        }

    def _stable_project_id_for_path(self, project_path: Path) -> str:
        # Single source of truth: same id ProjectDiscoveryService assigns, so a
        # rendered project reports back the id list_projects emits for it.
        return ProjectDiscoveryService._stable_project_id(project_path)

    def _public_project_path(self, project_path: Path) -> str:
        try:
            return project_path.resolve().relative_to(self.research_root).as_posix()
        except ValueError:
            return "input://project_path"

    @staticmethod
    def _project_relative_path(raw_path: Any, field_name: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{field_name} must be a non-empty project-relative path.")
        relpath = Path(raw_path.strip())
        if relpath.is_absolute() or ".." in relpath.parts:
            raise ValueError(f"{field_name} must be project-relative and must not contain '..'.")
        return relpath

    @staticmethod
    def _selected_figure_style_summary(
        config: dict[str, Any],
        selected_figure: dict[str, Any],
        arguments: dict[str, Any],
    ) -> dict[str, str]:
        visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
        output_relpath = str(selected_figure.get("output") or "")
        inferred_format = Path(output_relpath).suffix.lower().lstrip(".") or "png"
        return {
            "target_format": str(arguments.get("target_format") or visual_style.get("target_format") or "nature")
            .strip()
            .lower(),
            "profile": str(arguments.get("profile") or visual_style.get("profile") or DEFAULT_PROFILE).strip()
            or DEFAULT_PROFILE,
            "output_format": str(arguments.get("output_format") or selected_figure.get("format") or inferred_format)
            .strip()
            .lower()
            .lstrip("."),
        }

    @staticmethod
    def _selected_figure_declared_inputs(selected_figure: dict[str, Any]) -> list[str]:
        raw_inputs = selected_figure.get("inputs") or selected_figure.get("input") or []
        if isinstance(raw_inputs, str):
            raw_inputs = [raw_inputs]
        if not isinstance(raw_inputs, list):
            return []
        return [str(item) for item in raw_inputs if isinstance(item, str) and item.strip()]

    def _copy_project_snapshot(
        self,
        *,
        source_project: Path,
        snapshot_project: Path,
        config_relpath: str,
        selected_figure: dict[str, Any],
    ) -> list[str]:
        if snapshot_project.exists():
            shutil.rmtree(snapshot_project)
        snapshot_project.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []

        def copy_relative_path(raw_relpath: str) -> None:
            try:
                relpath = self._project_relative_path(raw_relpath, "snapshot path")
            except ValueError as exc:
                raise ProjectRenderExportError(str(exc)) from exc
            source_path = source_project / relpath
            destination_path = snapshot_project / relpath
            if not source_path.exists():
                raise ProjectRenderExportError(f"Required project snapshot path not found: {raw_relpath}")
            if source_path.is_symlink():
                raise ProjectRenderExportError(f"Project snapshot refuses symlinked path: {raw_relpath}")
            try:
                source_path.resolve().relative_to(source_project.resolve())
            except ValueError as exc:
                raise ProjectRenderExportError(f"Project snapshot path escapes project root: {raw_relpath}") from exc
            if source_path.is_dir():
                self._copy_project_snapshot_directory(source_path, destination_path, copied)
                return
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            copied.append(str(destination_path))

        copy_relative_path(config_relpath)
        script_rel = str(selected_figure.get("script") or "").split("::")[0]
        if script_rel:
            copy_relative_path(script_rel)
        for input_rel in self._selected_figure_declared_inputs(selected_figure):
            copy_relative_path(input_rel)
        for standard_folder in ("hub_scripts", "results/data"):
            if (source_project / standard_folder).is_dir():
                copy_relative_path(standard_folder)
        return [str(path) for path in snapshot_project.rglob("*") if path.is_file()]

    @staticmethod
    def _copy_project_snapshot_directory(source_dir: Path, destination_dir: Path, copied: list[str]) -> None:
        ignored_dirs = {".git", ".venv", "__pycache__", ".pytest_cache", ".dvc"}
        source_root = source_dir.resolve()
        for current_root, dirs, files in os.walk(source_dir):
            current_path = Path(current_root)
            dirs[:] = [dirname for dirname in dirs if dirname not in ignored_dirs]
            for dirname in list(dirs):
                child_dir = current_path / dirname
                if child_dir.is_symlink():
                    raise ProjectRenderExportError(f"Project snapshot refuses symlinked directory: {child_dir}")
                try:
                    child_dir.resolve().relative_to(source_root)
                except ValueError as exc:
                    raise ProjectRenderExportError(
                        f"Project snapshot directory escapes source tree: {child_dir}"
                    ) from exc
            relative_root = current_path.relative_to(source_dir)
            destination_root = destination_dir / relative_root
            destination_root.mkdir(parents=True, exist_ok=True)
            for filename in files:
                source_file = current_path / filename
                if source_file.is_symlink():
                    raise ProjectRenderExportError(f"Project snapshot refuses symlinked file: {source_file}")
                try:
                    source_file.resolve().relative_to(source_root)
                except ValueError as exc:
                    raise ProjectRenderExportError(f"Project snapshot file escapes source tree: {source_file}") from exc
                destination_file = destination_root / filename
                shutil.copy2(source_file, destination_file)
                copied.append(str(destination_file))

    def _run_project_figure_script(
        self,
        *,
        snapshot_project_path: Path,
        selected_figure: dict[str, Any],
        style_summary: dict[str, str],
    ) -> None:
        try:
            script_rel = self._project_relative_path(
                str(selected_figure.get("script") or "").split("::")[0],
                "figures[].script",
            )
        except ValueError as exc:
            raise ProjectRenderExportError(str(exc)) from exc
        script_path = snapshot_project_path / script_rel
        if not script_path.is_file():
            raise ProjectRenderExportError(f"Selected figure script not found: {script_rel.as_posix()}")
        # job_root is the snapshot parent; the sidecar must land OUTSIDE the snapshot
        # tree so it never enters environment_sha256 (which rglob-hashes the snapshot).
        job_root = snapshot_project_path.parent
        script_output_path = job_root / "script_output.json"
        env = os.environ.copy()
        env.update(
            {
                "RESEARCH_HUB_PATH": str(self.hub_path),
                "PYTHONPATH": self._pythonpath_with_hub(env),
                "PROJECT_ROOT": str(snapshot_project_path),
                "THEME_FORMAT": style_summary["target_format"],
                "THEME_PROFILE": style_summary["profile"],
                "THEME_OUTPUT_FORMAT": style_summary["output_format"],
                "GEOMETRY_DIAGNOSTICS_OUT": str(job_root / "geometry_diagnostics.json"),
                "GEOMETRY_DIAGNOSTICS_DEADLINE": str(time.time() + MCP_RENDER_TIMEOUT_SECONDS),
            }
        )
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(snapshot_project_path),
                text=True,
                capture_output=True,
                check=False,
                timeout=MCP_RENDER_TIMEOUT_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            self._write_project_script_output(
                script_output_path,
                returncode=None,
                stdout=exc.stdout,
                stderr=exc.stderr,
                timed_out=True,
            )
            raise TimeoutError(f"Figure script timed out after {MCP_RENDER_TIMEOUT_SECONDS:.1f} seconds.") from exc
        self._write_project_script_output(
            script_output_path,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
        )
        if completed.returncode != 0:
            message = (
                completed.stderr.strip() or completed.stdout.strip() or f"Figure script exited {completed.returncode}."
            )
            raise ProjectRenderScriptError(
                message,
                returncode=completed.returncode,
                script_output=self._script_output_tail(completed.stdout, completed.stderr),
            )

    @staticmethod
    def _normalize_script_stream(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @classmethod
    def _script_output_tail(cls, stdout: Any, stderr: Any) -> list[str]:
        combined = "\n".join(
            part
            for part in (
                cls._normalize_script_stream(stdout),
                cls._normalize_script_stream(stderr),
            )
            if part
        )
        lines = [line.rstrip() for line in combined.splitlines() if line.strip()]
        return lines[-SCRIPT_OUTPUT_TAIL_LINES:]

    @classmethod
    def _write_project_script_output(
        cls,
        path: Path,
        *,
        returncode: int | None,
        stdout: Any,
        stderr: Any,
        timed_out: bool,
    ) -> None:
        payload = {
            "returncode": returncode,
            "timed_out": bool(timed_out),
            "tail": cls._script_output_tail(stdout, stderr),
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _read_project_script_output(job_root: Path) -> list[str]:
        try:
            payload = json.loads((job_root / "script_output.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        tail = payload.get("tail")
        if not isinstance(tail, list):
            return []
        return [str(line) for line in tail if str(line).strip()]

    def _project_failure_script_output(self, exc: Exception, job_root: Path) -> list[str]:
        explicit = getattr(exc, "script_output", None)
        if isinstance(explicit, list) and explicit:
            return [str(line) for line in explicit if str(line).strip()]
        return self._read_project_script_output(job_root)

    @staticmethod
    def _exception_error_lines(exc: Exception) -> list[str]:
        lines = [line.rstrip() for line in traceback.format_exception(type(exc), exc, exc.__traceback__)]
        compact = [line for line in lines if line.strip()]
        message = str(exc).strip()
        tail = compact[-SCRIPT_OUTPUT_TAIL_LINES:]
        if message:
            tail = [line for line in tail if line != message]
            return [message, *tail]
        return tail or [type(exc).__name__]

    def _pythonpath_with_hub(self, env: dict[str, str]) -> str:
        hub_path = str(self.hub_path)
        current = env.get("PYTHONPATH", "")
        parts = [part for part in current.split(os.pathsep) if part and part != hub_path]
        return os.pathsep.join([hub_path, *parts])

    @staticmethod
    def _project_context_render_warnings(project_path: Path) -> list[str]:
        context_path = project_path / "hub_scripts" / "project_context.py"
        if not context_path.exists():
            return []
        try:
            context_text = context_path.read_text(encoding="utf-8")
        except OSError as exc:
            return [f"Could not inspect hub_scripts/project_context.py for MCP render path safety: {exc}"]
        if "RESEARCH_HUB_PATH" in context_text:
            return []
        return [
            "hub_scripts/project_context.py does not reference RESEARCH_HUB_PATH; MCP snapshot renders "
            "inject the canonical hub on PYTHONPATH, but this project should be updated to the env-first "
            "project_context.py template for portable direct runs."
        ]

    def _write_project_render_failure_artifacts(
        self,
        *,
        job_id: str,
        job_root: Path,
        snapshot_project_path: Path,
        selected_figure: dict[str, Any],
        manifest_path: Path,
        status_path: Path,
        latest_dir: Path,
        created_paths: list[str],
        failure_stage: str,
        resolution_hint: str,
        baseline_comparison: dict[str, Any],
        script_output: list[str] | None = None,
        layout_report: dict[str, Any] | None = None,
    ) -> list[str]:
        script_output = script_output or []
        layout_report = layout_report or _layout_report_from_geometry(
            _geometry_stub("render_execution_failed"),
            failure_stage=failure_stage,
            script_output=script_output,
        )
        created = list(created_paths)
        manifest = {
            "job_id": job_id,
            "job_root": str(job_root),
            "snapshot_project_path": str(snapshot_project_path),
            "selected_figure": selected_figure,
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
            "layout_report": layout_report,
            "failure_stage": failure_stage,
            "resolution_hint": resolution_hint,
            "script_output": script_output,
            "artifact_status": "failed",
            "baseline_comparison": baseline_comparison,
            "manual_review_needed": True,
        }
        status_payload = self._render_status_payload(
            job_id=job_id,
            status="error",
            summary="Project figure render execution failed.",
            manifest_path=manifest_path,
            output_path=snapshot_project_path / str(selected_figure.get("output") or ""),
            artifact_status="failed",
            manual_review_needed=True,
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
        )
        if script_output:
            status_payload["script_output"] = script_output
        status_payload["layout_report"] = layout_report
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        status_path.write_text(
            json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        for path in (manifest_path, status_path):
            path_text = str(path)
            if path_text not in created:
                created.append(path_text)
        manifest["created_paths"] = created
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        latest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest_path, latest_dir / "manifest.json")
        shutil.copy2(status_path, latest_dir / "status.json")
        return created

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
        layout_report = (
            manifest.get("layout_report")
            if isinstance(manifest.get("layout_report"), dict)
            else _layout_report_from_geometry(manifest.get("geometry_diagnostics") or _geometry_stub("no figure"))
        )
        figures = manifest.get("figures") if isinstance(manifest.get("figures"), list) else []
        figure_metadata = manifest.get("figure_metadata") if isinstance(manifest.get("figure_metadata"), dict) else {}
        figure_format_warnings = self._figure_metadata_warnings(figure_metadata)
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
            or bool(figure_format_warnings)
            or (baseline_comparison["checked"] and not baseline_comparison["matched"])
        )
        status = (
            "error"
            if persisted_failed
            else ("warning" if manual_review_needed or preflight.get("passed") is False else "ok")
        )
        artifact_status = (
            persisted_artifact_status if persisted_failed else self._artifact_status(preflight, baseline_comparison)
        )
        return self._envelope(
            "graphhub.collect_artifacts",
            arguments,
            status=status,
            summary=f"Collected artifacts for render job {job_id}.",
            artifact_resources=[f"file://{figure['path']}" for figure in figures if isinstance(figure, dict)],
            warnings=preflight_warnings + baseline_warnings + figure_format_warnings,
            script_output=manifest.get("script_output") if isinstance(manifest.get("script_output"), list) else [],
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
                **(manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}),
            },
            visual_preflight_status=preflight,
            layout_report=layout_report,
            figure_metadata=figure_metadata,
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
        )

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = self._parse_resource_uri(uri)
        authority = parsed["authority"]
        segments = parsed["segments"]

        if authority == "styles" and not segments:
            return self._resource_text(uri, "application/json", self._json_resource_text(self._styles_payload()))
        if authority == "profiles" and not segments:
            payload = {
                "profiles": list_profiles(),
                "profile_aliases": dict(sorted(PROFILE_ALIASES.items())),
                "default_profile": DEFAULT_PROFILE,
            }
            return self._resource_text(uri, "application/json", self._json_resource_text(payload))
        if authority == "projects" and not segments:
            root = self.research_root
            projects = ProjectDiscoveryService(root).discover(max_depth=4)
            payload = {
                "root": str(root),
                "count": len(projects),
                "projects": [self._serialize_project(project) for project in projects],
            }
            return self._resource_text(uri, "application/json", self._json_resource_text(payload))
        if authority == "projects" and len(segments) == 2 and segments[1] == "config":
            project = self._discover_project_by_id(segments[0])
            config_path = Path(project.config_path)
            self._validate_resource_config_path(config_path, (self.research_root / project.path).resolve())
            try:
                text = config_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise FileNotFoundError(f"Project config not found: {project.project_id}") from exc
            return self._resource_text(uri, "application/x-yaml", text)
        if authority == "jobs" and len(segments) == 2 and segments[1] == "manifest":
            job_id = segments[0]
            if _STRICT_JOB_ID_RE.fullmatch(job_id) is None:
                raise ValueError("job_id contains invalid characters.")
            manifest_path = self._find_job_manifest_path(job_id)
            if not manifest_path.exists():
                raise FileNotFoundError(f"Render job manifest not found: {job_id}")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Render job manifest could not be read: {exc}") from exc
            sanitized = self._sanitize_resource_payload(manifest, {"data_path": manifest.get("source_data_path")})
            return self._resource_text(uri, "application/json", self._json_resource_text(sanitized))

        raise ValueError(f"Unsupported Graph Hub resource URI: {uri}")

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        if name == "make_publication_graph_from_csv":
            self._validate_prompt_arguments(
                name,
                arguments,
                required={"data_path", "x_column", "y_column"},
                optional={"target_format", "plot_type"},
            )
            data_path = self._prompt_quote(arguments["data_path"])
            x_column = self._prompt_quote(arguments["x_column"])
            y_column = self._prompt_quote(arguments["y_column"])
            target_format = self._prompt_quote(arguments.get("target_format", "nature"))
            plot_type = self._prompt_quote(arguments.get("plot_type", "scatter"))
            text = (
                "Render a publication-style Graph Hub figure from structured CSV data.\n"
                f"- data_path: {data_path}\n"
                f"- x_column: {x_column}\n"
                f"- y_column: {y_column}\n"
                f"- target_format: {target_format}\n"
                f"- plot_type: {plot_type}\n\n"
                "Workflow:\n"
                "1. If style support is uncertain, call graphhub.list_styles.\n"
                "2. Call graphhub.render_csv_graph with dry_run=true using the supplied CSV and columns.\n"
                "3. Inspect calculation_checks, visual_preflight_status, failure_stage, and resolution_hint.\n"
                "4. Rerun graphhub.render_csv_graph without dry_run only when the dry run is clean "
                "or the user accepts warnings.\n"
                "5. Call graphhub.collect_artifacts for the returned job_id.\n"
                "6. If manual_review_needed=true, do not claim publication readiness without manual review."
            )
            return self._prompt_payload(
                "Workflow for rendering a publication-style graph from structured CSV data.",
                text,
            )

        if name == "inspect_graph_project_quality":
            self._validate_prompt_arguments(
                name,
                arguments,
                required=set(),
                optional={"project_id", "project_path"},
            )
            if not arguments.get("project_id") and not arguments.get("project_path"):
                raise ValueError("project_id or project_path is required.")
            selector = (
                f"project_id: {self._prompt_quote(arguments['project_id'])}"
                if arguments.get("project_id")
                else f"project_path: {self._prompt_quote(arguments['project_path'])}"
            )
            text = (
                "Inspect Graph Hub project quality without executing analysis or plotting scripts.\n"
                f"- {selector}\n\n"
                "Workflow:\n"
                "1. Call graphhub.inspect_project for the selected project.\n"
                "2. Call graphhub.validate_project for the same selector.\n"
                "3. Inspect config_errors, data_contract_errors, style_errors, missing_inputs, missing_outputs, "
                "and normalization_needed.\n"
                "4. Avoid rendering or normalization unless the user explicitly asks."
            )
            return self._prompt_payload("Workflow for inspecting graph project quality.", text)

        if name == "standardize_existing_graph_project":
            self._validate_prompt_arguments(
                name,
                arguments,
                required={"project_path"},
                optional={"move_policy"},
            )
            project_path = self._prompt_quote(arguments["project_path"])
            move_policy = self._prompt_quote(arguments.get("move_policy", "copy"))
            text = (
                "Plan safe Graph Hub project normalization.\n"
                f"- project_path: {project_path}\n"
                f"- move_policy: {move_policy}\n\n"
                "Workflow:\n"
                "1. Call graphhub.inspect_project.\n"
                "2. Call graphhub.normalize_project_structure with plan_only=true.\n"
                "3. Show the manifest and preserve project style choices.\n"
                "4. Apply only after user approval.\n"
                "5. Call graphhub.validate_project after apply."
            )
            return self._prompt_payload("Workflow for planning safe project normalization.", text)

        if name == "render_project_figure":
            self._validate_prompt_arguments(
                name,
                arguments,
                required=set(),
                optional={"project_id", "project_path", "figure_id", "figure_output"},
            )
            if not arguments.get("project_id") and not arguments.get("project_path"):
                raise ValueError("render_project_figure requires project_id or project_path.")
            selector = arguments.get("figure_id") or arguments.get("figure_output") or "<single configured figure>"
            text = (
                "Project figure workflow:\n"
                "1. Call graphhub.inspect_project for the selected project.\n"
                "2. Call graphhub.validate_project and stop on status=error.\n"
                f"3. Call graphhub.render_project_figure for selector {selector!r} with dry_run=true first.\n"
                "4. If dry_run is clean, call graphhub.render_project_figure without dry_run.\n"
                "5. Call graphhub.collect_artifacts for the returned job_id.\n"
                "6. Report manifest_path, status_path, provenance, failure_stage, resolution_hint, "
                "and manual_review_needed."
            )
            return self._prompt_payload(
                "Workflow for rendering one configured project figure through Graph Hub MCP.",
                text,
            )

        raise FileNotFoundError(f"Unknown prompt: {name}")

    def scaffold_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_name = self._required_string(arguments, "project_name")
        project_root = self._resolve_under_root(arguments.get("project_root"), field_name="project_root")
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
        project_path = self._resolve_under_root(arguments.get("project_path"), field_name="project_path")
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
            try:
                resume_path = self._resolve_allowed_data_path(
                    self._required_string(arguments, "resume_manifest_path"),
                    field_name="resume_manifest_path",
                )
            except ValueError as exc:
                return self._envelope(
                    "graphhub.batch_check",
                    arguments,
                    status="error",
                    summary="Batch resume manifest path is outside the allowed data roots.",
                    errors=[str(exc)],
                    manual_review_needed=True,
                    is_dry_run=dry_run,
                    failure_stage="CONTRACT",
                    resolution_hint="Point resume_manifest_path at a manifest under an allowed data root.",
                    batch_id=batch_id,
                    batch_root=str(batch_root),
                    manifest_path=str(manifest_path),
                    checked_projects=[],
                    skipped_projects=[],
                    resumed_from="",
                    log_paths=[],
                )
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
            resolved_root = Path(root).expanduser().resolve()
            for jobs_dir_name in ("mcp_jobs", "mcp_project_jobs"):
                manifest_path = resolved_root / jobs_dir_name / job_id / "manifest.json"
                key = str(manifest_path)
                if key in seen:
                    continue
                seen.add(key)
                if manifest_path.exists():
                    return manifest_path
        return Path(candidate_roots[0]).expanduser().resolve() / "mcp_jobs" / job_id / "manifest.json"

    def _styles_payload(self) -> dict[str, Any]:
        return {
            "target_formats": sorted(ALLOWED_TARGET_FORMATS),
            "output_formats": sorted(ALLOWED_OUTPUT_FORMATS),
            "profiles": list_profiles(),
            "profile_aliases": dict(sorted(PROFILE_ALIASES.items())),
            "style_packs": list_style_packs(),
            "default_target_format": "nature",
            "default_profile": DEFAULT_PROFILE,
        }

    @staticmethod
    def _resource_text(uri: str, mime_type: str, text: str) -> dict[str, Any]:
        return {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]}

    @staticmethod
    def _json_resource_text(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    @staticmethod
    def _parse_resource_uri(uri: str) -> dict[str, Any]:
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError("Resource uri is required.")
        parsed = urlsplit(uri)
        if parsed.scheme != "graphhub":
            raise ValueError("Resource uri scheme must be graphhub.")
        if parsed.query or parsed.fragment:
            raise ValueError("Resource uri query and fragment are not supported.")
        authority = parsed.netloc
        if authority not in {"styles", "profiles", "projects", "jobs"}:
            raise ValueError(f"Unsupported Graph Hub resource authority: {authority}")
        if authority in {"styles", "profiles"} and parsed.path:
            raise ValueError(f"Resource graphhub://{authority} does not accept path segments.")
        if authority == "projects" and not parsed.path:
            return {"authority": authority, "segments": []}
        if authority == "jobs" and not parsed.path:
            raise ValueError("Job resource must be graphhub://jobs/{job_id}/manifest.")
        if authority in {"projects", "jobs"} and not parsed.path.startswith("/"):
            raise ValueError("Dynamic Graph Hub resource path must start with '/'.")
        raw_segments = parsed.path[1:].split("/") if parsed.path else []
        if any(segment == "" for segment in raw_segments):
            raise ValueError("Resource uri contains an empty path segment.")
        segments = [unquote(segment) for segment in raw_segments]
        if any(segment in {"", ".", ".."} or "/" in segment or "\\" in segment for segment in segments):
            raise ValueError("Resource uri contains an invalid path segment.")
        if authority == "projects" and not (len(segments) == 2 and segments[1] == "config"):
            raise ValueError("Project resource must be graphhub://projects or graphhub://projects/{project_id}/config.")
        if authority == "jobs" and not (len(segments) == 2 and segments[1] == "manifest"):
            raise ValueError("Job resource must be graphhub://jobs/{job_id}/manifest.")
        return {"authority": authority, "segments": segments}

    @staticmethod
    def _validate_resource_config_path(config_path: Path, project_path: Path) -> None:
        if config_path.is_symlink():
            raise ValueError("Project config resource refuses symlinked config files.")
        resolved_config = config_path.resolve()
        resolved_project = project_path.resolve()
        try:
            resolved_config.relative_to(resolved_project)
        except ValueError as exc:
            raise ValueError("Project config resource must stay inside the discovered project.") from exc
        if not config_path.is_file():
            raise FileNotFoundError(f"Project config not found: {config_path}")
        if config_path.stat().st_size > 1024 * 1024:
            raise ValueError("Project config resource refuses configs larger than 1 MiB.")

    def _discover_project_by_id(self, project_id: str) -> Any:
        for project in ProjectDiscoveryService(self.research_root).discover(max_depth=4):
            if project.project_id == project_id:
                return project
        raise FileNotFoundError(f"Project id not found: {project_id}")

    def _sanitize_resource_payload(self, value: Any, arguments: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize_resource_payload(item, arguments) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_resource_payload(item, arguments) for item in value]
        if isinstance(value, str):
            return self._sanitize_diagnostic_text(value, arguments)
        return value

    @staticmethod
    def _prompt_payload(description: str, text: str) -> dict[str, Any]:
        return {"description": description, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

    @staticmethod
    def _prompt_quote(value: Any) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _validate_prompt_arguments(
        name: str,
        arguments: dict[str, Any],
        *,
        required: set[str],
        optional: set[str],
    ) -> None:
        allowed = required | optional
        unknown = sorted(set(arguments) - allowed)
        if unknown:
            raise ValueError(f"Unknown prompt argument(s) for {name}: {', '.join(unknown)}")
        missing = sorted(
            key for key in required if not isinstance(arguments.get(key), str) or not arguments.get(key).strip()
        )
        if missing:
            raise ValueError(f"Missing required prompt argument(s) for {name}: {', '.join(missing)}")
        invalid = sorted(
            key
            for key, value in arguments.items()
            if key in allowed and (not isinstance(value, str) or not value.strip())
        )
        if invalid:
            raise ValueError(f"Prompt argument(s) must be non-empty strings for {name}: {', '.join(invalid)}")

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

    def _baseline_comparison(self, artifact_path: Path | None, raw_baseline_path: Any) -> dict[str, Any]:
        if not isinstance(raw_baseline_path, str) or not raw_baseline_path.strip():
            return {"checked": False, "matched": None, "status": "not_checked", "warnings": []}

        try:
            baseline_path = self._resolve_allowed_data_path(raw_baseline_path, field_name="baseline_path")
        except ValueError as exc:
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": "",
                "artifact_path": str(artifact_path) if artifact_path else "",
                "algorithm": "sha256",
                "warnings": [str(exc)],
            }
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

    def _mcp_render_provenance(
        self,
        *,
        job_id: str,
        source_data_path: Path,
        copied_data_path: Path,
        config_path: Path,
        output_path: Path,
        target_format: str,
        profile: str,
        output_format: str,
    ) -> dict[str, Any]:
        source_hash = self._file_sha256(source_data_path) if source_data_path.is_file() else ""
        copied_hash = self._file_sha256(copied_data_path) if copied_data_path.is_file() else ""
        config_hash = self._file_sha256(config_path) if config_path.is_file() else ""
        output_hash = self._file_sha256(output_path) if output_path.is_file() else ""
        python_lock = self.hub_path / "uv.lock"
        r_lock = self.hub_path / "renv.lock"
        lock_status = {
            "python_lock": {
                "path": str(python_lock),
                "exists": python_lock.is_file(),
                "sha256": self._file_sha256(python_lock) if python_lock.is_file() else "",
            },
            "r_lock": {
                "path": str(r_lock),
                "exists": r_lock.is_file(),
                "sha256": self._file_sha256(r_lock) if r_lock.is_file() else "",
            },
        }
        env_payload = {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "target_format": target_format,
            "profile": profile,
            "output_format": output_format,
            "lock_status": lock_status,
            "renderer": "plotting.bridge_renderer.render_bridge_figure",
            "mcp_surface_version": self._read_version(),
        }
        environment_hash = hashlib.sha256(
            json.dumps(env_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "job_id": job_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "renderer": "plotting.bridge_renderer.render_bridge_figure",
            "renderer_surface": "graphhub.render_csv_graph",
            "mcp_surface_version": self._read_version(),
            "hub_git_commit": self._git_commit(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "source_data_sha256": source_hash,
            "copied_data_sha256": copied_hash,
            "config_sha256": config_hash,
            "output_sha256": output_hash,
            "environment_sha256": environment_hash,
            "lock_status": lock_status,
        }

    def _mcp_project_render_provenance(
        self,
        *,
        job_id: str,
        project_path: Path,
        snapshot_project_path: Path,
        config_path: Path,
        output_path: Path,
        selected_figure: dict[str, Any],
        style_summary: dict[str, str],
    ) -> dict[str, Any]:
        config_hash = self._file_sha256(config_path) if config_path.is_file() else ""
        output_hash = self._file_sha256(output_path) if output_path.is_file() else ""
        project_files = sorted(path for path in snapshot_project_path.rglob("*") if path.is_file())
        snapshot_payload = [
            {
                "path": path.relative_to(snapshot_project_path).as_posix(),
                "sha256": self._file_sha256(path),
            }
            for path in project_files
        ]
        python_lock = self.hub_path / "uv.lock"
        r_lock = self.hub_path / "renv.lock"
        lock_status = {
            "python_lock": {
                "path": str(python_lock),
                "exists": python_lock.is_file(),
                "sha256": self._file_sha256(python_lock) if python_lock.is_file() else "",
            },
            "r_lock": {
                "path": str(r_lock),
                "exists": r_lock.is_file(),
                "sha256": self._file_sha256(r_lock) if r_lock.is_file() else "",
            },
        }
        env_payload = {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "selected_figure": self._public_selected_figure(selected_figure),
            "style_summary": style_summary,
            "lock_status": lock_status,
            "renderer": "project_config.figure_script",
            "mcp_surface_version": self._read_version(),
            "snapshot_files": snapshot_payload,
        }
        environment_hash = hashlib.sha256(
            json.dumps(env_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "job_id": job_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "renderer": "project_config.figure_script",
            "renderer_surface": "graphhub.render_project_figure",
            "mcp_surface_version": self._read_version(),
            "hub_git_commit": self._git_commit(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "source_project_path": self._public_project_path(project_path),
            "snapshot_project_path": str(snapshot_project_path),
            "selected_figure": self._public_selected_figure(selected_figure),
            "snapshot_file_count": len(snapshot_payload),
            "snapshot_files_sha256": hashlib.sha256(
                json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "config_sha256": config_hash,
            "output_sha256": output_hash,
            "environment_sha256": environment_hash,
            "lock_status": lock_status,
        }

    def _git_commit(self) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.hub_path), "rev-parse", "--short", "HEAD"],
                text=True,
                capture_output=True,
                check=False,
                timeout=3,
            )
        except Exception:
            return ""
        return completed.stdout.strip() if completed.returncode == 0 else ""

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
        script_output = extra.pop("script_output", None)
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
            "script_output": [self._sanitize_diagnostic_text(line, arguments) for line in (script_output or [])],
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
        root = arguments.get("root")
        if root:
            return self._resolve_under_root(root, field_name="root")
        return self.research_root

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
        try:
            process.start()
            try:
                result = result_queue.get(timeout=max(0.0, timeout_seconds))
            except queue.Empty:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                    if process.is_alive():
                        process.kill()
                        process.join(5)
                    return [], True, [f"Batch discovery timed out after {timeout_seconds:.1f} seconds."]
                if process.exitcode not in (0, None):
                    return [], True, [f"Batch discovery worker exited with code {process.exitcode}."]
                return [], True, ["Batch discovery worker exited without returning a result."]
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                return [], True, ["Batch discovery worker returned a result but did not exit cleanly."]
            if process.exitcode not in (0, None):
                return [], True, [f"Batch discovery worker exited with code {process.exitcode}."]
            if result.get("status") != "ok":
                trace = result.get("traceback") if isinstance(result.get("traceback"), list) else []
                message = "\n".join(str(line) for line in trace[-SCRIPT_OUTPUT_TAIL_LINES:]) or str(
                    result.get("error") or "Batch discovery failed."
                )
                return [], True, [message]
            projects = result.get("projects")
            return (projects if isinstance(projects, list) else []), False, []
        finally:
            close_queue = getattr(result_queue, "close", None)
            if close_queue is not None:
                close_queue()
            join_queue_thread = getattr(result_queue, "join_thread", None)
            if join_queue_thread is not None:
                join_queue_thread()

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
        if Path(project.config_path).is_symlink():
            return {
                "project_id": project.project_id,
                "project_root": project.path,
                "config_path": project.config,
                "status": "invalid",
                "errors": ["Project config is a symlink and is not exposed through MCP resources."],
                "declared_figures": 0,
                "declared_diagrams": 0,
                "target_format": "",
            }
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
            return self._resolve_under_root(project_path, field_name="project_path")

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
        project_path = arguments.get("project_path")
        if isinstance(project_path, str) and project_path.strip():
            expanded_project_path = Path(project_path).expanduser()
            replacements.append((str(expanded_project_path), "input://project_path"))
            replacements.append((str(expanded_project_path.resolve()), "input://project_path"))

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

    def _mcp_project_jobs_root(self) -> Path:
        return self.runtime_root / "mcp_project_jobs"

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

    def _input_file_path(self, raw_path: Any) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("data_path is required.")
        path = self._resolve_allowed_data_path(raw_path, field_name="data_path")
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

    @classmethod
    def _project_figure_metadata(
        cls,
        output_path: Path,
        selected_figure: dict[str, Any],
        *,
        project_path: Path | None = None,
        figures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        width_px, height_px = cls._image_dimensions(output_path)
        aspect = round(width_px / height_px, 6) if width_px and height_px else None
        metadata = {
            "schema_version": "figure_metadata/1",
            "width_px": width_px,
            "height_px": height_px,
            "aspect": aspect,
            "layout_type": str(selected_figure.get("layout_type") or selected_figure.get("layout") or "").strip(),
        }
        metadata["canonical_check"] = cls._figure_canonical_check(metadata, selected_figure)
        metadata["family_check"] = cls._figure_family_check(metadata, selected_figure, project_path, figures or [])
        return metadata

    @staticmethod
    def _figure_metadata_warnings(figure_metadata: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        for key in ("canonical_check", "family_check"):
            check = figure_metadata.get(key)
            if not isinstance(check, dict):
                continue
            raw_warnings = check.get("warnings")
            if isinstance(raw_warnings, list):
                warnings.extend(str(item) for item in raw_warnings if str(item).strip())
        return warnings

    @staticmethod
    def _image_dimensions(output_path: Path) -> tuple[int | None, int | None]:
        candidates = [output_path, *sorted(output_path.parent.glob(f"{output_path.stem}.*"))]
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                from PIL import Image

                with Image.open(candidate) as image:
                    width, height = image.size
                    return int(width), int(height)
            except Exception:
                if candidate.suffix.lower() == ".svg":
                    svg_width, svg_height = GraphHubMCPServer._svg_dimensions(candidate)
                    if svg_width is not None and svg_height is not None:
                        return svg_width, svg_height
        return None, None

    @staticmethod
    def _svg_dimensions(path: Path) -> tuple[int | None, int | None]:
        try:
            root = ElementTree.parse(path).getroot()
        except Exception:
            return None, None

        def parse_length(value: Any) -> float | None:
            match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", str(value or ""))
            return float(match.group(1)) if match else None

        width = parse_length(root.attrib.get("width"))
        height = parse_length(root.attrib.get("height"))
        if width is None or height is None:
            view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
            parts = [float(part) for part in re.findall(r"[-+]?(?:\d*\.\d+|\d+)", str(view_box or ""))]
            if len(parts) == 4:
                width = width if width is not None else parts[2]
                height = height if height is not None else parts[3]
        if width is None or height is None:
            return None, None
        return int(round(width)), int(round(height))

    @classmethod
    def _figure_canonical_check(
        cls,
        metadata: dict[str, Any],
        selected_figure: dict[str, Any],
    ) -> dict[str, Any]:
        canonical = selected_figure.get("canonical")
        if canonical is None:
            canonical = {}
        if not isinstance(canonical, dict):
            canonical = {}
        expected = cls._canonical_expectations(selected_figure, canonical)
        warnings: list[str] = list(expected.get("warnings", []))
        tolerance = expected["dimension_tolerance_px"]
        width_px = metadata.get("width_px")
        height_px = metadata.get("height_px")
        expected_width = expected.get("width_px")
        expected_height = expected.get("height_px")
        expected_layout = str(expected.get("layout_type") or "").strip()
        actual_layout = str(metadata.get("layout_type") or "").strip()

        if expected_layout and actual_layout and actual_layout != expected_layout:
            warnings.append(f"figure canonical mismatch: layout_type {actual_layout!r} != expected {expected_layout!r}")
        if isinstance(width_px, int) and isinstance(expected_width, int) and abs(width_px - expected_width) > tolerance:
            warnings.append(
                f"figure canonical mismatch: width_px {width_px} != expected {expected_width} (tolerance {tolerance}px)"
            )
        if (
            isinstance(height_px, int)
            and isinstance(expected_height, int)
            and abs(height_px - expected_height) > tolerance
        ):
            warnings.append(
                f"figure canonical mismatch: height_px {height_px} != expected {expected_height} "
                f"(tolerance {tolerance}px)"
            )
        declared_dimensions = expected.get("declared_width") or expected.get("declared_height")
        if declared_dimensions and (width_px is None or height_px is None):
            warnings.append("figure canonical check could not inspect rendered dimensions")
        return {
            "passed": len(warnings) == 0,
            "expected": expected,
            "warnings": warnings,
        }

    @staticmethod
    def _canonical_expectations(
        selected_figure: dict[str, Any],
        canonical: dict[str, Any],
    ) -> dict[str, Any]:
        expected_dims = canonical.get("expected_dims") or canonical.get("dims") or canonical.get("dimensions")
        expected_width = canonical.get("width_px", selected_figure.get("expected_width_px"))
        expected_height = canonical.get("height_px", selected_figure.get("expected_height_px"))
        warnings: list[str] = []
        allowed_keys = {
            "expected_dims",
            "dims",
            "dimensions",
            "width_px",
            "height_px",
            "layout_type",
            "dimension_tolerance_px",
            "family_dimension_tolerance_px",
            "match_family",
        }
        for key in sorted(str(item) for item in canonical.keys() if str(item) not in allowed_keys):
            warnings.append(f"figure canonical config warning: unknown key {key!r}")
        if isinstance(expected_dims, (list, tuple)) and len(expected_dims) >= 2:
            expected_width = expected_dims[0]
            expected_height = expected_dims[1]
        elif expected_dims is not None:
            warnings.append("figure canonical config warning: expected_dims must contain width and height")
        tolerance = canonical.get("dimension_tolerance_px", selected_figure.get("dimension_tolerance_px", 8))
        try:
            tolerance_px = max(0, int(tolerance))
        except (TypeError, ValueError):
            tolerance_px = 8
            warnings.append("figure canonical config warning: dimension_tolerance_px must be an integer")
        family_tolerance = canonical.get(
            "family_dimension_tolerance_px",
            selected_figure.get("family_dimension_tolerance_px", 8),
        )
        try:
            family_tolerance_px = max(0, int(family_tolerance))
        except (TypeError, ValueError):
            family_tolerance_px = 8
            warnings.append("figure canonical config warning: family_dimension_tolerance_px must be an integer")

        def optional_int(value: Any, field_name: str) -> int | None:
            if isinstance(value, bool) or value is None:
                if isinstance(value, bool):
                    warnings.append(f"figure canonical config warning: {field_name} must be an integer")
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                warnings.append(f"figure canonical config warning: {field_name} must be an integer")
                return None

        return {
            "layout_type": str(
                canonical.get("layout_type") or selected_figure.get("expected_layout_type") or ""
            ).strip(),
            "width_px": optional_int(expected_width, "width_px"),
            "height_px": optional_int(expected_height, "height_px"),
            "declared_width": expected_width is not None,
            "declared_height": expected_height is not None,
            "dimension_tolerance_px": tolerance_px,
            "family_dimension_tolerance_px": family_tolerance_px,
            "match_family": str(canonical.get("match_family") or selected_figure.get("match_family") or "").strip(),
            "warnings": warnings,
        }

    @classmethod
    def _figure_family_check(
        cls,
        metadata: dict[str, Any],
        selected_figure: dict[str, Any],
        project_path: Path | None,
        figures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        expected = metadata.get("canonical_check", {}).get("expected", {})
        family_pattern = str(expected.get("match_family") or "").strip() if isinstance(expected, dict) else ""
        selected_output = str(selected_figure.get("output") or "")
        try:
            selected_output_parent = cls._project_relative_path(selected_output, "figures[].output").parent
        except ValueError:
            return {"passed": True, "family": family_pattern, "siblings": [], "warnings": []}
        family = family_pattern or cls._figure_family_key(
            str(selected_figure.get("id") or ""),
            output_parent=selected_output_parent.as_posix(),
        )
        if not family or project_path is None:
            return {"passed": True, "family": family, "siblings": [], "warnings": []}

        siblings: list[dict[str, Any]] = []
        tolerance = int(metadata.get("canonical_check", {}).get("expected", {}).get("family_dimension_tolerance_px", 8))
        width_px = metadata.get("width_px")
        height_px = metadata.get("height_px")
        for figure in figures:
            if figure is selected_figure:
                continue
            sibling_id = str(figure.get("id") or "")
            try:
                sibling_rel = cls._project_relative_path(figure.get("output"), "figures[].output")
            except ValueError:
                continue
            sibling_matches = (
                fnmatch.fnmatch(sibling_id, family_pattern)
                if family_pattern
                else cls._figure_family_key(sibling_id, output_parent=sibling_rel.parent.as_posix()) == family
            )
            if not sibling_matches:
                continue
            if sibling_rel.parent != selected_output_parent:
                continue
            sibling_width, sibling_height = cls._image_dimensions(project_path / sibling_rel)
            if sibling_width is None or sibling_height is None:
                continue
            siblings.append(
                {
                    "id": sibling_id,
                    "output": sibling_rel.as_posix(),
                    "width_px": sibling_width,
                    "height_px": sibling_height,
                    "layout_type": str(figure.get("layout_type") or figure.get("layout") or "").strip(),
                }
            )

        warnings: list[str] = []
        for sibling in siblings:
            if isinstance(width_px, int) and abs(width_px - int(sibling["width_px"])) > tolerance:
                warnings.append(
                    f"figure family sibling mismatch: {selected_figure.get('id')} width_px {width_px} "
                    f"differs from sibling {sibling['id']} width_px {sibling['width_px']}"
                )
            if isinstance(height_px, int) and abs(height_px - int(sibling["height_px"])) > tolerance:
                warnings.append(
                    f"figure family sibling mismatch: {selected_figure.get('id')} height_px {height_px} "
                    f"differs from sibling {sibling['id']} height_px {sibling['height_px']}"
                )
            actual_layout = str(metadata.get("layout_type") or "")
            sibling_layout = str(sibling.get("layout_type") or "")
            if actual_layout and sibling_layout and actual_layout != sibling_layout:
                warnings.append(
                    f"figure family sibling mismatch: {selected_figure.get('id')} layout_type {actual_layout!r} "
                    f"differs from sibling {sibling['id']} layout_type {sibling_layout!r}"
                )
        return {
            "passed": len(warnings) == 0,
            "family": family,
            "siblings": siblings,
            "warnings": warnings,
        }

    @staticmethod
    def _figure_family_key(figure_id: str, *, output_parent: str = "") -> str:
        text = figure_id.strip()
        if "_" not in text:
            return f"dir:{output_parent}" if output_parent else ""
        parts = [part for part in text.split("_") if part]
        if len(parts) < 3:
            return ""
        return "_".join(parts[1:])

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
        z_column: str,
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
                        "required_columns": [x_column, y_column, *([z_column] if z_column else [])],
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

    @classmethod
    def _visual_preflight_with_geometry_overlaps(
        cls,
        output_path: Path,
        target_format: str,
        geometry_diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        preflight = cls._safe_preflight(output_path, target_format)
        overlaps = cls._artist_overlaps_from_geometry(geometry_diagnostics)
        if overlaps:
            preflight = dict(preflight)
            preflight["overlaps"] = overlaps
            warnings = list(preflight.get("warnings") or [])
            warnings.append(f"artist_overlaps_detected:{len(overlaps)}")
            preflight["warnings"] = warnings
        return preflight

    @staticmethod
    def _artist_overlaps_from_geometry(geometry_diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
        checks = geometry_diagnostics.get("checks") if isinstance(geometry_diagnostics, dict) else None
        if not isinstance(checks, list):
            return []
        overlaps: list[dict[str, Any]] = []
        for check in checks:
            if not isinstance(check, dict) or check.get("name") != "artist_overlaps":
                continue
            data = check.get("data") if isinstance(check.get("data"), dict) else {}
            raw_overlaps = data.get("overlaps") if isinstance(data, dict) else []
            if not isinstance(raw_overlaps, list):
                continue
            for item in raw_overlaps:
                if isinstance(item, dict):
                    overlaps.append(
                        {
                            "axes": int(item.get("axes", data.get("axis_index", 0))),
                            "a": str(item.get("a", "")),
                            "b": str(item.get("b", "")),
                            "iou": float(item.get("iou", 0.0)),
                        }
                    )
        return overlaps


def run_stdio_server(
    server: GraphHubMCPServer | None = None,
    *,
    input_stream: Any | None = None,
    output_stream: Any | None = None,
) -> int:
    """Run a JSON-RPC stdio MCP server (newline-delimited or Content-Length framed)."""
    active_server = server or GraphHubMCPServer()
    in_stream = input_stream or sys.stdin.buffer
    out_stream = output_stream or sys.stdout.buffer

    while True:
        framing = "content-length"
        try:
            request, framing = _read_stdio_message(in_stream)
            if request is None:
                break
            response = _handle_json_rpc(active_server, request)
        except _StdioParseError as exc:
            framing = exc.framing
            response = _json_rpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc.error}")
        except json.JSONDecodeError as exc:
            response = _json_rpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}")
        except Exception as exc:
            response = _json_rpc_error(None, JSONRPC_INTERNAL_ERROR, str(exc))
        if response is not None:
            _write_stdio_message(out_stream, response, framing)
    return 0


def _handle_json_rpc(server: GraphHubMCPServer, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if "id" not in request:
        return None
    raw_params = request.get("params")
    if raw_params is None:
        params = {}
    elif isinstance(raw_params, dict):
        params = raw_params
    else:
        return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "JSON-RPC params must be an object when provided.")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
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
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": list_resource_definitions()}}
    if method == "resources/templates/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resourceTemplates": list_resource_templates()},
        }
    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Resource uri is required.")
        try:
            result = server.read_resource(uri)
        except ValueError as exc:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, str(exc))
        except FileNotFoundError as exc:
            return _json_rpc_error(request_id, JSONRPC_RESOURCE_NOT_FOUND, str(exc))
        except Exception as exc:
            return _json_rpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(exc))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": list_prompt_definitions()}}
    if method == "prompts/get":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Prompt name is required.")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Prompt arguments must be an object.")
        try:
            result = server.get_prompt(name.strip(), arguments)
        except ValueError as exc:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, str(exc))
        except FileNotFoundError as exc:
            return _json_rpc_error(request_id, JSONRPC_RESOURCE_NOT_FOUND, str(exc))
        except Exception as exc:
            return _json_rpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(exc))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
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
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type is None:
        return True
    return False


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class _StdioParseError(Exception):
    """Carries the detected framing so an error reply matches the client's wire format."""

    def __init__(self, error: ValueError, framing: str) -> None:
        super().__init__(str(error))
        self.error = error
        self.framing = framing


def _read_stdio_message(stream: Any) -> tuple[dict[str, Any] | None, str]:
    first_line = stream.readline()
    if first_line == b"" or first_line == "":
        return None, "content-length"
    if isinstance(first_line, str):
        first_line = first_line.encode("utf-8")

    if first_line.lstrip().startswith(b"{"):
        try:
            return json.loads(first_line.decode("utf-8")), "newline"
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _StdioParseError(exc, "newline") from exc

    headers = _read_headers(stream, first_line)
    content_length = headers.get("content-length")
    if content_length is None:
        raise ValueError("Missing Content-Length header.")
    try:
        expected_size = int(content_length)
    except ValueError as exc:
        raise ValueError(f"Invalid Content-Length header: {content_length}") from exc
    # Reject before reading: a negative size makes stream.read(-1) buffer the whole stream,
    # and an oversized size invites a single huge allocation — both memory-exhaustion DoS.
    if expected_size < 0 or expected_size > MCP_MAX_MESSAGE_BYTES:
        raise ValueError(f"Content-Length out of range: {expected_size} (allowed 0..{MCP_MAX_MESSAGE_BYTES}).")
    body = stream.read(expected_size)
    if isinstance(body, str):
        body = body.encode("utf-8")
    if len(body) != expected_size:
        raise ValueError(f"Incomplete MCP message body: expected {expected_size} bytes, got {len(body)}.")
    return json.loads(body.decode("utf-8")), "content-length"


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


def _write_stdio_message(stream: Any, response: dict[str, Any], framing: str = "content-length") -> None:
    body = json.dumps(response, ensure_ascii=False).encode("utf-8")
    if framing == "newline":
        payload = body + b"\n"
    else:
        payload = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    stream.write(payload)
    if hasattr(stream, "flush"):
        stream.flush()
