"""Deterministic, reviewable plans for copy-only structure changes."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import yaml

from .structure_path_security import capture_project_root, open_bound_source, source_identity

PLAN_VERSION = "2"
TOKEN_PREFIX = "FIGOPS-APPLY-"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty canonical relative path.")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or value in {".", ".."} or ".." in path.parts:
        raise ValueError(f"{field} must be a canonical relative path.")
    if any(":" in part for part in path.parts) or "\\" in value:
        raise ValueError(f"{field} must be a canonical relative path.")
    return value


def canonical_plan_digest(plan: Mapping[str, Any]) -> str:
    """Hash the semantic plan while excluding its self-referential digest."""

    payload = dict(plan)
    payload.pop("digest", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def confirmation_token(plan: Mapping[str, Any]) -> str:
    digest = str(plan.get("digest") or canonical_plan_digest(plan))
    return TOKEN_PREFIX + digest


def validate_confirmation_token(plan: Mapping[str, Any], token: str) -> None:
    digest = canonical_plan_digest(plan)
    if plan.get("digest") != digest:
        raise ValueError("Structure plan digest is stale or invalid.")
    if token != TOKEN_PREFIX + digest:
        raise PermissionError("Explicit confirmation token does not match the reviewed structure plan.")


def build_structure_plan(
    project_root: str | Path,
    approved_mappings: Iterable[Mapping[str, Any]],
    *,
    config_diff: Iterable[Mapping[str, Any]] = (),
    hardcoded_unresolved_references: Iterable[object] = (),
) -> dict[str, Any]:
    """Create a deterministic plan solely from explicitly approved mappings."""

    root = Path(project_root).absolute()
    try:
        root_identity = capture_project_root(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("project_root must be an existing, non-reparse directory.") from exc
    entries: list[dict[str, Any]] = []
    destinations: dict[str, list[str]] = {}
    for mapping in approved_mappings:
        source_rel = _relative(mapping.get("source"), field="source")
        destination_rel = _relative(mapping.get("destination"), field="destination")
        role = mapping.get("role")
        if not isinstance(role, str) or not role.strip():
            raise ValueError("Every approved mapping requires an explicit role.")
        source = root / Path(source_rel)
        try:
            identity = source_identity(source)
            with open_bound_source(
                root,
                source_rel,
                root_identity=root_identity,
                planned_identity=identity,
            ) as source_handle:
                digest = hashlib.sha256()
                size = 0
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"Approved source must be an existing safe regular file: {source_rel}") from exc
        entry = {
            "source": source_rel,
            "destination": destination_rel,
            "role": role.strip(),
            "sha256": digest.hexdigest(),
            "size": size,
            "source_identity": identity,
        }
        entries.append(entry)
        destinations.setdefault(destination_rel, []).append(source_rel)
    entries.sort(key=lambda item: (item["destination"], item["source"], item["role"]))

    collisions: list[dict[str, Any]] = []
    for destination, sources in sorted(destinations.items()):
        occupied = (root / Path(destination)).exists() or (root / Path(destination)).is_symlink()
        if len(sources) > 1 or occupied:
            collisions.append(
                {"destination": destination, "sources": sorted(sources), "existing_destination": occupied}
            )

    normalized_diff = [_normalize_config_edit(item) for item in config_diff]
    normalized_diff.sort(key=lambda item: json.dumps(item["path"], ensure_ascii=False))
    unresolved = sorted(
        [
            dict(item) if isinstance(item, Mapping) else {"reference": str(item)}
            for item in hardcoded_unresolved_references
        ],
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
    )
    config_path = root / "project_config.yaml"
    config_sha256: str | None = None
    config_identity: dict[str, int] | None = None
    config_text: str | None = None
    if config_path.is_file() and not config_path.is_symlink():
        config_identity = source_identity(config_path)
        with open_bound_source(
            root,
            "project_config.yaml",
            root_identity=root_identity,
            planned_identity=config_identity,
        ) as config_handle:
            config_bytes = config_handle.read()
        config_sha256 = hashlib.sha256(config_bytes).hexdigest()
        try:
            config_text = config_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("project_config.yaml must be valid UTF-8.") from exc
    config_update = _build_config_update(config_text, config_sha256, normalized_diff)
    rollback = {
        "remove_new_copies_only_if_hash_matches": [
            {"path": item["destination"], "sha256": item["sha256"]} for item in entries
        ],
        "config_backup_required": bool(normalized_diff),
        "delete_originals": False,
    }
    plan: dict[str, Any] = {
        "version": PLAN_VERSION,
        "project_root": str(root),
        "project_root_identity": {"device": root_identity[0], "inode": root_identity[1]},
        "operation": "copy_only",
        "entries": entries,
        "collisions": collisions,
        "config_diff": normalized_diff,
        "config_sha256": config_sha256,
        "config_identity": config_identity,
        "config_update": config_update,
        "hardcoded_unresolved_references": unresolved,
        "total_bytes": sum(item["size"] for item in entries),
        "rollback_journal": rollback,
    }
    plan["digest"] = canonical_plan_digest(plan)
    return plan


create_structure_plan = build_structure_plan
confirmation_token_for_plan = confirmation_token


def _normalize_config_edit(item: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(item, Mapping) or set(item) != {"path", "before", "after"}:
        raise ValueError("Each config diff must contain exactly path, before, and after.")
    path = item["path"]
    if not isinstance(path, (list, tuple)) or not path:
        raise ValueError("Config diff path must be a non-empty typed YAML path list.")
    normalized_path: list[str | int] = []
    for component in path:
        if isinstance(component, bool) or not isinstance(component, (str, int)):
            raise ValueError("Config diff path components must be strings or integer list indexes.")
        if isinstance(component, str) and not component:
            raise ValueError("Config diff path string components must not be empty.")
        if isinstance(component, int) and component < 0:
            raise ValueError("Config diff list indexes must be non-negative.")
        normalized_path.append(component)
    return {"path": normalized_path, "before": deepcopy(item["before"]), "after": deepcopy(item["after"])}


def _build_config_update(
    config_text: str | None,
    before_sha256: str | None,
    edits: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not edits:
        return None
    if before_sha256 is None or config_text is None:
        raise ValueError("Typed config edits require an existing regular project_config.yaml.")
    config = yaml.safe_load(config_text)
    updated = deepcopy(config)
    for edit in edits:
        cursor = updated
        for component in edit["path"][:-1]:
            try:
                cursor = cursor[component]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError(f"Config diff path does not exist: {edit['path']}") from exc
        leaf = edit["path"][-1]
        try:
            current = cursor[leaf]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Config diff path does not exist: {edit['path']}") from exc
        if current != edit["before"]:
            raise ValueError(f"Config diff before value is stale at: {edit['path']}")
        cursor[leaf] = deepcopy(edit["after"])
    after_text = yaml.safe_dump(updated, sort_keys=False, allow_unicode=True)
    after_bytes = after_text.encode("utf-8")
    return {
        "path": "project_config.yaml",
        "before_sha256": before_sha256,
        "after_sha256": hashlib.sha256(after_bytes).hexdigest(),
        "after_text": after_text,
        "size": len(after_bytes),
    }
