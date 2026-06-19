from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_ADAPTER_SECURITY_ENV_VARS = frozenset(
    {
        "ATHENA_PATH",
        "GRAPH_HUB_ATHENA_ADAPTER",
        "GRAPH_HUB_CONVENTIONS_ADAPTER",
        "GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS",
        "GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES",
        "GRAPH_HUB_MCP_STRICT_ROOTS",
        "GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED",
        "GRAPH_HUB_PREFETCH_ADAPTER",
        "PROJECT_ROOT",
        "RESEARCH_HUB_PATH",
        "RESEARCH_HUB_RUNTIME_HOME",
        "RESEARCH_HUB_RUNTIME_ROOT",
    }
)


@dataclass(frozen=True)
class McpServerConfig:
    hub_path: str | os.PathLike | None = None
    research_root: str | os.PathLike | None = None
    runtime_root: str | os.PathLike | None = None
    write_tools_enabled: bool | None = None
    allowed_data_roots: tuple[str | os.PathLike, ...] = ()
    strict_roots: bool | None = None

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None) -> McpServerConfig:
        if values is None:
            return cls()
        if not isinstance(values, dict):
            raise TypeError("MCP server config must be a mapping.")

        allowed_data_roots = values.get("allowed_data_roots", ())
        if allowed_data_roots is None:
            allowed_data_roots = ()
        if isinstance(allowed_data_roots, (str, os.PathLike)):
            allowed_data_roots = (allowed_data_roots,)
        if not isinstance(allowed_data_roots, (list, tuple)):
            raise TypeError("MCP server config allowed_data_roots must be a list or tuple.")
        write_tools_enabled = values.get("write_tools_enabled")
        if write_tools_enabled is not None and not isinstance(write_tools_enabled, bool):
            raise TypeError("MCP server config write_tools_enabled must be a boolean.")
        strict_roots = values.get("strict_roots")
        if strict_roots is not None and not isinstance(strict_roots, bool):
            raise TypeError("MCP server config strict_roots must be a boolean.")

        return cls(
            hub_path=values.get("hub_path"),
            research_root=values.get("research_root"),
            runtime_root=values.get("runtime_root"),
            write_tools_enabled=write_tools_enabled,
            allowed_data_roots=tuple(allowed_data_roots),
            strict_roots=strict_roots,
        )

    @classmethod
    def from_env(cls) -> McpServerConfig:
        runtime_root = os.environ.get("RESEARCH_HUB_RUNTIME_ROOT") or os.environ.get("RESEARCH_HUB_RUNTIME_HOME")
        allowed_data_roots = tuple(
            item.strip()
            for item in os.environ.get("GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS", "").split(os.pathsep)
            if item.strip()
        )
        return cls(
            hub_path=os.environ.get("RESEARCH_HUB_PATH"),
            research_root=os.environ.get("PROJECT_ROOT"),
            runtime_root=runtime_root,
            write_tools_enabled=_env_bool("GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED"),
            allowed_data_roots=allowed_data_roots,
            strict_roots=_env_bool("GRAPH_HUB_MCP_STRICT_ROOTS"),
        )

    def overlay(self, **overrides: Any) -> McpServerConfig:
        values = {
            "hub_path": self.hub_path,
            "research_root": self.research_root,
            "runtime_root": self.runtime_root,
            "write_tools_enabled": self.write_tools_enabled,
            "allowed_data_roots": self.allowed_data_roots,
            "strict_roots": self.strict_roots,
        }
        for key, value in overrides.items():
            if value is not None:
                values[key] = value
        return McpServerConfig(**values)

    def explicit_runtime_root(self) -> bool:
        return self.runtime_root is not None


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def normalize_allowed_root(raw_root: str | os.PathLike) -> Path:
    return Path(raw_root).expanduser()
