from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from hub_core.adapters.selection import AdapterSelectionError, select_adapters
from hub_core.mcp import GraphHubMCPServer, McpServerConfig


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    summary: str
    hint: str = ""
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
        }
        if self.hint:
            payload["hint"] = self.hint
        if self.details:
            payload["details"] = self.details
        return payload


def run_doctor(config: McpServerConfig) -> dict[str, Any]:
    server = GraphHubMCPServer(config=config)
    checks = [
        _check_python(),
        _check_uv(),
        _check_optional_io_dependency("pyarrow", "Parquet/Feather support", "uv sync --extra io"),
        _check_optional_io_dependency("tables", "HDF5 support", "uv sync --extra io"),
        _check_rscript(),
        _check_write_tools(server),
        _check_roots(server),
        _check_adapters(),
    ]
    if any(check.status == "error" for check in checks):
        status = "error"
    elif any(check.status == "warning" for check in checks):
        status = "warning"
    else:
        status = "ok"
    return {
        "status": status,
        "ready": status != "error",
        "summary": _summary_for(status),
        "checks": [check.to_dict() for check in checks],
    }


def format_doctor_report(report: dict[str, Any]) -> str:
    lines = [
        f"Graph Hub doctor: {report['status']}",
        report["summary"],
        "",
    ]
    for check in report["checks"]:
        marker = {"ok": "OK", "warning": "WARN", "error": "ERROR"}.get(check["status"], check["status"].upper())
        lines.append(f"[{marker}] {check['name']}: {check['summary']}")
        hint = check.get("hint")
        if hint:
            lines.append(f"  Hint: {hint}")
        details = check.get("details")
        if details:
            for key, value in details.items():
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _summary_for(status: str) -> str:
    if status == "ok":
        return "Environment is ready for Graph Hub MCP discovery and rendering."
    if status == "warning":
        return "Environment is usable, but optional or workflow-specific capabilities are missing."
    return "Environment has blocking configuration errors that must be fixed before reliable use."


def _check_python() -> DoctorCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 12):
        return DoctorCheck(
            "python",
            "error",
            f"Python {version} is below the required 3.12 runtime.",
            "Run with `uv run python ...` using Python 3.12 or newer.",
            {"executable": sys.executable, "version": version},
        )
    return DoctorCheck("python", "ok", f"Python {version} is supported.", details={"executable": sys.executable})


def _check_uv() -> DoctorCheck:
    uv_path = shutil.which("uv")
    if not uv_path:
        return DoctorCheck(
            "uv",
            "error",
            "uv is not available on PATH.",
            "Install uv and run commands through `uv run` / `uv sync`.",
        )
    completed = subprocess.run([uv_path, "--version"], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return DoctorCheck(
            "uv",
            "error",
            "`uv --version` failed.",
            "Reinstall uv or fix PATH so the uv executable can run.",
            {"path": uv_path, "stderr": completed.stderr.strip()},
        )
    return DoctorCheck("uv", "ok", completed.stdout.strip() or "uv is available.", details={"path": uv_path})


def _check_optional_io_dependency(module_name: str, purpose: str, install_hint: str) -> DoctorCheck:
    if importlib.util.find_spec(module_name):
        return DoctorCheck(module_name, "ok", f"{module_name} is installed for {purpose}.")
    return DoctorCheck(
        module_name,
        "warning",
        f"{module_name} is missing; {purpose} is unavailable.",
        f"Install optional I/O dependencies with `{install_hint}`.",
    )


def _check_rscript() -> DoctorCheck:
    rscript = shutil.which("Rscript")
    if not rscript:
        return DoctorCheck(
            "Rscript",
            "warning",
            "Rscript is not available on PATH; R analysis steps cannot run.",
            "Install R, for example `brew install r` on macOS, then rerun doctor.",
        )
    completed = subprocess.run([rscript, "--version"], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return DoctorCheck(
            "Rscript",
            "error",
            "`Rscript --version` failed.",
            "Fix the R installation or remove the broken Rscript from PATH.",
            {"path": rscript, "stderr": completed.stderr.strip()},
        )
    version = (completed.stderr or completed.stdout).strip()
    return DoctorCheck("Rscript", "ok", version or "Rscript is available.", details={"path": rscript})


def _check_write_tools(server: GraphHubMCPServer) -> DoctorCheck:
    if server.write_tools_enabled:
        return DoctorCheck(
            "write_tools",
            "ok",
            "MCP write/render tools are enabled (not execution-verified).",
            details={"enabled": True},
        )
    return DoctorCheck(
        "write_tools",
        "warning",
        "MCP write/render tools are disabled by default.",
        "Set GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED=1 or pass --enable-write-tools when rendering is intended.",
        {"enabled": False},
    )


def _check_roots(server: GraphHubMCPServer) -> DoctorCheck:
    details = {
        "hub_path": str(server.hub_path),
        "research_root": str(server.research_root),
        "runtime_root": str(server.runtime_root),
        "allowed_data_roots": [str(root) for root in server.allowed_data_roots],
    }
    warnings = list(server.security_warnings)
    errors: list[str] = []
    if not server.research_root.exists():
        errors.append(f"research_root does not exist: {server.research_root}")
    elif not server.research_root.is_dir():
        errors.append(f"research_root is not a directory: {server.research_root}")

    runtime_root_explicit = bool(getattr(server, "_runtime_root_explicit", True))
    if not server.runtime_root.exists():
        if runtime_root_explicit:
            warnings.append(f"runtime_root does not exist: {server.runtime_root}")
    elif not server.runtime_root.is_dir():
        errors.append(f"runtime_root is not a directory: {server.runtime_root}")
    elif not os.access(server.runtime_root, os.W_OK | os.X_OK):
        errors.append(f"runtime_root is not writable/executable: {server.runtime_root}")

    if errors:
        return DoctorCheck(
            "roots",
            "error",
            "Resolved roots have blocking filesystem errors.",
            "Fix the configured research_root/runtime_root paths before using MCP rendering.",
            {**details, "errors": errors, "warnings": warnings},
        )
    if warnings:
        summary = "Resolved roots with security or filesystem warnings."
        if any("does not exist" in warning for warning in warnings):
            summary = "Resolved roots with warnings; one or more paths does not exist."
        hint = "Tighten GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS or set GRAPH_HUB_MCP_STRICT_ROOTS=1."
        if any(warning.startswith("runtime_root ") for warning in warnings):
            hint = "Create the configured runtime_root or choose a writable runtime location."
        return DoctorCheck(
            "roots",
            "warning",
            summary,
            hint,
            {**details, "warnings": warnings},
        )
    return DoctorCheck("roots", "ok", "Resolved roots are valid.", details=details)


def _check_adapters() -> DoctorCheck:
    try:
        selection = select_adapters()
    except AdapterSelectionError as exc:
        return DoctorCheck(
            "adapters",
            "error",
            str(exc),
            "Use GRAPH_HUB_PREFETCH_ADAPTER=none|gdrive, GRAPH_HUB_ATHENA_ADAPTER=off|legacy, "
            "and GRAPH_HUB_CONVENTIONS_ADAPTER=generic|workspace.",
        )
    return DoctorCheck(
        "adapters",
        "ok",
        "Adapters selected.",
        details={
            "prefetch": type(selection.prefetcher).__name__,
            "athena": type(selection.athena).__name__,
            "conventions": type(selection.conventions).__name__,
        },
    )
