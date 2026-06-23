#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from hub_core.doctor import format_doctor_report, run_doctor
from hub_core.logging import configure_logging
from hub_core.mcp import GraphHubMCPServer, McpServerConfig, run_stdio_server


def _run_smoke(config: McpServerConfig) -> int:
    server = GraphHubMCPServer(config=config)
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


def _smoke_config(config: McpServerConfig) -> McpServerConfig:
    if config.research_root is not None or os.environ.get("PROJECT_ROOT"):
        return config
    hub_path = config.hub_path or Path(__file__).resolve().parent
    return config.overlay(research_root=hub_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="FigOps MCP stdio server")
    parser.add_argument("--smoke", action="store_true", help="Run a read-only MCP health/style smoke check")
    subparsers = parser.add_subparsers(dest="command")
    doctor_parser = subparsers.add_parser("doctor", help="Run a FigOps environment readiness check")
    doctor_parser.add_argument("--json", action="store_true", help="Emit structured doctor output for agents")
    parser.add_argument("--hub-path", help="Explicit FigOps repository path")
    parser.add_argument("--research-root", help="Explicit research/project discovery root")
    parser.add_argument("--runtime-root", help="Explicit MCP runtime root")
    parser.add_argument(
        "--enable-write-tools",
        action="store_true",
        help="Enable MCP tools that write files or execute render jobs",
    )
    args = parser.parse_args()
    configure_logging()
    config = McpServerConfig.from_env().overlay(
        hub_path=args.hub_path,
        research_root=args.research_root,
        runtime_root=args.runtime_root,
        write_tools_enabled=True if args.enable_write_tools else None,
    )
    if args.smoke:
        return _run_smoke(_smoke_config(config))
    if args.command == "doctor":
        report = run_doctor(config)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(format_doctor_report(report))
        return 0 if report["ready"] else 1
    return run_stdio_server(GraphHubMCPServer(config=config, require_initialize=True))


if __name__ == "__main__":
    raise SystemExit(main())
