#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from hub_core.runtime_paths import preview_runtime_root


def _runtime_root() -> Path:
    return Path(preview_runtime_root()).expanduser()


def _venv_python(runtime_root: Path) -> Path:
    if os.name == "nt":
        return runtime_root / "uv_envs" / "figops" / "Scripts" / "python.exe"
    return runtime_root / "uv_envs" / "figops" / "bin" / "python"


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    server = repo_root / "graphhub_mcp_server.py"
    server_args = [str(server), *sys.argv[1:]]
    venv_python = _venv_python(_runtime_root())
    if venv_python.is_file():
        os.execv(str(venv_python), [str(venv_python), *server_args])

    hub_uv = repo_root / "hub_uv.py"
    os.execv(sys.executable, [sys.executable, str(hub_uv), "run", "python", *server_args])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
