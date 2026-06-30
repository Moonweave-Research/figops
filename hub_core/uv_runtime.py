from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

try:
    from .runtime_paths import resolve_runtime_root
except ImportError:
    module_path = Path(__file__).with_name("runtime_paths.py")
    spec = importlib.util.spec_from_file_location("_figops_runtime_paths", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load FigOps runtime paths: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolve_runtime_root = module.resolve_runtime_root

UV_ENV_NAME = "figops"


def _as_path(value: str | os.PathLike) -> Path:
    return Path(value).expanduser().resolve()


def _default_hub_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_uv_project_environment(
    hub_root: str | os.PathLike | None = None,
    runtime_root: str | os.PathLike | None = None,
) -> str:
    """Return the external uv project environment path for FigOps."""
    hub_root_path = _as_path(hub_root or _default_hub_root())
    runtime_root_path = _as_path(runtime_root or resolve_runtime_root())
    env_path = runtime_root_path / "uv_envs" / UV_ENV_NAME

    if env_path == hub_root_path / ".venv" or hub_root_path in env_path.parents:
        raise ValueError(f"UV project environment must stay outside FigOps: {env_path}")

    return str(env_path)


def build_uv_environment(
    base_env: Mapping[str, str] | None = None,
    hub_root: str | os.PathLike | None = None,
    runtime_root: str | os.PathLike | None = None,
) -> dict[str, str]:
    """Build an environment that prevents uv from creating repo-local `.venv`."""
    env = dict(os.environ if base_env is None else base_env)
    runtime_root_value = runtime_root or env.get("RESEARCH_HUB_RUNTIME_ROOT") or resolve_runtime_root()
    runtime_root_path = _as_path(runtime_root_value)

    env["RESEARCH_HUB_RUNTIME_ROOT"] = str(runtime_root_path)
    env["UV_PROJECT_ENVIRONMENT"] = resolve_uv_project_environment(hub_root, runtime_root_path)
    env["UV_CACHE_DIR"] = str(runtime_root_path / "uv_cache")
    return env


def ensure_uv_runtime_dirs(env: Mapping[str, str]) -> None:
    Path(env["UV_PROJECT_ENVIRONMENT"]).parent.mkdir(parents=True, exist_ok=True)
    Path(env["UV_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)


def run_uv(argv: Sequence[str], cwd: str | os.PathLike | None = None) -> int:
    env = build_uv_environment(hub_root=_default_hub_root())
    ensure_uv_runtime_dirs(env)
    if shutil.which("uv", path=env.get("PATH")) is None:
        print(
            "Error: `uv` was not found on PATH. Install uv, then rerun this command, "
            "or use a Python environment with the FigOps dev dependencies installed.",
            file=sys.stderr,
        )
        return 127
    command = ["uv", *argv]
    return subprocess.call(command, cwd=str(cwd or _default_hub_root()), env=env)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args == ["--help"]:
        python_cmd = Path(sys.executable).name or "python"
        print(f"Usage: {python_cmd} hub_uv.py <uv-args...>")
        print(f"Example: {python_cmd} hub_uv.py run python orchestrator.py --list-projects")
        print(f"UV_PROJECT_ENVIRONMENT={resolve_uv_project_environment()}")
        return 0
    if args == ["--print-env"]:
        env = build_uv_environment(hub_root=_default_hub_root())
        print(f"RESEARCH_HUB_RUNTIME_ROOT={env['RESEARCH_HUB_RUNTIME_ROOT']}")
        print(f"UV_PROJECT_ENVIRONMENT={env['UV_PROJECT_ENVIRONMENT']}")
        print(f"UV_CACHE_DIR={env['UV_CACHE_DIR']}")
        return 0
    return run_uv(args)


if __name__ == "__main__":
    raise SystemExit(main())
