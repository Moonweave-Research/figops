#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_main():
    module_path = Path(__file__).resolve().parent / "hub_core" / "uv_runtime.py"
    spec = importlib.util.spec_from_file_location("_figops_uv_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load FigOps uv runtime: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


main = _load_main()

if __name__ == "__main__":
    raise SystemExit(main())
