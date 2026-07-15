"""Thin read-only MCP adapter for bounded data inspection."""

from __future__ import annotations

import os
from typing import Any

from hub_core.allowed_data import resolve_inspect_max_bytes
from hub_core.data_inspection import inspect_allowed_data


class McpDataToolsMixin:
    """Expose one-shot facts without adding response-envelope context overhead."""

    def inspect_data(self, arguments: dict[str, Any]) -> dict[str, Any]:
        prefetch_mode = str(os.environ.get("GRAPH_HUB_PREFETCH_ADAPTER") or "none").strip().lower()
        if prefetch_mode == "noop":
            prefetch_mode = "noop"
        elif prefetch_mode == "gdrive":
            prefetch_mode = "gdrive"
        else:
            prefetch_mode = "none"
        return inspect_allowed_data(
            arguments.get("data_path"),
            allowed_roots=tuple(root for root in self.allowed_data_roots if root.is_dir()),
            relative_base=self.research_root,
            prefetch_mode=prefetch_mode,
            max_bytes=resolve_inspect_max_bytes(warnings=self.security_warnings),
            columns=arguments.get("columns"),
            include_samples=arguments.get("include_samples", False),
            sample_rows=arguments.get("sample_rows", 0),
        )


__all__ = ["McpDataToolsMixin"]
