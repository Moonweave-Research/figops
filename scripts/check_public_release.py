#!/usr/bin/env python3
"""Conservative read-only gate for future public Graph Hub releases."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hub_core.provenance import read_provenance_fingerprint  # noqa: E402
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
BINARY_PROVENANCE_SUFFIXES = {".png", ".pdf", ".svg"}
TEXT_SCAN_SKIP_SUFFIXES = {".png", ".pdf", ".jpg", ".jpeg", ".gif", ".xlsx", ".rds"}


@dataclass(frozen=True)
class ReleaseCheckResult:
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blockers


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _decode_blocker(rel: str, exc: UnicodeDecodeError) -> str:
    return f"Unable to decode UTF-8 text file: {rel} ({exc.reason} at byte {exc.start})."


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
    core = pattern.strip()
    anchored = core.startswith("/")
    directory_only = core.endswith("/")
    core = core.strip("/")
    if not core:
        return False
    if directory_only:
        if core.startswith("**/"):
            target = core[3:]
            return candidate == target or candidate.startswith(f"{target}/") or f"/{target}/" in f"/{candidate}/"
        if anchored:
            return candidate == core or candidate.startswith(f"{core}/")
        return (
            candidate == core
            or candidate.startswith(f"{core}/")
            or f"/{core}/" in f"/{candidate}/"
        )
    if anchored:
        if "/" not in core and "/" in candidate:
            return False
        return fnmatch.fnmatch(candidate, core)
    if "/" in core:
        return fnmatch.fnmatch(candidate, core) or fnmatch.fnmatch(candidate, f"*/{core}")
    if fnmatch.fnmatch(candidate, core):
        return True
    if fnmatch.fnmatch(Path(candidate).name, core):
        return True
    if not any(char in core for char in "*?[]"):
        parts = candidate.split("/")
        return core in parts
    return False


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


def _iter_candidate_files(root: Path) -> list[Path]:
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
        files.append(path)
    return files


def _iter_text_files(root: Path) -> list[Path]:
    return [path for path in _iter_candidate_files(root) if path.suffix.lower() not in TEXT_SCAN_SKIP_SUFFIXES]


def _is_marker_scan_exempt(rel_path: str) -> bool:
    return rel_path in MARKER_SCAN_EXEMPT_PATHS


def _private_marker_in_text(text: str, rel_path: str) -> str | None:
    normalized_text = _normalize_text(text)
    normalized_rel = _normalize_text(rel_path)
    for marker in PRIVATE_MARKERS:
        normalized_marker = _normalize_text(marker)
        if normalized_marker in normalized_text or normalized_marker in normalized_rel:
            return marker
    return None


def _provenance_payload_text(fingerprint: dict) -> str:
    return json.dumps(fingerprint, ensure_ascii=False, sort_keys=True)


def run_release_check(root: Path, *, check_style_registry: bool = True) -> ReleaseCheckResult:
    blockers: list[str] = []
    warnings: list[str] = []

    license_path = root / "LICENSE"
    if not license_path.exists():
        blockers.append("LICENSE is missing; public release license is undefined.")
    else:
        try:
            license_text = _normalize_text(_read_text(license_path)).lower()
        except UnicodeDecodeError as exc:
            blockers.append(_decode_blocker("LICENSE", exc))
            license_text = ""
        if "all rights reserved" in license_text or "proprietary" in license_text:
            blockers.append("LICENSE is proprietary/all-rights-reserved; public release is blocked.")

    notice_path = root / "NOTICE"
    if notice_path.exists():
        try:
            notice_text = _normalize_text(_read_text(notice_path)).lower()
        except UnicodeDecodeError as exc:
            blockers.append(_decode_blocker("NOTICE", exc))
            notice_text = ""
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
        normalized_rel = _normalize_text(rel)
        for pattern in PRIVATE_DOC_PATTERNS:
            if _normalize_text(pattern) in normalized_rel:
                blockers.append(f"Private workflow document path present: {rel}.")
                break
        if _is_marker_scan_exempt(rel):
            continue
        try:
            text = _read_text(path)
        except UnicodeDecodeError as exc:
            blockers.append(_decode_blocker(rel, exc))
            continue
        marker = _private_marker_in_text(text, rel)
        if marker is not None:
            blockers.append(f"Private marker {marker!r} found in {rel}.")

    for path in _iter_candidate_files(root):
        if path.suffix.lower() not in BINARY_PROVENANCE_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        if _is_marker_scan_exempt(rel):
            continue
        fingerprint = read_provenance_fingerprint(str(path))
        if not fingerprint:
            continue
        marker = _private_marker_in_text(_provenance_payload_text(fingerprint), rel)
        if marker is not None:
            blockers.append(f"Private marker {marker!r} found in provenance fingerprint for {rel}.")

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
