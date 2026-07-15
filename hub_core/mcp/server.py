from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from hub_core.redaction import redact_secrets, redact_text

from .config import McpServerConfig
from .errors import infer_tool_error_entry, taxonomy_data, taxonomy_entry_for_exception
from .prompts import McpPromptsMixin
from .render_orchestration import McpRenderOrchestrationMixin
from .resources import McpResourcesMixin
from .schemas import (
    get_tool_handlers,
)
from .schemas import (
    list_prompt_definitions as schema_list_prompt_definitions,
)
from .schemas import (
    list_resource_definitions as schema_list_resource_definitions,
)
from .schemas import (
    list_resource_templates as schema_list_resource_templates,
)
from .schemas import (
    list_tool_definitions as schema_list_tool_definitions,
)
from .security import McpSecurityMixin
from .surface_profiles import normalize_surface_profile
from .tools.audit_tools import McpAuditToolsMixin
from .tools.batch_tools import McpBatchToolsMixin
from .tools.data_tools import McpDataToolsMixin
from .tools.project_tools import McpProjectToolsMixin
from .tools.read_tools import McpReadToolsMixin
from .tools.readiness_tools import McpReadinessToolsMixin
from .tools.render_csv import McpRenderCsvMixin
from .tools.render_project import McpRenderProjectMixin
from .tools.render_tools import McpRenderToolsMixin
from .tools.render_v2 import McpRenderV2Mixin
from .tools.render_validation import McpRenderValidationMixin


class FigOpsMCPServer(
    McpDataToolsMixin,
    McpAuditToolsMixin,
    McpRenderV2Mixin,
    McpReadToolsMixin,
    McpReadinessToolsMixin,
    McpRenderToolsMixin,
    McpRenderProjectMixin,
    McpRenderCsvMixin,
    McpRenderValidationMixin,
    McpProjectToolsMixin,
    McpBatchToolsMixin,
    McpResourcesMixin,
    McpPromptsMixin,
    McpRenderOrchestrationMixin,
    McpSecurityMixin,
):
    """Dependency-free MCP surface over FigOps core contracts."""

    def __init__(
        self,
        *,
        config: McpServerConfig | dict[str, Any] | None = None,
        hub_path: str | os.PathLike | None = None,
        research_root: str | os.PathLike | None = None,
        runtime_root: str | os.PathLike | None = None,
        write_tools_enabled: bool | None = None,
        surface_profile: str | None = None,
        require_initialize: bool = False,
    ) -> None:
        self.require_initialize = require_initialize
        self.initialized = False
        if config is None:
            resolved_config = McpServerConfig.from_env()
        elif isinstance(config, McpServerConfig):
            resolved_config = config
        else:
            resolved_config = McpServerConfig.from_mapping(config)
        resolved_config = resolved_config.overlay(surface_profile=surface_profile)
        self.surface_profile = normalize_surface_profile(resolved_config.surface_profile)
        self._init_security_state(
            config=resolved_config,
            hub_path=hub_path,
            research_root=research_root,
            runtime_root=runtime_root,
            write_tools_enabled=write_tools_enabled,
        )
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = get_tool_handlers(self)

    def list_tool_definitions(self) -> list[dict[str, Any]]:
        return schema_list_tool_definitions(
            profile=self.surface_profile,
            write_tools_enabled=self.write_tools_enabled,
        )

    @staticmethod
    def list_resource_definitions() -> list[dict[str, str]]:
        return schema_list_resource_definitions()

    @staticmethod
    def list_resource_templates() -> list[dict[str, str]]:
        return schema_list_resource_templates()

    def list_prompt_definitions(self) -> list[dict[str, Any]]:
        definitions = schema_list_prompt_definitions()
        if self.surface_profile == "v2":
            allowed = {"make_publication_graph_from_csv", "render_project_figure"}
            return [definition for definition in definitions if definition["name"] in allowed]
        return definitions

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown FigOps MCP tool: {name}")
        structured = self._authorize_write_tool(name, arguments)
        if structured is not None:
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, sort_keys=True)}],
                "structuredContent": structured,
                "isError": True,
            }

        try:
            structured = handler(arguments)
            is_error = structured.get("status") == "error"
        except Exception as exc:
            entry = taxonomy_entry_for_exception(exc)
            structured = self._envelope(
                name,
                arguments,
                status="error",
                summary=f"{name} failed.",
                errors=[redact_text(str(exc))],
                manual_review_needed=True,
                error_category=entry.category,
                error_code=getattr(exc, "code", None),
            )
            is_error = True

        return {
            "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, sort_keys=True)}],
            "structuredContent": structured,
            "isError": is_error,
        }

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
        error_category: str | None = None,
        error_code: str | None = None,
        jsonrpc_code: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        operation_id = self._operation_id(tool_name, arguments)
        script_output = extra.pop("script_output", None)
        redacted_extra = redact_secrets(extra)
        public_extra = (
            self._sanitize_public_payload(redacted_extra, arguments)
            if status == "error" and tool_name == "figops.render_project_figure"
            else redacted_extra
        )
        if not isinstance(public_extra, dict):
            raise RuntimeError("MCP envelope extras must be a mapping.")
        result = {
            "status": status,
            "operation_id": operation_id,
            "is_dry_run": is_dry_run,
            "summary": summary,
            "created_paths": created_paths or [],
            "modified_paths": modified_paths or [],
            "skipped_paths": skipped_paths or [],
            "artifact_resources": artifact_resources or [],
            "warnings": [
                self._sanitize_diagnostic_text(redact_text(str(warning)), arguments)
                for warning in (warnings or [])
            ],
            "errors": [
                self._sanitize_diagnostic_text(redact_text(str(error)), arguments) for error in (errors or [])
            ],
            "script_output": [
                self._sanitize_diagnostic_text(redact_text(str(line)), arguments) for line in (script_output or [])
            ],
            "manual_review_needed": manual_review_needed,
        }
        if status == "error":
            entry = infer_tool_error_entry(
                error_category=error_category,
            failure_stage=public_extra.get("failure_stage"),
                errors=result["errors"],
            )
            data = taxonomy_data(entry)
            result["error_category"] = data["category"]
            result["error_code"] = error_code or str(data["code"])
            result["jsonrpc_code"] = jsonrpc_code if jsonrpc_code is not None else int(data["jsonrpc_code"])
        elif error_category or error_code or jsonrpc_code is not None:
            entry = infer_tool_error_entry(error_category=error_category)
            data = taxonomy_data(entry)
            result["error_category"] = data["category"]
            result["error_code"] = error_code or str(data["code"])
            result["jsonrpc_code"] = jsonrpc_code if jsonrpc_code is not None else int(data["jsonrpc_code"])
        result.update(public_extra)
        return result

    def _sanitize_public_payload(self, value: object, arguments: dict[str, Any]) -> object:
        """Recursively sanitize nested envelope extras without changing their JSON shape."""
        if isinstance(value, dict):
            return {str(key): self._sanitize_public_payload(item, arguments) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_public_payload(item, arguments) for item in value]
        if isinstance(value, str):
            return self._sanitize_diagnostic_text(redact_text(value), arguments)
        return value

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
            if os.altsep:
                sanitized = sanitized.replace(f"{root_text}{os.altsep}", child_label)
            token_pattern = re.compile(rf"(?<![\w.-]){re.escape(root_text)}(?![\w.-])")
            sanitized = token_pattern.sub(label, sanitized)
        return self._normalize_sanitized_uris(sanitized)

    @staticmethod
    def _normalize_sanitized_uris(text: str) -> str:
        labels = ("runtime://", "research://", "hub://", "input://data_path", "input://project_path")
        for label in labels:
            pattern = re.compile(rf"{re.escape(label)}[^\s\"'<>)]*")
            text = pattern.sub(lambda match: match.group(0).replace("\\", "/"), text)
        return text

    def _diagnostic_path_replacements(self, arguments: dict[str, Any]) -> list[tuple[str, str]]:
        replacements = [
            (str(self.runtime_root), "runtime://"),
            (str(self.research_root), "research://"),
            (str(self.hub_path), "hub://"),
        ]
        data_path = arguments.get("data_path")
        if isinstance(data_path, str) and data_path.strip():
            expanded_path = Path(data_path).expanduser()
            if expanded_path.is_absolute():
                replacements.append((str(expanded_path), "input://data_path"))
            replacements.append((str(expanded_path.resolve()), "input://data_path"))
        project_path = arguments.get("project_path")
        if isinstance(project_path, str) and project_path.strip():
            expanded_project_path = Path(project_path).expanduser()
            if expanded_project_path.is_absolute():
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


class GraphHubMCPServer(FigOpsMCPServer):
    """Historical Python class name selecting the compatibility profile."""

    def __init__(self, **kwargs: Any) -> None:
        config = kwargs.get("config")
        configured_profile = (
            config.surface_profile
            if isinstance(config, McpServerConfig)
            else config.get("surface_profile") if isinstance(config, dict) else None
        )
        for requested_profile in (kwargs.get("surface_profile"), configured_profile):
            if requested_profile is not None and normalize_surface_profile(requested_profile) != "compatibility":
                raise ValueError("GraphHubMCPServer only supports surface_profile='compatibility'.")
        # Make the historical class deterministic even if the process env asks
        # the modern FigOps launcher for v2.
        kwargs["surface_profile"] = "compatibility"
        super().__init__(**kwargs)
