from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hub_core.adapters.selection import AdapterSelectionError, select_adapters
from hub_core.mcp.config import McpServerConfig
from hub_core.mcp.security import McpSecurityMixin
from hub_core.uv_runtime import build_uv_environment


class _DoctorSecurityState(McpSecurityMixin):
    def __init__(self, config: McpServerConfig) -> None:
        self._init_security_state(
            config=config,
            hub_path=None,
            research_root=None,
            runtime_root=None,
            write_tools_enabled=None,
        )


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
    server = _DoctorSecurityState(config)
    checks = [
        _check_python(),
        _check_uv(),
        _check_source_checkout_runtime(server),
        _check_runtime_dependencies(),
        _check_pytest(),
        _check_optional_io_dependency("pyarrow", "Parquet/Feather support", "python hub_uv.py sync --extra io"),
        _check_optional_io_dependency("tables", "HDF5 support", "python hub_uv.py sync --extra io"),
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
        f"FigOps doctor: {report['status']}",
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
        return "Environment is ready for FigOps MCP discovery and rendering."
    if status == "warning":
        return "Environment is usable, but optional or workflow-specific capabilities are missing."
    return "Environment has blocking configuration errors that must be fixed before reliable use."


def _check_python() -> DoctorCheck:
    version = _python_version()
    if sys.version_info < (3, 12):
        return DoctorCheck(
            "python",
            "error",
            f"Python {version} is below the required 3.12 runtime.",
            "Use Python 3.12 or newer; from a source checkout prefer `python hub_uv.py run python ...`.",
            {"executable": sys.executable, "version": version},
        )
    return DoctorCheck("python", "ok", f"Python {version} is supported.", details={"executable": sys.executable})


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _check_uv() -> DoctorCheck:
    uv_path = shutil.which("uv")
    if not uv_path:
        return DoctorCheck(
            "uv",
            "error",
            "uv is not available on PATH.",
            "Install uv outside this checkout, then use `python hub_uv.py sync` and "
            "`python hub_uv.py run ...` for source-checkout commands.",
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


def _check_source_checkout_runtime(server: _DoctorSecurityState) -> DoctorCheck:
    runtime_root = server.runtime_root
    runtime_root_explicit = bool(getattr(server, "_runtime_root_explicit", True))
    uv_path = shutil.which("uv")
    try:
        uv_env = build_uv_environment(hub_root=server.hub_path)
    except ValueError as exc:
        return DoctorCheck(
            "source_checkout_runtime",
            "error",
            "Source-checkout uv runtime paths are invalid.",
            "Choose a runtime root outside the FigOps checkout before using `python hub_uv.py ...`.",
            {
                "python_executable": sys.executable,
                "python_version": _python_version(),
                "uv_available": uv_path is not None,
                "uv_path": uv_path,
                "mcp_runtime_root": str(runtime_root),
                "runtime_root_explicit": runtime_root_explicit,
                "error": str(exc),
            },
        )

    uv_project_environment = Path(uv_env["UV_PROJECT_ENVIRONMENT"])
    uv_cache_dir = Path(uv_env["UV_CACHE_DIR"])
    hub_path = server.hub_path.resolve()
    runtime_root_exists = runtime_root.exists()
    runtime_root_is_dir = runtime_root.is_dir() if runtime_root_exists else False
    runtime_root_ready = runtime_root_is_dir and os.access(runtime_root, os.W_OK | os.X_OK)
    uv_environment_outside_hub = uv_project_environment != hub_path / ".venv" and hub_path not in uv_project_environment.parents
    details = {
        "python_executable": sys.executable,
        "python_version": _python_version(),
        "uv_available": uv_path is not None,
        "uv_path": uv_path,
        "RESEARCH_HUB_RUNTIME_ROOT": uv_env["RESEARCH_HUB_RUNTIME_ROOT"],
        "UV_PROJECT_ENVIRONMENT": uv_env["UV_PROJECT_ENVIRONMENT"],
        "UV_CACHE_DIR": uv_env["UV_CACHE_DIR"],
        "mcp_runtime_root": str(runtime_root),
        "uv_environment_outside_hub": uv_environment_outside_hub,
        "runtime_root_explicit": runtime_root_explicit,
        "runtime_root_exists": runtime_root_exists,
        "runtime_root_is_dir": runtime_root_is_dir,
        "runtime_root_writable_executable": runtime_root_ready,
        "operator_command": "python hub_uv.py run python figops_mcp_server.py doctor --json",
        "uv_cache_parent_exists": uv_cache_dir.parent.exists(),
    }
    errors: list[str] = []
    warnings: list[str] = []
    if sys.version_info < (3, 12):
        errors.append(f"Python {_python_version()} is below the required 3.12 runtime.")
    if uv_path is None:
        errors.append("uv is not available on PATH.")
    if not uv_environment_outside_hub:
        errors.append(f"UV_PROJECT_ENVIRONMENT is inside the FigOps checkout: {uv_project_environment}")
    if runtime_root_exists and not runtime_root_is_dir:
        errors.append(f"runtime_root is not a directory: {runtime_root}")
    elif runtime_root_exists and not runtime_root_ready:
        errors.append(f"runtime_root is not writable and executable: {runtime_root}")
    elif runtime_root_explicit and not runtime_root_exists:
        warnings.append(f"runtime_root does not exist: {runtime_root}")

    if errors:
        return DoctorCheck(
            "source_checkout_runtime",
            "error",
            "Source-checkout runtime readiness has blocking errors.",
            "Install uv, ensure PATH includes it, and choose a runtime root that is writable and executable.",
            {**details, "errors": errors, "warnings": warnings},
        )
    if warnings:
        return DoctorCheck(
            "source_checkout_runtime",
            "warning",
            "Source-checkout runtime readiness has filesystem warnings.",
            "Create the configured runtime root or choose an existing writable runtime location.",
            {**details, "warnings": warnings},
        )
    return DoctorCheck(
        "source_checkout_runtime",
        "ok",
        "Source-checkout runtime is ready for `python hub_uv.py ...` commands.",
        details=details,
    )


def _check_runtime_dependencies() -> DoctorCheck:
    required_modules = {
        "matplotlib": "plot rendering",
        "pandas": "CSV/table contracts",
        "yaml": "project_config.yaml parsing",
    }
    missing = [module for module in required_modules if not importlib.util.find_spec(module)]
    details = {
        "checked": sorted(required_modules),
        "missing": sorted(missing),
    }
    if missing:
        capabilities = ", ".join(required_modules[module] for module in missing)
        return DoctorCheck(
            "runtime_dependencies",
            "error",
            f"Missing Python runtime dependencies for {capabilities}.",
            "From a source checkout, run `python hub_uv.py sync`, then rerun doctor with "
            "`python hub_uv.py run python figops_mcp_server.py doctor`.",
            details,
        )
    return DoctorCheck(
        "runtime_dependencies",
        "ok",
        "Core Python runtime dependencies are importable.",
        details=details,
    )


def _check_pytest() -> DoctorCheck:
    if importlib.util.find_spec("pytest"):
        return DoctorCheck("pytest", "ok", "pytest is importable for source-checkout verification.")
    return DoctorCheck(
        "pytest",
        "warning",
        "pytest is missing; source-checkout tests cannot run in this Python environment.",
        "Use `python hub_uv.py sync --group dev`, then verify with "
        "`python hub_uv.py run python -m pytest tests/test_doctor.py -q`.",
    )


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
            "Install R for projects that declare `lang: R`, ensure `Rscript` is on PATH, then rerun doctor.",
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


def _check_write_tools(server: _DoctorSecurityState) -> DoctorCheck:
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


def _check_roots(server: _DoctorSecurityState) -> DoctorCheck:
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
            "and GRAPH_HUB_CONVENTIONS_ADAPTER=generic|surfur.",
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
