"""Contained subprocess runtime support for :mod:`hub_core.process_runner`."""

import os
import subprocess
import tempfile
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar

from .execution_security import (
    ExecutionSecurityError,
    canonicalize_execution_environment,
    is_positive_finite_timeout,
    reject_reserved_execution_env,
)
from .utils import get_hub_path

_RUN_COMMAND_ENV_OVERLAY: ContextVar[dict[str, str] | None] = ContextVar(
    "_RUN_COMMAND_ENV_OVERLAY",
    default=None,
)
_OUTPUT_TAIL_LINES = 20


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
        mpl_cache = os.path.join(tempfile.gettempdir(), "graph_hub_mplcache")
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

    output_lines: deque[str] = deque(maxlen=_OUTPUT_TAIL_LINES)

    def record_output(line: str) -> None:
        stripped = line.strip()
        log(f"      {stripped}")
        if stripped:
            output_lines.append(stripped)

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
        if output_lines:
            log(f"      ── last {len(output_lines)} lines ──")
            for tail_line in output_lines:
                log(f"      {tail_line}")
    return result.succeeded
