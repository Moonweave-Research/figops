#!/usr/bin/env python3
"""Inspect built distribution artifacts for public-package surface blockers."""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_public_release import PRIVATE_MARKERS, _normalize_text  # noqa: E402

DEFAULT_DIST_GLOB = "dist/*"
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".in",
    ".json",
    ".md",
    ".py",
    ".r",
    ".R",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
BLOCKED_PATH_PATTERNS = (
    "*/tests/*",
    "*/tests",
    "*/docs/hks/*",
    "*/docs/02-design/*",
    "*/docs/superpowers/*",
    "*/AGENTS.md",
    "*/task.md",
    "*/Research_Central_Architecture.md",
    "project_config_template.yaml",
    "figops-*/project_config_template.yaml",
)


@dataclass(frozen=True)
class ArtifactMember:
    artifact: str
    name: str
    content: bytes | None = None

    @property
    def normalized_name(self) -> str:
        return _normalize_text(self.name)


def expand_dist_paths(root: Path, dist_glob: str = DEFAULT_DIST_GLOB) -> tuple[Path, ...]:
    pattern = Path(dist_glob).expanduser()
    if pattern.is_absolute():
        matches = glob.glob(str(pattern))
    else:
        matches = glob.glob(str(root / pattern))
    return tuple(
        sorted(
            path.resolve()
            for path in (Path(match) for match in matches)
            if path.is_file() and not path.name.startswith(".")
        )
    )


def _iter_wheel_members(path: Path) -> Iterator[ArtifactMember]:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                yield ArtifactMember(str(path), info.filename)
                continue
            content = archive.read(info) if Path(info.filename).suffix.lower() in TEXT_SUFFIXES else None
            yield ArtifactMember(str(path), info.filename, content)


def _iter_sdist_members(path: Path) -> Iterator[ArtifactMember]:
    with tarfile.open(path) as archive:
        for info in archive.getmembers():
            if info.isdir():
                yield ArtifactMember(str(path), info.name)
                continue
            suffix = Path(info.name).suffix.lower()
            content: bytes | None = None
            if suffix in TEXT_SUFFIXES:
                file_obj = archive.extractfile(info)
                if file_obj is not None:
                    content = file_obj.read()
            yield ArtifactMember(str(path), info.name, content)


def iter_artifact_members(path: Path) -> Iterator[ArtifactMember]:
    if path.suffix == ".whl":
        yield from _iter_wheel_members(path)
        return
    if path.name.endswith(".tar.gz"):
        yield from _iter_sdist_members(path)
        return
    raise ValueError(f"Unsupported distribution artifact: {path}")


def blocked_path_reason(member_name: str) -> str | None:
    normalized = _normalize_text(member_name)
    if normalized.endswith("/hub_core/templates/project_config_template.yaml"):
        return None
    for pattern in BLOCKED_PATH_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return pattern
    return None


def private_marker_in_member(member: ArtifactMember) -> str | None:
    haystacks = [member.normalized_name]
    if member.content is not None:
        try:
            haystacks.append(_normalize_text(member.content.decode("utf-8")))
        except UnicodeDecodeError:
            return "undecodable_text"
    for marker in PRIVATE_MARKERS:
        normalized_marker = _normalize_text(marker)
        if any(normalized_marker in haystack for haystack in haystacks):
            return marker
    return None


def inspect_public_package_surface(root: Path, dist_glob: str = DEFAULT_DIST_GLOB) -> dict[str, object]:
    artifacts = expand_dist_paths(root, dist_glob)
    blockers: list[str] = []
    member_count = 0
    for artifact in artifacts:
        for member in iter_artifact_members(artifact):
            member_count += 1
            path_reason = blocked_path_reason(member.name)
            if path_reason is not None:
                blockers.append(f"{Path(member.artifact).name}: blocked path {member.name!r} matched {path_reason!r}.")
            marker = private_marker_in_member(member)
            if marker is not None:
                blockers.append(f"{Path(member.artifact).name}: private marker {marker!r} found in {member.name!r}.")

    if not artifacts:
        blockers.append(f"No distribution artifacts found for glob: {dist_glob}")

    return {
        "schema_version": "public_package_surface/1",
        "artifact_count": len(artifacts),
        "member_count": member_count,
        "artifacts": [str(path) for path in artifacts],
        "ok": not blockers,
        "blockers": sorted(set(blockers)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist-glob", default=DEFAULT_DIST_GLOB)
    args = parser.parse_args(argv)

    payload = inspect_public_package_surface(args.root.resolve(), args.dist_glob)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
