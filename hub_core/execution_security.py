from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final, Mapping

DEFAULT_EXECUTION_TIMEOUT_SECONDS: Final[float] = 600.0
RESERVED_EXECUTION_ENV_KEYS: Final[frozenset[str]] = frozenset(
    {
        "PYTHONPATH",
        "RESEARCH_HUB_PATH",
        "PROJECT_ROOT",
        "RESEARCH_HUB_RUNTIME_ROOT",
        "RESEARCH_HUB_RUNTIME_HOME",
        "GRAPH_HUB_RUNTIME_ROOT",
        "UV_PROJECT_ENVIRONMENT",
        "UV_CACHE_DIR",
    }
)


@dataclass(frozen=True, slots=True)
class ExecutionSecurityError(ValueError):
    message: str

    def __str__(self) -> str:
        return self.message


def is_reserved_execution_env_key(key: str) -> bool:
    return key.upper() in RESERVED_EXECUTION_ENV_KEYS


def reject_reserved_execution_env(env: Mapping[str, str], *, source: str) -> None:
    reserved = sorted(key for key in env if is_reserved_execution_env_key(key))
    if reserved:
        joined = ", ".join(reserved)
        raise ExecutionSecurityError(f"{source} contains reserved execution environment key(s): {joined}")


def canonicalize_execution_environment(
    inherited: Mapping[str, str],
    canonical: Mapping[str, str],
) -> dict[str, str]:
    env = {key: value for key, value in inherited.items() if not is_reserved_execution_env_key(key)}
    env.update(canonical)
    return env


def output_pattern_error(pattern: str) -> str | None:
    if not pattern.strip():
        return "must be a non-empty string"
    normalized = pattern.replace("\\", "/")
    windows_path = PureWindowsPath(pattern)
    if PurePosixPath(normalized).is_absolute() or bool(windows_path.anchor):
        return "must be a project-relative path"
    if ".." in PurePosixPath(normalized).parts:
        return "must not contain parent traversal '..'"
    return None


def resolve_contained_project_path(project_dir: str | os.PathLike[str], relative_path: str) -> Path:
    error = output_pattern_error(relative_path)
    if error is not None:
        raise ExecutionSecurityError(f"Output path {error}: {relative_path!r}")

    project_root = Path(project_dir).resolve()
    candidate = (project_root / Path(relative_path)).resolve(strict=False)
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ExecutionSecurityError(f"Output path escapes project root: {relative_path!r}") from exc
    return candidate


def is_positive_finite_timeout(value: int | float | None) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def execution_timeout_seconds(config: Mapping[str, dict]) -> float:
    configured_execution = config.get("execution", {})
    execution = configured_execution if isinstance(configured_execution, Mapping) else {}
    raw_timeout = execution.get("timeout_seconds", DEFAULT_EXECUTION_TIMEOUT_SECONDS)
    if not is_positive_finite_timeout(raw_timeout):
        raise ExecutionSecurityError("execution.timeout_seconds must be a positive finite number")
    return float(raw_timeout)
