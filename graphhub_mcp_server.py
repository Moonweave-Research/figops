#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

from hub_core.approval_authority import ApprovalAuthorityRoot
from hub_core.doctor import format_doctor_report, run_doctor
from hub_core.logging import configure_logging
from hub_core.mcp.config import McpServerConfig

if TYPE_CHECKING:
    from hub_core.mcp import FigOpsMCPServer


def _build_production_server(
    config: McpServerConfig,
    *,
    host_authority_root: ApprovalAuthorityRoot | None = None,
    **server_kwargs: Any,
) -> "FigOpsMCPServer":
    from hub_core.mcp import FigOpsMCPServer

    if host_authority_root is not None and not isinstance(host_authority_root, ApprovalAuthorityRoot):
        raise TypeError("host_authority_root must be an ApprovalAuthorityRoot.")
    trusted_root = host_authority_root if host_authority_root is not None else ApprovalAuthorityRoot()
    return FigOpsMCPServer(
        config=config,
        require_host_approval=True,
        host_authority_root=trusted_root,
        **server_kwargs,
    )


def build_trusted_figops_mcp_server(
    *,
    config: McpServerConfig,
    host_authority_root: ApprovalAuthorityRoot | None = None,
    **server_kwargs: Any,
) -> "FigOpsMCPServer":
    return _build_production_server(
        config,
        host_authority_root=host_authority_root,
        **server_kwargs,
    )


def _run_smoke(config: McpServerConfig) -> int:
    doctor_report = run_doctor(config)
    runtime_dependency_check = next(
        (check for check in doctor_report.get("checks", []) if check.get("name") == "runtime_dependencies"),
        None,
    )
    if runtime_dependency_check and runtime_dependency_check.get("status") == "error":
        payload = {
            "status": "error",
            "ready": False,
            "tool_surface": "figops_mcp",
            "check": runtime_dependency_check,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1

    server = _build_production_server(config)
    health = server.call_tool("figops.health", {})["structuredContent"]
    styles = server.call_tool("figops.list_styles", {})["structuredContent"]
    payload = {
        "status": "ok" if health.get("status") in {"ok", "warning"} and styles.get("status") == "ok" else "error",
        "health_status": health.get("status"),
        "style_format_count": styles.get("style_format_count") or len(styles.get("target_formats", [])),
        "tool_surface": "figops_mcp",
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


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
        "--surface-profile",
        choices=("v2", "compatibility"),
        help="MCP discovery surface (default: v2; compatibility exposes the frozen legacy contract)",
    )
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
        surface_profile=args.surface_profile,
    )
    if args.smoke:
        return _run_smoke(config)
    if args.command == "doctor":
        report = run_doctor(config)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(format_doctor_report(report))
        return 0 if report["ready"] else 1
    from hub_core.mcp import run_stdio_server

    return run_stdio_server(_build_production_server(config, require_initialize=True))


if __name__ == "__main__":
    raise SystemExit(main())
