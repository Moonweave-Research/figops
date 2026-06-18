from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import yaml

from themes.style_packs import list_style_packs
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles

from .config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS
from .mcp.render_orchestration import McpRenderOrchestrationMixin
from .mcp.schemas import (
    get_tool_handlers,
)
from .mcp.schemas import (
    list_prompt_definitions as schema_list_prompt_definitions,
)
from .mcp.schemas import (
    list_resource_definitions as schema_list_resource_definitions,
)
from .mcp.schemas import (
    list_resource_templates as schema_list_resource_templates,
)
from .mcp.schemas import (
    list_tool_definitions as schema_list_tool_definitions,
)
from .mcp.security import McpSecurityMixin, is_write_tool_name
from .mcp.tools.batch_tools import McpBatchToolsMixin
from .mcp.tools.project_tools import McpProjectToolsMixin
from .mcp.tools.read_tools import McpReadToolsMixin
from .mcp.tools.render_tools import McpRenderToolsMixin
from .project_discovery import ProjectDiscoveryService

_STRICT_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

































class GraphHubMCPServer(
    McpReadToolsMixin,
    McpRenderToolsMixin,
    McpProjectToolsMixin,
    McpBatchToolsMixin,
    McpRenderOrchestrationMixin,
    McpSecurityMixin,
):
    """Dependency-free MCP surface over Graph Hub core contracts."""

    def __init__(
        self,
        *,
        hub_path: str | os.PathLike | None = None,
        research_root: str | os.PathLike | None = None,
        runtime_root: str | os.PathLike | None = None,
        write_tools_enabled: bool | None = None,
        require_initialize: bool = False,
    ) -> None:
        self.require_initialize = require_initialize
        self.initialized = False
        self._init_security_state(
            hub_path=hub_path,
            research_root=research_root,
            runtime_root=runtime_root,
            write_tools_enabled=write_tools_enabled,
        )
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = get_tool_handlers(self)

    @staticmethod
    def list_tool_definitions() -> list[dict[str, Any]]:
        return schema_list_tool_definitions()

    @staticmethod
    def list_resource_definitions() -> list[dict[str, str]]:
        return schema_list_resource_definitions()

    @staticmethod
    def list_resource_templates() -> list[dict[str, str]]:
        return schema_list_resource_templates()

    @staticmethod
    def list_prompt_definitions() -> list[dict[str, Any]]:
        return schema_list_prompt_definitions()

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown Graph Hub MCP tool: {name}")
        if is_write_tool_name(name) and not self.write_tools_enabled:
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
                "2. Call graphhub.normalize_project_structure with dry_run=true.\n"
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
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()



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




    def _read_version(self) -> str:
        pyproject = self.hub_path / "pyproject.toml"
        try:
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            return "unknown"
        return "unknown"











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
