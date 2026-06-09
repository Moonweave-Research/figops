#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def _runtime_root() -> Path:
    override = os.environ.get("GRAPH_HUB_RUNTIME_ROOT")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "Graph_making_hub"
    return Path.home() / ".cache" / "Graph_making_hub"


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    server = repo_root / "graphhub_mcp_server.py"
    server_args = [str(server), *sys.argv[1:]]
    venv_python = _runtime_root() / "uv_envs" / "graph-making-hub" / "bin" / "python3"
    if venv_python.is_file():
        os.execv(str(venv_python), [str(venv_python), *server_args])

    hub_uv = repo_root / "hub_uv.py"
    os.execv(str(hub_uv), [str(hub_uv), "run", "python", *server_args])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
