"""Command/path helpers used by the pipeline process runner."""

from __future__ import annotations

import sys
from pathlib import Path

from .utils import get_hub_path


def join_config_path(directory: str, filename: str) -> str:
    normalized_dir = str(directory or "").replace("\\", "/").rstrip("/")
    normalized_name = str(filename or "").replace("\\", "/").split("/")[-1]
    return f"{normalized_dir}/{normalized_name}" if normalized_dir else normalized_name


def fallback_sanitize_path(raw_path: str, allowed_roots: list[Path]) -> Path:
    """Standalone fallback when Athena's path_sanitizer is unavailable."""
    if ".." in Path(raw_path).parts:
        raise ValueError(f"Path traversal rejected: '..' found in '{raw_path}'")

    candidate = Path(raw_path).expanduser().resolve()
    for root in allowed_roots:
        resolved_root = root.expanduser().resolve()
        try:
            candidate.relative_to(resolved_root)
            return candidate
        except ValueError:
            continue

    allowed_strs = ", ".join(str(root) for root in allowed_roots)
    raise ValueError(f"Path '{candidate}' is outside all allowed roots: {allowed_strs}")


def sanitize_script_path(raw_path: str, project_dir: str) -> str:
    """Verify script path is within FigOps before execution."""
    hub_root = Path(get_hub_path()).resolve()
    project_root = Path(project_dir).resolve()
    allowed = [hub_root, project_root]
    try:
        return str(fallback_sanitize_path(raw_path, allowed))
    except ValueError as exc:
        raise ValueError(f"Script path rejected (path traversal guard): {exc}") from exc


def resolve_runner(lang, step_cfg, config):
    execution = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
    if lang == "r":
        return step_cfg.get("r_exec") or execution.get("rscript") or "Rscript"
    if lang in {"python", "py"}:
        return step_cfg.get("python_exec") or execution.get("python") or sys.executable
    return None


def prefix_uv_if_needed(cmd, config):
    environment = config.get("environment", {})
    if environment.get("uv_run") is True:
        return ["uv", "run"] + cmd
    return cmd


def build_r_cmd(runner: str, script_path: str, config: dict) -> list[str]:
    """Build the Rscript command, wrapping with renv::activate() when r_strict is enabled."""
    environment = config.get("environment", {}) or {}
    r_strict = bool(environment.get("r_strict", False))
    if r_strict:
        safe_path = str(script_path).replace("\\", "\\\\").replace("'", "\\'")
        renv_expr = (
            "tryCatch("
            "renv::activate(), "
            "error=function(e) stop(paste('[renv] activate() failed:', conditionMessage(e)))"
            f"); source('{safe_path}')"
        )
        return [runner, "-e", renv_expr]
    return [runner, script_path]
