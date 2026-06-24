#!/usr/bin/env python3
"""Fail-closed wrapper for TestPyPI/PyPI uploads."""

from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_public_release import ReleaseCheckResult, run_release_check  # noqa: E402

DEFAULT_DIST_GLOB = "dist/*"


def expand_dist_paths(root: Path, dist_glob: str = DEFAULT_DIST_GLOB) -> tuple[Path, ...]:
    pattern = Path(dist_glob).expanduser()
    if pattern.is_absolute():
        matches = glob.glob(str(pattern))
    else:
        matches = glob.glob(str(root / pattern))
    return tuple(sorted(Path(path).resolve() for path in matches if Path(path).is_file()))


def build_upload_command(repository: str, dist_paths: Sequence[Path]) -> list[str]:
    command = [sys.executable, "-m", "twine", "upload"]
    if repository != "pypi":
        command.extend(["--repository", repository])
    command.extend(str(path) for path in dist_paths)
    return command


def upload_blockers(root: Path, dist_glob: str = DEFAULT_DIST_GLOB) -> tuple[str, ...]:
    release_result = run_release_check(root)
    blockers = list(release_result.blockers)
    if not expand_dist_paths(root, dist_glob):
        blockers.append(f"No distribution files found for glob: {dist_glob}")
    return tuple(sorted(set(blockers)))


def _print_release_result(result: ReleaseCheckResult) -> None:
    if result.ok:
        print("public_release_check: ok")
    else:
        print("public_release_check: blocked")
        for blocker in result.blockers:
            print(f"- {blocker}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root to validate before upload")
    parser.add_argument("--dist-glob", default=DEFAULT_DIST_GLOB, help="Distribution artifact glob, relative to root")
    parser.add_argument(
        "--repository",
        choices=("testpypi", "pypi"),
        default="testpypi",
        help="Twine repository target. Defaults to TestPyPI.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run twine upload. Without this flag the command is only printed.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    release_result = run_release_check(root)
    _print_release_result(release_result)
    dist_paths = expand_dist_paths(root, args.dist_glob)
    if not dist_paths:
        print(f"upload_guard: blocked: no distribution files found for glob: {args.dist_glob}", file=sys.stderr)
        return 1
    if not release_result.ok:
        print("upload_guard: blocked: public release gate must pass before TestPyPI/PyPI upload.", file=sys.stderr)
        return 1

    check_command = [sys.executable, "-m", "twine", "check", *(str(path) for path in dist_paths)]
    upload_command = build_upload_command(args.repository, dist_paths)
    print("twine_check:", " ".join(check_command))
    print("twine_upload:", " ".join(upload_command))
    if not args.execute:
        print("upload_guard: dry-run only; pass --execute to upload after reviewing the command.")
        return 0

    check_completed = subprocess.run(check_command, check=False)
    if check_completed.returncode != 0:
        return check_completed.returncode
    return subprocess.run(upload_command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
