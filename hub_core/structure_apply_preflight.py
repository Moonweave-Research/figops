"""Reviewed-plan destination preflight for structure transactions.

This module owns plan validation and destination-parent witness preparation.
Destination parents are only created eagerly for the legacy no-verifier path;
when an authority verifier is supplied, existing parent components are
witnessed without mutation and any missing suffix is materialized only after
the verifier has accepted the reviewed plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .structure_path_security import (
    DirectoryWitness,
    capture_directory_witness,
    hash_handle,
    open_bound_source,
)


@dataclass(frozen=True, slots=True)
class PreparedStructureEntry:
    """Source and destination facts validated before the authority gate."""

    entry: Mapping[str, Any]
    source: Path
    destination: Path
    parent_relative: str
    parent_witness: DirectoryWitness | None


def inside(root: Path, value: object) -> Path:
    """Resolve a canonical project-relative plan path without following links."""

    if not isinstance(value, str):
        raise ValueError("Plan paths must be strings.")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or ".." in relative.parts
        or any(":" in part for part in relative.parts)
        or "\\" in value
    ):
        raise ValueError("Plan path escapes the project root.")
    path = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Plan path traverses a symlink: {value}")
    return path


def prepare_structure_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    root: Path,
    root_identity: tuple[int, int, int],
    defer_parent_creation: bool,
) -> list[PreparedStructureEntry]:
    """Validate sources, destinations, and parent witnesses before applying."""

    prepared: list[PreparedStructureEntry] = []
    for entry in entries:
        if set(entry) != {"source", "destination", "role", "sha256", "size", "source_identity"}:
            raise ValueError("Plan entry shape is invalid or contains an executable operation.")
        if not isinstance(entry["source_identity"], Mapping) or set(entry["source_identity"]) != {
            "device",
            "inode",
        }:
            raise ValueError("Plan source identity is invalid.")
        source = inside(root, entry["source"])
        destination = inside(root, entry["destination"])
        with open_bound_source(
            root,
            entry["source"],
            root_identity=root_identity,
            planned_identity=dict(entry["source_identity"]),
        ) as source_handle:
            source_hash, source_size = hash_handle(source_handle)
        if source_size != entry["size"] or source_hash != entry["sha256"]:
            raise RuntimeError(f"Planned source changed after review: {entry['source']}")
        parent_relative = PurePosixPath(entry["destination"]).parent.as_posix()
        parent_witness: DirectoryWitness | None = None
        if defer_parent_creation:
            try:
                # Validate existing parent components without creating a
                # destination directory before the authority gate.
                capture_directory_witness(
                    root,
                    parent_relative,
                    root_identity=root_identity,
                    create=False,
                )
            except FileNotFoundError:
                pass
        else:
            parent_witness = capture_directory_witness(
                root,
                parent_relative,
                root_identity=root_identity,
                create=True,
            )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Destination appeared after plan review: {entry['destination']}")
        prepared.append(
            PreparedStructureEntry(
                entry=entry,
                source=source,
                destination=destination,
                parent_relative=parent_relative,
                parent_witness=parent_witness,
            )
        )
    return prepared


def materialize_parent_witness(
    prepared: PreparedStructureEntry,
    *,
    root: Path,
    root_identity: tuple[int, int, int],
) -> DirectoryWitness:
    """Return a reviewed parent witness, creating missing suffixes if needed."""

    if prepared.parent_witness is not None:
        return prepared.parent_witness
    return capture_directory_witness(
        root,
        prepared.parent_relative,
        root_identity=root_identity,
        create=True,
    )
