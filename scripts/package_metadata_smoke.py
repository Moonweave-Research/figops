#!/usr/bin/env python3
"""Validate built distribution package metadata and console scripts."""

from __future__ import annotations

import argparse
import configparser
import json
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.public_package_surface import DEFAULT_DIST_GLOB, expand_dist_paths  # noqa: E402


@dataclass(frozen=True)
class MetadataExpectations:
    name: str
    version: str
    authors: tuple[str, ...]
    maintainers: tuple[str, ...]
    console_scripts: Mapping[str, str]


def load_expectations(root: Path) -> MetadataExpectations:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    return MetadataExpectations(
        name=project["name"],
        version=project["version"],
        authors=tuple(entry["name"] for entry in project.get("authors", ()) if "name" in entry),
        maintainers=tuple(entry["name"] for entry in project.get("maintainers", ()) if "name" in entry),
        console_scripts=dict(project.get("scripts", {})),
    )


def _parse_metadata(text: str) -> Mapping[str, str]:
    message = Parser().parsestr(text)
    return {key: message.get(key, "") for key in ("Name", "Version", "Author", "Maintainer")}


def _parse_entry_points(text: str) -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read_string(text)
    if not parser.has_section("console_scripts"):
        return {}
    return {key: value.strip() for key, value in parser.items("console_scripts")}


def _wheel_metadata(path: Path) -> tuple[Mapping[str, str], Mapping[str, str]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_name = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        entry_points_name = next((name for name in names if name.endswith(".dist-info/entry_points.txt")), None)
        if metadata_name is None:
            raise ValueError(f"{path.name}: missing .dist-info/METADATA")
        metadata = _parse_metadata(archive.read(metadata_name).decode("utf-8"))
        entry_points = _parse_entry_points(archive.read(entry_points_name).decode("utf-8")) if entry_points_name else {}
        return metadata, entry_points


def _sdist_metadata(path: Path) -> tuple[Mapping[str, str], Mapping[str, str]]:
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        metadata_member = next((member for member in members if member.name.endswith("/PKG-INFO")), None)
        entry_points_member = next(
            (member for member in members if member.name.endswith(".egg-info/entry_points.txt")),
            None,
        )
        if metadata_member is None:
            raise ValueError(f"{path.name}: missing PKG-INFO")
        metadata_file = archive.extractfile(metadata_member)
        if metadata_file is None:
            raise ValueError(f"{path.name}: unreadable PKG-INFO")
        metadata = _parse_metadata(metadata_file.read().decode("utf-8"))
        entry_points: dict[str, str] = {}
        if entry_points_member is not None:
            entry_points_file = archive.extractfile(entry_points_member)
            if entry_points_file is not None:
                entry_points = _parse_entry_points(entry_points_file.read().decode("utf-8"))
        return metadata, entry_points


def inspect_artifact_metadata(path: Path) -> tuple[Mapping[str, str], Mapping[str, str]]:
    if path.suffix == ".whl":
        return _wheel_metadata(path)
    if path.name.endswith(".tar.gz"):
        return _sdist_metadata(path)
    raise ValueError(f"Unsupported distribution artifact: {path}")


def _missing_or_mismatched_metadata(
    artifact_name: str, metadata: Mapping[str, str], expectations: MetadataExpectations
) -> list[str]:
    blockers: list[str] = []
    expected_fields = {
        "Name": expectations.name,
        "Version": expectations.version,
    }
    if expectations.authors:
        expected_fields["Author"] = ", ".join(expectations.authors)
    if expectations.maintainers:
        expected_fields["Maintainer"] = ", ".join(expectations.maintainers)
    for field, expected in expected_fields.items():
        actual = metadata.get(field, "")
        if actual != expected:
            blockers.append(f"{artifact_name}: metadata {field!r} is {actual!r}, expected {expected!r}.")
    return blockers


def _missing_or_mismatched_entry_points(
    artifact_name: str, entry_points: Mapping[str, str], expectations: MetadataExpectations
) -> list[str]:
    blockers: list[str] = []
    for name, expected_target in expectations.console_scripts.items():
        actual = entry_points.get(name)
        if actual != expected_target:
            blockers.append(
                f"{artifact_name}: console script {name!r} is {actual!r}, expected {expected_target!r}."
            )
    return blockers


def inspect_package_metadata(root: Path, dist_glob: str = DEFAULT_DIST_GLOB) -> dict[str, object]:
    expectations = load_expectations(root)
    artifacts = expand_dist_paths(root, dist_glob)
    blockers: list[str] = []
    inspected: list[dict[str, object]] = []
    for artifact in artifacts:
        try:
            metadata, entry_points = inspect_artifact_metadata(artifact)
        except ValueError as exc:
            blockers.append(str(exc))
            continue
        artifact_name = artifact.name
        blockers.extend(_missing_or_mismatched_metadata(artifact_name, metadata, expectations))
        blockers.extend(_missing_or_mismatched_entry_points(artifact_name, entry_points, expectations))
        inspected.append(
            {
                "artifact": str(artifact),
                "name": metadata.get("Name", ""),
                "version": metadata.get("Version", ""),
                "author": metadata.get("Author", ""),
                "maintainer": metadata.get("Maintainer", ""),
                "console_scripts": dict(sorted(entry_points.items())),
            }
        )

    if not artifacts:
        blockers.append(f"No distribution artifacts found for glob: {dist_glob}")

    return {
        "schema_version": "package_metadata_smoke/1",
        "artifact_count": len(artifacts),
        "artifacts": [str(path) for path in artifacts],
        "inspected": inspected,
        "expected": {
            "name": expectations.name,
            "version": expectations.version,
            "authors": list(expectations.authors),
            "maintainers": list(expectations.maintainers),
            "console_scripts": dict(sorted(expectations.console_scripts.items())),
        },
        "ok": not blockers,
        "blockers": sorted(set(blockers)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dist-glob", default=DEFAULT_DIST_GLOB)
    args = parser.parse_args(argv)

    payload = inspect_package_metadata(args.root.resolve(), args.dist_glob)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
