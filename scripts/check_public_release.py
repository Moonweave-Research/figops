#!/usr/bin/env python3
"""Conservative read-only gate for future public Graph Hub releases."""

from __future__ import annotations

import argparse
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


def _iter_text_files(root: Path) -> list[Path]:
    ignored_parts = {".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ignored_parts & set(path.parts):
            continue
        if path.suffix.lower() in {".png", ".pdf", ".svg", ".jpg", ".jpeg", ".xlsx", ".rds"}:
            continue
        files.append(path)
    return files


def run_release_check(root: Path) -> ReleaseCheckResult:
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
        text = _read_text(path)
        for marker in PRIVATE_MARKERS:
            if marker in text or marker in rel:
                blockers.append(f"Private marker {marker!r} found in {rel}.")
                break

    return ReleaseCheckResult(blockers=tuple(sorted(set(blockers))), warnings=tuple(sorted(set(warnings))))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Graph Hub repository root")
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
