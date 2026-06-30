from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "FigOpsMCPServer": ("hub_core.mcp.server", "FigOpsMCPServer"),
    "GraphHubMCPServer": ("hub_core.mcp.server", "FigOpsMCPServer"),
    "McpServerConfig": ("hub_core.mcp.config", "McpServerConfig"),
    "list_tool_definitions": ("hub_core.mcp.schemas", "list_tool_definitions"),
    "run_stdio_server": ("hub_core.mcp.transport", "run_stdio_server"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'hub_core.mcp' has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})

__all__ = [
    "FigOpsMCPServer",
    "GraphHubMCPServer",
    "McpServerConfig",
    "list_tool_definitions",
    "run_stdio_server",
]
