from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from .mcp.prompts import McpPromptsMixin
from .mcp.render_orchestration import McpRenderOrchestrationMixin
from .mcp.resources import McpResourcesMixin
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


class GraphHubMCPServer(
    McpReadToolsMixin,
    McpRenderToolsMixin,
    McpProjectToolsMixin,
    McpBatchToolsMixin,
    McpResourcesMixin,
    McpPromptsMixin,
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
