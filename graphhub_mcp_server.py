#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from hub_core.mcp_surface import GraphHubMCPServer, run_stdio_server


def _run_smoke() -> int:
    server = GraphHubMCPServer()
    health = server.call_tool("graphhub.health", {})["structuredContent"]
    styles = server.call_tool("graphhub.list_styles", {})["structuredContent"]
    payload = {
        "status": "ok" if health.get("status") in {"ok", "warning"} and styles.get("status") == "ok" else "error",
        "health_status": health.get("status"),
        "style_format_count": styles.get("style_format_count") or len(styles.get("target_formats", [])),
        "tool_surface": "graphhub_mcp",
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Graph Hub MCP stdio server")
    parser.add_argument("--smoke", action="store_true", help="Run a read-only MCP health/style smoke check")
    args = parser.parse_args()
    if args.smoke:
        return _run_smoke()
    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())
