#!/usr/bin/env python3
"""Run consumer-style install smokes against a built wheel."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST_DIR = "dist"
AUTHENTIC_STYLE_METADATA_SMOKE = (
    "import json; "
    "from themes.authentic_style_language import get_authentic_style_language_metadata; "
    "metadata = get_authentic_style_language_metadata('nature'); "
    "assert metadata['matrix_source'] == 'package:themes/data/journal_visual_language_matrix.json'; "
    "print(json.dumps(metadata, sort_keys=True))"
)


def package_version(root: Path) -> str:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def package_name(root: Path) -> str:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["name"]


def wheel_distribution_stem(root: Path) -> str:
    return re.sub(r"[-_.]+", "_", package_name(root)).lower()


def expected_wheel_name(root: Path) -> str:
    return f"{wheel_distribution_stem(root)}-{package_version(root)}-py3-none-any.whl"


def resolve_wheel(root: Path, wheel: Path | None = None, dist_dir: str = DEFAULT_DIST_DIR) -> Path:
    if wheel is not None:
        resolved = wheel.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Wheel not found: {resolved}")
        return resolved

    expected = (root / dist_dir / expected_wheel_name(root)).resolve()
    if not expected.is_file():
        raise FileNotFoundError(f"Expected wheel not found: {expected}. Run `uv build` first.")
    return expected


def consumer_smoke_commands(
    wheel: Path, uv_bin: str = "uv", scaffold_project: str = "smoke_project"
) -> tuple[tuple[str, ...], ...]:
    wheel_ref = str(wheel)
    return (
        (
            uv_bin,
            "run",
            "--isolated",
            "--with",
            wheel_ref,
            "python",
            "-c",
            AUTHENTIC_STYLE_METADATA_SMOKE,
        ),
        (uv_bin, "run", "--isolated", "--with", wheel_ref, "figops-mcp", "--smoke"),
        (uv_bin, "run", "--isolated", "--with", wheel_ref, "figops", "--help"),
        (uv_bin, "run", "--isolated", "--with", wheel_ref, "figops", "--init", "--project", scaffold_project),
    )


def run_commands(commands: Sequence[Sequence[str]], cwd: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for command in commands:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, cwd=cwd)
        results.append(
            {
                "command": list(command),
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
        )
        if completed.returncode != 0:
            break
    return results


def inspect_consumer_install(root: Path, wheel: Path | None = None, uv_bin: str = "uv") -> dict[str, object]:
    wheel_path = resolve_wheel(root, wheel)
    with tempfile.TemporaryDirectory(prefix="figops-consumer-smoke-") as temp_dir:
        smoke_cwd = Path(temp_dir)
        commands = consumer_smoke_commands(
            wheel_path,
            uv_bin=uv_bin,
            scaffold_project=str(smoke_cwd / "smoke_project"),
        )
        results = run_commands(commands, cwd=smoke_cwd)
    blockers = [
        f"Command failed with exit {result['returncode']}: {' '.join(result['command'])}"
        for result in results
        if result["returncode"] != 0
    ]
    return {
        "schema_version": "consumer_install_smoke/1",
        "wheel": str(wheel_path),
        "ok": not blockers and len(results) == len(commands),
        "blockers": blockers,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help="Wheel to install. Defaults to dist/<current-version>.whl",
    )
    parser.add_argument("--uv-bin", default="uv", help="uv executable to run consumer-style smokes")
    args = parser.parse_args(argv)

    try:
        payload = inspect_consumer_install(args.root.resolve(), args.wheel, uv_bin=args.uv_bin)
    except FileNotFoundError as exc:
        payload = {
            "schema_version": "consumer_install_smoke/1",
            "wheel": str(args.wheel) if args.wheel else None,
            "ok": False,
            "blockers": [str(exc)],
            "results": [],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
