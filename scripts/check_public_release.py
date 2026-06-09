#!/usr/bin/env python3
"""Conservative read-only gate for future public Graph Hub releases."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from themes.style_packs import private_or_internal_style_packs, validate_style_pack_registry  # noqa: E402

PRIVATE_MARKERS = (
    "02_Surfur_Polymer",
    "PI_control",
    "저항 측정",
    "nature_surfur",
    "resistance_premium",
)

PRIVATE_DOC_PATTERNS = (
    "docs/hks/",
    "HKS",
)

MARKER_SCAN_EXEMPT_PATHS = {
    "scripts/check_public_release.py",
    "tests/test_public_release_check.py",
}


@dataclass(frozen=True)
class ReleaseCheckResult:
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blockers


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _load_gitignore_patterns(root: Path) -> tuple[str, ...]:
    ignore_path = root / ".gitignore"
    if not ignore_path.exists():
        return ()
    patterns: list[str] = []
    for line in ignore_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return tuple(patterns)


def _matches_gitignore_pattern(rel_path: str, pattern: str) -> bool:
    candidate = rel_path.strip("/")
    core = pattern.strip("/")
    if not core:
        return False
    if core.startswith("**/"):
        suffix = core[3:]
        return candidate == suffix or candidate.startswith(f"{suffix}/") or f"/{suffix}/" in f"/{candidate}/"
    if "/" not in core:
        parts = candidate.split("/")
        return core in parts
    return candidate == core or candidate.startswith(f"{core}/")


def _is_ignored_by_gitignore(rel_path: str, patterns: tuple[str, ...]) -> bool:
    ignored = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        core = pattern[1:] if negated else pattern
        if _matches_gitignore_pattern(rel_path, core):
            ignored = not negated
    return ignored


def _iter_git_candidate_files(root: Path) -> list[Path] | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return [root / rel for rel in completed.stdout.split("\0") if rel]


def _iter_text_files(root: Path) -> list[Path]:
    ignored_parts = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".uv_cache",
        ".dvc",
        ".dvc_home",
        "venv",
        "env",
        "hub_logs",
    }
    candidates = _iter_git_candidate_files(root)
    if candidates is None:
        patterns = _load_gitignore_patterns(root)
        candidates = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if _is_ignored_by_gitignore(rel, patterns):
                continue
            candidates.append(path)

    files: list[Path] = []
    for path in candidates:
        if not path.is_file():
            continue
        if ignored_parts & set(path.parts):
            continue
        if path.suffix.lower() in {".png", ".pdf", ".jpg", ".jpeg", ".gif", ".xlsx", ".rds"}:
            continue
        files.append(path)
    return files


def _is_marker_scan_exempt(rel_path: str) -> bool:
    return rel_path in MARKER_SCAN_EXEMPT_PATHS


def run_release_check(root: Path, *, check_style_registry: bool = True) -> ReleaseCheckResult:
    blockers: list[str] = []
    warnings: list[str] = []

    license_path = root / "LICENSE"
    if not license_path.exists():
        blockers.append("LICENSE is missing; public release license is undefined.")
    else:
        license_text = _read_text(license_path).lower()
        if "all rights reserved" in license_text or "proprietary" in license_text:
            blockers.append("LICENSE is proprietary/all-rights-reserved; public release is blocked.")

    notice_path = root / "NOTICE"
    if notice_path.exists():
        notice_text = _read_text(notice_path).lower()
        if "no open source license" in notice_text:
            blockers.append("NOTICE states no open source license has been granted.")

    if check_style_registry:
        for error in validate_style_pack_registry():
            blockers.append(f"Style pack registry error: {error}")

        internal_packs = private_or_internal_style_packs()
        if internal_packs:
            names = ", ".join(str(pack["name"]) for pack in internal_packs)
            blockers.append(f"Internal/private style packs are present: {names}.")

    for path in _iter_text_files(root):
        rel = path.relative_to(root).as_posix()
        for pattern in PRIVATE_DOC_PATTERNS:
            if pattern in rel:
                blockers.append(f"Private workflow document path present: {rel}.")
                break
        if _is_marker_scan_exempt(rel):
            continue
        text = _read_text(path)
        for marker in PRIVATE_MARKERS:
            if marker in text or marker in rel:
                blockers.append(f"Private marker {marker!r} found in {rel}.")
                break

    return ReleaseCheckResult(blockers=tuple(sorted(set(blockers))), warnings=tuple(sorted(set(warnings))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Graph Hub release-candidate repository root")
    args = parser.parse_args(argv)

    result = run_release_check(args.root.resolve())
    if result.ok:
        print("public_release_check: ok")
    else:
        print("public_release_check: blocked")
        for blocker in result.blockers:
            print(f"- {blocker}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
