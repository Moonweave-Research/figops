#!/usr/bin/env python3
"""Verify a GitHub release exposes the current wheel and sdist assets."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "Moonweave-Research/figops"


def package_version(root: Path) -> str:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def package_name(root: Path) -> str:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["name"]


def wheel_distribution_stem(root: Path) -> str:
    return re.sub(r"[-_.]+", "_", package_name(root)).lower()


def expected_asset_names(root: Path) -> tuple[str, str]:
    version = package_version(root)
    dist_name = wheel_distribution_stem(root)
    return (
        f"{dist_name}-{version}-py3-none-any.whl",
        f"{dist_name}-{version}.tar.gz",
    )


def release_tag(root: Path) -> str:
    return f"v{package_version(root)}"


def gh_release_view_command(gh_bin: str, repo: str, tag: str) -> tuple[str, ...]:
    return (gh_bin, "release", "view", tag, "--repo", repo, "--json", "assets,url,tagName")


def _run_json(command: Sequence[str]) -> tuple[dict[str, object] | None, str | None]:
    if os.name == "nt":
        executable = Path(command[0])
        if executable.is_file() and executable.suffix.lower() not in {".exe", ".bat", ".cmd", ".com"}:
            command = (sys.executable, *command)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return None, completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from gh: {exc}"


def inspect_release_assets(root: Path, repo: str = DEFAULT_REPO, gh_bin: str = "gh") -> dict[str, object]:
    tag = release_tag(root)
    expected = expected_asset_names(root)
    command = gh_release_view_command(gh_bin, repo, tag)
    payload, error = _run_json(command)
    blockers: list[str] = []
    if error is not None:
        blockers.append(f"Unable to inspect release {tag}: {error}")
        assets: list[dict[str, object]] = []
        release_url = ""
    else:
        assets = list(payload.get("assets", [])) if payload is not None else []
        release_url = str(payload.get("url", "")) if payload is not None else ""

    asset_names = sorted(str(asset.get("name", "")) for asset in assets)
    for name in expected:
        if name not in asset_names:
            blockers.append(f"Release {tag} is missing asset {name!r}.")

    return {
        "schema_version": "github_release_asset_smoke/1",
        "repo": repo,
        "tag": tag,
        "url": release_url,
        "expected_assets": list(expected),
        "actual_assets": asset_names,
        "ok": not blockers,
        "blockers": blockers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--gh-bin", default="gh")
    args = parser.parse_args(argv)

    payload = inspect_release_assets(args.root.resolve(), repo=args.repo, gh_bin=args.gh_bin)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
