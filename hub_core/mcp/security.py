from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hub_core.mcp.config import McpServerConfig, normalize_allowed_root
from hub_core.project_discovery import ProjectDiscoveryService
from hub_core.runtime_paths import preview_runtime_root, resolve_runtime_root
from hub_core.utils import get_hub_path, get_research_root

WRITE_TOOL_NAMES = (
    "graphhub.render_csv_graph",
    "graphhub.render_project_figure",
    "graphhub.scaffold_project",
    "graphhub.normalize_project_structure",
    "graphhub.batch_check",
)


def is_write_tool_name(name: str) -> bool:
    return name in WRITE_TOOL_NAMES


class McpSecurityMixin:
    hub_path: Path
    research_root: Path
    runtime_root: Path
    _runtime_root_explicit: bool
    security_warnings: list[str]
    allowed_data_roots: tuple[Path, ...]
    write_tools_enabled: bool

    def _init_security_state(
        self,
        *,
        config: McpServerConfig | dict[str, Any] | None,
        hub_path: str | os.PathLike | None,
        research_root: str | os.PathLike | None,
        runtime_root: str | os.PathLike | None,
        write_tools_enabled: bool | None,
    ) -> None:
        server_config = self._resolve_server_config(
            config,
            hub_path=hub_path,
            research_root=research_root,
            runtime_root=runtime_root,
            write_tools_enabled=write_tools_enabled,
        )
        self.hub_path = Path(server_config.hub_path or get_hub_path()).expanduser().resolve()
        self.research_root = Path(server_config.research_root or get_research_root()).expanduser().resolve()
        self._runtime_root_explicit = server_config.explicit_runtime_root()
        self.runtime_root = self._resolve_runtime_root(server_config.runtime_root)
        self.security_warnings = []
        self._configured_allowed_data_roots = server_config.allowed_data_roots
        self._strict_roots = bool(server_config.strict_roots)
        self.allowed_data_roots = self._allowed_data_roots()
        self.write_tools_enabled = self._resolve_write_tools_enabled(server_config.write_tools_enabled)

    @staticmethod
    def _resolve_server_config(
        config: McpServerConfig | dict[str, Any] | None,
        *,
        hub_path: str | os.PathLike | None,
        research_root: str | os.PathLike | None,
        runtime_root: str | os.PathLike | None,
        write_tools_enabled: bool | None,
    ) -> McpServerConfig:
        if config is None:
            server_config = McpServerConfig.from_env()
        elif isinstance(config, McpServerConfig):
            server_config = config
        else:
            server_config = McpServerConfig.from_mapping(config)
        return server_config.overlay(
            hub_path=hub_path,
            research_root=research_root,
            runtime_root=runtime_root,
            write_tools_enabled=write_tools_enabled,
        )

    @staticmethod
    def _resolve_runtime_root(runtime_root: str | os.PathLike | None = None) -> Path:
        if runtime_root:
            return Path(runtime_root).expanduser().resolve()
        return Path(preview_runtime_root()).expanduser().resolve()

    @staticmethod
    def _resolve_write_tools_enabled(write_tools_enabled: bool | None) -> bool:
        if write_tools_enabled is not None:
            return bool(write_tools_enabled)
        # Fail closed: write/exec tools require explicit opt-in via config, constructor, or env config source.
        return False

    def _allowed_data_roots(self) -> tuple[Path, ...]:
        roots = [self.research_root, self.runtime_root]
        for item in self._configured_allowed_data_roots:
            extra = normalize_allowed_root(item)
            stripped = str(item)
            if not extra.is_absolute():
                self.security_warnings.append(f"Skipped allowed data root because it is not absolute: {stripped}")
                continue
            resolved = extra.resolve()
            if not resolved.is_dir():
                self.security_warnings.append(
                    f"Skipped allowed data root because it does not exist as a directory: {resolved}"
                )
                continue
            broad_warning = self._broad_data_root_warning(resolved)
            if broad_warning:
                if self._strict_roots:
                    self.security_warnings.append(f"refused broad data root: {resolved}")
                    continue
                self.security_warnings.append(broad_warning)
            roots.append(resolved)
        deduped: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root)
            if key not in seen:
                seen.add(key)
                deduped.append(root)
        return tuple(deduped)

    @staticmethod
    def _broad_data_root_warning(root: Path) -> str:
        if root == Path(root.anchor):
            return f"Configured broad data root allows the filesystem root: {root}"
        home = Path.home().resolve()
        if root == home:
            return f"Configured broad data root allows the current user's home directory: {root}"
        if os.name == "nt" and root.anchor and root == Path(root.anchor).resolve():
            return f"Configured broad data root allows the drive root: {root}"
        return ""

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

    def _activate_runtime_root_for_runtime_access(self) -> None:
        if not self._runtime_root_explicit:
            self.runtime_root = Path(resolve_runtime_root()).expanduser().resolve()
            self.allowed_data_roots = self._allowed_data_roots()

    def _scan_root(self, arguments: dict[str, Any]) -> Path:
        root = arguments.get("root")
        if root:
            return self._resolve_under_root(root, field_name="root")
        return self.research_root

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
