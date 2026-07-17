"""Contained subprocess runtime support for :mod:`hub_core.process_runner`."""

import os
import subprocess
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar

from .execution_security import (
    ExecutionSecurityError,
    canonicalize_execution_environment,
    is_positive_finite_timeout,
    reject_reserved_execution_env,
)
from .runtime_paths import resolve_temp_dir
from .utils import get_hub_path

_RUN_COMMAND_ENV_OVERLAY: ContextVar[dict[str, str] | None] = ContextVar(
    "_RUN_COMMAND_ENV_OVERLAY",
    default=None,
)
_OUTPUT_TAIL_LINES = 20
_OUTPUT_TAIL_LINE_CHARS = 500
_CHILD_OUTPUT_CLASSES = (
    "R_PACKAGE_MISSING",
    "R_PACKAGE_LOAD_ERROR",
    "R_PARSE_ERROR",
    "R_IO_ERROR",
    "R_INPUT_MISSING",
    "R_INPUT_SCHEMA_ERROR",
    "R_OBJECT_NOT_FOUND",
    "R_EXECUTION_HALTED",
    "R_RUNTIME_ERROR",
    "PYTHON_TRACEBACK",
    "UNKNOWN",
)


@contextmanager
def run_command_env_overlay(env_overrides: dict[str, str]):
    prior = _RUN_COMMAND_ENV_OVERLAY.get() or {}
    merged = dict(prior)
    merged.update(env_overrides)
    token = _RUN_COMMAND_ENV_OVERLAY.set(merged)
    try:
        yield
    finally:
        _RUN_COMMAND_ENV_OVERLAY.reset(token)


def _classify_child_output(line: str) -> str:
    """Map child output to one fixed diagnostic class without returning content."""

    folded = line[:4096].casefold()
    if "there is no package called" in folded or "package is not installed" in folded:
        return "R_PACKAGE_MISSING"
    if "package or namespace load failed" in folded or "loadnamespace" in folded:
        return "R_PACKAGE_LOAD_ERROR"
    if "execution halted" in folded:
        return "R_EXECUTION_HALTED"
    if "no analysis input csv found" in folded:
        return "R_INPUT_MISSING"
    if "missing required column" in folded:
        return "R_INPUT_SCHEMA_ERROR"
    if "object" in folded and "not found" in folded:
        return "R_OBJECT_NOT_FOUND"
    if any(
        marker in folded
        for marker in ("cannot open", "failed to open", "no such file", "permission denied", "read error")
    ):
        return "R_IO_ERROR"
    if any(marker in folded for marker in ("parse error", "unexpected symbol", "unexpected string")):
        return "R_PARSE_ERROR"
    if "traceback (most recent call last)" in folded:
        return "PYTHON_TRACEBACK"
    if folded.startswith("error") or "error in " in folded:
        return "R_RUNTIME_ERROR"
    return "UNKNOWN"


def _child_output_metadata(line: str, *, sequence: int) -> tuple[str, str]:
    """Return content-free metadata and its allowlisted classification."""

    classification = _classify_child_output(line)
    if classification not in _CHILD_OUTPUT_CLASSES:  # defensive closed set
        classification = "UNKNOWN"
    character_count = len(line.rstrip("\r\n"))
    if character_count == 0:
        length_bucket = "empty"
    elif character_count <= 32:
        length_bucket = "1-32"
    elif character_count <= 128:
        length_bucket = "33-128"
    elif character_count <= _OUTPUT_TAIL_LINE_CHARS:
        length_bucket = "129-500"
    else:
        length_bucket = ">500"
    truncated = character_count > _OUTPUT_TAIL_LINE_CHARS
    metadata = (
        f"seq={sequence} class={classification} length_bucket={length_bucket} "
        f"truncated={str(truncated).lower()}"
    )
    return metadata, classification


def run_command_runtime(
    cmd_list,
    cwd,
    additional_env,
    timeout_seconds,
    *,
    log,
    popen_factory,
    build_uv_environment,
    ensure_uv_runtime_dirs,
    supervise_process,
):
    """Execute one command while preserving the orchestrator runtime contract."""

    hub_path = get_hub_path()

    if not is_positive_finite_timeout(timeout_seconds):
        log("      ❌ Execution configuration rejected: timeout_seconds must be a positive finite number")
        return False

    try:
        if additional_env:
            reject_reserved_execution_env(additional_env, source="additional_env")
        env_overlay = _RUN_COMMAND_ENV_OVERLAY.get()
        if env_overlay:
            reject_reserved_execution_env(env_overlay, source="execution environment overlay")
    except ExecutionSecurityError as exc:
        log(f"      ❌ Execution configuration rejected: {exc}")
        return False

    inherited_env = os.environ.copy()
    canonical_env = {
        "PYTHONPATH": (
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            + os.pathsep
            + inherited_env.get("PYTHONPATH", "")
        ),
        "RESEARCH_HUB_PATH": hub_path,
        "PROJECT_ROOT": os.path.abspath(cwd),
    }
    env = canonicalize_execution_environment(inherited_env, canonical_env)
    if "MPLCONFIGDIR" not in env:
        mpl_cache = os.path.join(resolve_temp_dir("matplotlib", project_root=cwd), "cache")
        os.makedirs(mpl_cache, exist_ok=True)
        env["MPLCONFIGDIR"] = mpl_cache
    if "MPLBACKEND" not in env and not env.get("DISPLAY"):
        env["MPLBACKEND"] = "Agg"
    if env_overlay:
        env.update(env_overlay)
    if additional_env:
        env.update(additional_env)
    env = build_uv_environment(env, hub_root=hub_path)
    ensure_uv_runtime_dirs(env)

    output_tail: deque[str] = deque(maxlen=_OUTPUT_TAIL_LINES)
    output_class_counts: Counter[str] = Counter()
    output_line_count = 0

    def record_output(line: str) -> None:
        nonlocal output_line_count
        output_line_count += 1
        metadata, classification = _child_output_metadata(line, sequence=output_line_count)
        output_class_counts[classification] += 1
        log(f"      child-output {metadata}")
        output_tail.append(metadata)

    try:
        result = supervise_process(
            cmd_list,
            cwd=os.path.abspath(cwd),
            env=env,
            timeout_seconds=float(timeout_seconds),
            on_output=record_output,
            popen_factory=popen_factory,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log(f"      ❌ Execution failed: {exc}")
        return False

    if result.timed_out:
        log(f"      ❌ Execution timed out ({timeout_seconds:g}s limit)")
    if result.failure:
        log(f"      ❌ Execution supervision failed: {result.failure}")
    if not result.succeeded:
        log(f"      ❌ Execution failed with return code {result.returncode}")
        if output_tail:
            class_summary = ",".join(
                f"{classification}:{output_class_counts[classification]}"
                for classification in _CHILD_OUTPUT_CLASSES
                if output_class_counts[classification]
            )
            log(
                f"      ❌ Child output metadata: lines={output_line_count} "
                f"classes={class_summary} tail={len(output_tail)}"
            )
            for tail_entry in output_tail:
                log(f"      ❌ child-meta {tail_entry}")
    return result.succeeded
