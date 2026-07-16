"""Validate structure-plan destinations against declared project roles."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml

from .project_structure_contract import resolve_project_structure
from .structure_contract_types import SEMANTIC_ROLE_BY_ROOT_ROLE
from .structure_path_security import hash_handle, open_bound_source, source_identity


def config_mapping(
    config_path: Path,
    config_update: Mapping[str, Any] | None,
    *,
    root: Path,
    root_identity: tuple[int, int, int],
    planned_hash: str | None,
) -> Mapping[str, Any]:
    """Load the reviewed effective config used to bind plan destinations."""

    if config_update is not None:
        loaded = yaml.safe_load(str(config_update["after_text"]))
    elif config_path.is_file():
        identity = source_identity(config_path)
        with open_bound_source(
            root,
            "project_config.yaml",
            root_identity=root_identity,
            planned_identity=identity,
        ) as config_handle:
            actual_hash, _ = hash_handle(config_handle)
            if actual_hash != planned_hash:
                raise RuntimeError("project_config.yaml changed before role binding validation.")
            loaded = yaml.safe_load(config_handle.read().decode("utf-8"))
    else:
        loaded = {}
    if loaded is None:
        return {}
    if not isinstance(loaded, Mapping):
        raise ValueError("Project config must be a mapping before structure apply.")
    return loaded


def validate_role_destination_bindings(
    root: Path,
    entries: list[Mapping[str, Any]],
    *,
    config_path: Path,
    config_update: Mapping[str, Any] | None,
    root_identity: tuple[int, int, int],
    planned_hash: str | None,
) -> None:
    """Ensure every reviewed copy lands below the root declared for its role."""

    contract = resolve_project_structure(
        config_mapping(
            config_path,
            config_update,
            root=root,
            root_identity=root_identity,
            planned_hash=planned_hash,
        ),
        project_root=root,
    )
    role_roots = {
        semantic_role: PurePosixPath(contract.roots[root_role])
        for root_role, semantic_role in SEMANTIC_ROLE_BY_ROOT_ROLE.items()
    }
    for entry in entries:
        role = entry.get("role")
        destination = PurePosixPath(str(entry.get("destination")))
        expected_root = role_roots.get(role)
        if expected_root is None:
            raise ValueError(f"Plan entry uses an unknown structure role: {role!r}")
        is_descendant = (
            len(destination.parts) > len(expected_root.parts)
            and destination.parts[: len(expected_root.parts)] == expected_root.parts
        )
        if not is_descendant:
            raise ValueError(
                f"Plan destination is not bound to the resolved {role!r} role root: "
                f"{entry.get('destination')}"
            )
