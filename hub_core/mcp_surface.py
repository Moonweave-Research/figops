from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from .config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS, find_config_path, validate_config
from .project_discovery import ProjectDiscoveryService
from .utils import get_hub_path, get_research_root
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles

READ_ONLY_TOOL_NAMES = (
    "graphhub.health",
    "graphhub.list_styles",
    "graphhub.list_projects",
    "graphhub.inspect_project",
    "graphhub.validate_project",
)

JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_PARSE_ERROR = -32700


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
            "Return read-only Graph Hub server health and discovery status.",
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
        self.runtime_root = self._resolve_runtime_root(runtime_root)
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "graphhub.health": self.health,
            "graphhub.list_styles": self.list_styles,
            "graphhub.list_projects": self.list_projects,
            "graphhub.inspect_project": self.inspect_project,
            "graphhub.validate_project": self.validate_project,
        }

    @staticmethod
    def _resolve_runtime_root(runtime_root: str | os.PathLike | None = None) -> Path:
        if runtime_root:
            return Path(runtime_root).expanduser().resolve()
        override = os.environ.get("RESEARCH_HUB_RUNTIME_ROOT") or os.environ.get("RESEARCH_HUB_RUNTIME_HOME")
        if override:
            return Path(override).expanduser().resolve()
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        elif os.name == "posix" and hasattr(os, "uname") and os.uname().sysname == "Darwin":
            base = str(Path.home() / "Library" / "Caches")
        else:
            base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        return (Path(base) / "Graph_making_hub").expanduser().resolve()

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
            summary="Graph Hub read-only MCP surface is available.",
            warnings=warnings,
            hub_path=str(self.hub_path),
            version=self._read_version(),
            python_executable=sys.executable,
            runtime_root=str(self.runtime_root),
            style_format_count=len(ALLOWED_TARGET_FORMATS),
            discovery_status=discovery,
            write_tools_enabled=False,
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
        **extra: Any,
    ) -> dict[str, Any]:
        operation_id = self._operation_id(tool_name, arguments)
        result = {
            "status": status,
            "operation_id": operation_id,
            "is_dry_run": True,
            "summary": summary,
            "created_paths": created_paths or [],
            "modified_paths": modified_paths or [],
            "skipped_paths": skipped_paths or [],
            "artifact_resources": artifact_resources or [],
            "warnings": warnings or [],
            "errors": errors or [],
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
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str) or tool_name not in server._handlers:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Tool arguments must be an object.")
        return {"jsonrpc": "2.0", "id": request_id, "result": server.call_tool(tool_name, arguments)}
    return _json_rpc_error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")


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
