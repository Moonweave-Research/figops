from __future__ import annotations

from typing import Any

from hub_core.mcp.tools.render_csv import McpRenderCsvMixin
from hub_core.mcp.tools.render_project import McpRenderProjectMixin
from hub_core.mcp.tools.render_support import McpRenderToolSupportMixin


class McpRenderToolsMixin(McpRenderToolSupportMixin):
    """Graph rendering MCP tool handler aggregator."""

    def render_csv_graph(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return McpRenderCsvMixin.render_csv_graph(self, arguments)

    def render_project_figure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return McpRenderProjectMixin.render_project_figure(self, arguments)
