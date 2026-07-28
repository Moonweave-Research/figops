from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from .adapters import select_adapters
from .config_parser import ALLOWED_TARGET_FORMATS, load_yaml_with_unique_keys
from .dependency_script_inspection import analyze_dependency_script
from .project_layout import SCAFFOLD_MANIFEST_FILENAME, build_scaffold_manifest
from .project_structure_contract import resolve_project_structure
from .structure_apply import apply_structure_plan
from .structure_contract_types import SEMANTIC_ROLE_BY_ROOT_ROLE
from .structure_inventory import (
    build_structure_inventory,
    classify_declared_role,
    classify_structure_candidate,
    semantic_role_candidates,
)
from .structure_plan import build_structure_plan, canonical_plan_digest

_TERMINAL_STRUCTURE_ROLES = frozenset(SEMANTIC_ROLE_BY_ROOT_ROLE)
_LEGACY_SOURCE_PREFIXES: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "analysis_scripts": (("scripts",), ("hub_scripts",)),
    "figure_scripts": (("scripts",), ("hub_scripts",)),
    "shared_scripts": (("scripts",), ("hub_scripts",)),
    "raw": (("data", "raw"), ("data",), ("raw",)),
    "intermediate": (("work",), ("results", "data")),
    "source_data": (("results", "data"),),
    "tables": (("tables",), ("results", "tables")),
    "figures": (("results", "figures"), ("figures",), ("images",)),
    "evidence": (("results", "evidence"), ("evidence",)),
    "publication": (("results", "publication"), ("publication",)),
}

NORMALIZATION_POLICY_DEPRECATED = "FIGOPS_NORMALIZATION_POLICY_DEPRECATED"
NORMALIZATION_OVERWRITE_DISABLED = "FIGOPS_NORMALIZATION_OVERWRITE_DISABLED"
NORMALIZATION_REVIEW_REQUIRED = "FIGOPS_NORMALIZATION_REVIEW_REQUIRED"
NORMALIZATION_CONFIRMATION_REQUIRED = "FIGOPS_NORMALIZATION_CONFIRMATION_REQUIRED"
NORMALIZATION_PLAN_REJECTED = "FIGOPS_NORMALIZATION_PLAN_REJECTED"
NORMALIZATION_HOST_APPROVAL_REQUIRED = "FIGOPS_NORMALIZATION_HOST_APPROVAL_REQUIRED"
NORMALIZATION_HOST_APPROVAL_REJECTED = "FIGOPS_NORMALIZATION_HOST_APPROVAL_REJECTED"


def plan_scaffold_project(
    *,
    project_root: Path,
    hub_path: Path,
    project_name: str,
    target_format: str,
    template: str,
    conventions=None,
    font_scale: float = 1.0,
) -> dict[str, Any]:
    if template not in {"standard", "researchos"}:
        raise ValueError("template must be 'standard' or 'researchos'.")
    if target_format not in ALLOWED_TARGET_FORMATS:
        raise ValueError(f"Invalid target_format: {target_format}.")

    project_root = _project_root_path(project_root)
    conventions = conventions if conventions is not None else select_adapters({}).conventions
    return build_scaffold_manifest(
        project_root=project_root,
        hub_path=hub_path,
        project_name=project_name,
        target_format=target_format,
        template=template,
        conventions=conventions,
        font_scale=font_scale,
    )


def apply_scaffold_project(manifest: dict[str, Any], *, overwrite: bool) -> dict[str, Any]:
    project_root = _project_root_path(Path(str(manifest["project_root"])))
    entries = list(manifest["entries"])
    manifest_path = _safe_destination(project_root, SCAFFOLD_MANIFEST_FILENAME)
    conflicts = []
    if manifest_path.is_dir() and not manifest_path.is_symlink():
        conflicts.append(manifest_path.name)
    elif _path_occupied(manifest_path) and not overwrite:
        conflicts.append(manifest_path.name)
    for entry in entries:
        destination = _safe_destination(project_root, entry["destination"])
        if entry["kind"] == "directory":
            blocker = _parent_blocker(project_root, destination)
            if blocker:
                conflicts.append(blocker)
            if destination.is_symlink():
                conflicts.append(entry["destination"])
            if _path_occupied(destination) and not destination.is_dir():
                conflicts.append(entry["destination"])
        if entry["kind"] == "file":
            blocker = _parent_blocker(project_root, destination)
            if blocker:
                conflicts.append(blocker)
            if destination.is_dir() and not destination.is_symlink():
                conflicts.append(entry["destination"])
            if _path_occupied(destination):
                if destination.is_dir() or destination.is_symlink():
                    conflicts.append(entry["destination"])
                elif _sha256(destination) != entry.get("checksum"):
                    conflicts.append(entry["destination"])
    if conflicts:
        raise FileExistsError(
            f"Destination already exists: {conflicts[0]}. "
            "Scaffold overwrite never replaces existing config or script content."
        )

    created: list[str] = []
    modified: list[str] = []
    skipped: list[str] = []
    applied_entries: list[dict[str, Any]] = []
    for entry in entries:
        path = _safe_destination(project_root, entry["destination"])
        applied = dict(entry)
        if entry["kind"] == "directory":
            if path.exists():
                applied["status"] = "skipped"
                skipped.append(str(path))
            else:
                path.mkdir(parents=True, exist_ok=True)
                applied["status"] = "created"
                created.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            existed = _path_occupied(path)
            if existed:
                applied["status"] = "skipped"
                skipped.append(str(path))
            else:
                path.write_bytes(str(entry["content"]).encode("utf-8"))
                applied["status"] = "created"
                created.append(str(path))
        applied_entries.append(_without_content(applied))

    if overwrite and _path_occupied(manifest_path):
        _unlink_destination(manifest_path)
    manifest_payload = {**manifest, "entries": applied_entries}
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    created.append(str(manifest_path))
    applied_entries.append(
        {
            "source": "",
            "destination": manifest_path.name,
            "operation": "write_manifest",
            "kind": "file",
            "reason": "scaffold manifest",
            "status": "created",
            "checksum": "",
        }
    )
    manifest_payload["entries"] = applied_entries
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "manifest": manifest_payload,
        "created_paths": created,
        "modified_paths": modified,
        "skipped_paths": skipped,
    }


def plan_normalize_project(
    *,
    project_path: Path,
    move_policy: str = "adopt",
    include_raw: bool = False,
    approved_mappings: list[dict[str, Any]] | None = None,
    config_diff: list[dict[str, Any]] | None = None,
    hardcoded_unresolved_references: list[object] | None = None,
) -> dict[str, Any]:
    """Return a dry-run/adopt plan; mutation requires explicit reviewed mappings."""

    if move_policy in {"move", "symlink"}:
        raise ValueError(
            f"move_policy={move_policy!r} is deprecated and disabled; structure normalization is copy-only."
        )
    if move_policy not in {"adopt", "copy"}:
        raise ValueError("move_policy must be 'adopt' or 'copy'.")
    project_path = _project_root_path(project_path, must_exist_dir=True)
    if move_policy == "copy" and approved_mappings is None:
        raise ValueError("copy normalization requires explicit approved_mappings from a reviewed dry-run.")
    if approved_mappings is not None and not isinstance(approved_mappings, list):
        approved_mappings = list(approved_mappings)
    config, style_config_path = _load_project_config(project_path)
    proposed_mappings, unresolved_proposals = _propose_normalization_mappings(
        project_path,
        config=config,
        include_raw=include_raw,
    )
    approved_sources = {
        source
        for mapping in approved_mappings or []
        if isinstance(mapping, Mapping)
        for source in [mapping.get("source")]
        if isinstance(source, str)
    }
    unresolved_proposals = [
        proposal
        for proposal in unresolved_proposals
        if proposal.get("source") not in approved_sources
    ]
    dependency_blockers = _scan_normalization_script_dependencies(
        project_path,
        config=config,
        proposed_mappings=proposed_mappings,
        approved_mappings=approved_mappings,
    )
    plan = build_structure_plan(
        project_path,
        approved_mappings or [],
        config_diff=config_diff or [],
        hardcoded_unresolved_references=[
            *(hardcoded_unresolved_references or []),
            *dependency_blockers,
        ],
        unresolved_proposals=unresolved_proposals,
    )
    plan.update(
        {
            "mode": "dry_run",
            "adopt_existing": move_policy == "adopt",
            "include_raw": include_raw,
            "proposed_mappings": proposed_mappings,
            "style_summary": _style_summary(style_config_path),
        }
    )
    plan["digest"] = canonical_plan_digest(plan)
    return plan


def apply_normalize_project(
    manifest: dict[str, Any],
    *,
    hub_path: Path | None = None,
    overwrite: bool = False,
    confirmation_token: str | None = None,
    pre_apply_verifier: Callable[[Path, Mapping[str, Any]], None] | None = None,
    post_apply_verifier: Callable[[Path, Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Apply only an immutable copy plan with explicit confirmation."""

    del hub_path
    if overwrite:
        raise ValueError("overwrite is disabled; normalization never replaces existing paths.")
    if confirmation_token is None:
        raise PermissionError("apply requires the reviewed plan and its explicit confirmation token.")
    return apply_structure_plan(
        manifest,
        confirmation_token=confirmation_token,
        pre_apply_verifier=pre_apply_verifier,
        post_apply_verifier=post_apply_verifier,
    )


def _iter_normalization_files(project_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_path.rglob("*"):
        rel_path = path.relative_to(project_path)
        if any(part.startswith(".") or part == "__pycache__" for part in rel_path.parts):
            continue
        if not path.is_file():
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(project_path).as_posix())


def _scan_normalization_script_dependencies(
    project_path: Path,
    *,
    config: Mapping[str, Any],
    proposed_mappings: list[dict[str, Any]],
    approved_mappings: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Collect dependency blockers for the exact script sources under review.

    Static dependency evidence never becomes a role or mapping.  In copy mode,
    only explicitly reviewed script sources are inspected so an unrelated
    legacy script cannot block an otherwise reviewed subset of a project.
    Adopt-mode previews inspect the script candidates that discovery proposed.
    """

    if approved_mappings is not None:
        script_sources = {
            str(mapping["source"])
            for mapping in approved_mappings
            if isinstance(mapping, Mapping)
            and isinstance(mapping.get("source"), str)
            and isinstance(mapping.get("role"), str)
            and mapping["role"].startswith("script.")
        }
    else:
        script_sources = {
            str(mapping["source"])
            for mapping in proposed_mappings
            if isinstance(mapping.get("source"), str)
            and isinstance(mapping.get("role"), str)
            and mapping["role"].startswith("script.")
        }
    if not script_sources:
        return []

    contract = resolve_project_structure(config, project_root=project_path)
    role_roots = dict(contract.roots)
    blockers: list[dict[str, Any]] = []
    for source in sorted(script_sources):
        try:
            script_path = _safe_destination(project_path, source)
            result = analyze_dependency_script(
                script_path,
                script_path=source,
                role_roots=role_roots,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            blockers.append(
                {
                    "kind": "dependency_scan_incomplete",
                    "script": source,
                    "reason": f"dependency scan failed safely: {type(exc).__name__}",
                }
            )
            continue

        for reference in result.get("hardcoded_unresolved_references") or []:
            blocker = dict(reference) if isinstance(reference, Mapping) else {"reference": str(reference)}
            blocker["script"] = source
            blockers.append(blocker)
        if result.get("dependency_scan_incomplete"):
            blockers.append(
                {
                    "kind": "dependency_scan_incomplete",
                    "script": source,
                    "reason": "dependency scan could not inspect the complete script safely.",
                }
            )
    return blockers


def _propose_normalization_mappings(
    project_path: Path,
    *,
    config: Mapping[str, Any],
    include_raw: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return contract-rooted hints without treating classifiers as approvals."""

    contract = resolve_project_structure(config, project_root=project_path)
    roots = dict(contract.roots)
    inventory = build_structure_inventory(project_path, config)
    reference_roles: dict[str, set[str]] = {}
    for edge in inventory["graph"]["edges"]:
        relationship = str(edge["relationship"])
        if relationship in roots:
            reference_roles.setdefault(str(edge["to"]), set()).add(relationship)
    proposed: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for path in _iter_normalization_files(project_path):
        source = path.relative_to(project_path).as_posix()
        if source in {"project_config.yaml", "scripts/project_config.yaml"}:
            continue
        rel_path = Path(source)
        declared_role = classify_declared_role(source, roots)
        if declared_role in _TERMINAL_STRUCTURE_ROLES:
            continue

        candidate = classify_structure_candidate(
            source,
            reference_roles=reference_roles.get(source, ()),
        )
        root_role = str(candidate["candidate_role"])
        reason = str(candidate["reason"])
        confidence = float(candidate["confidence"])
        if root_role == "unknown" and include_raw and any(
            role == "raw" for role, _, _ in semantic_role_candidates(source)
        ):
            root_role = "raw"
            confidence = 0.4
            reason = "include_raw permits a provisional raw-data candidate"
        if root_role not in SEMANTIC_ROLE_BY_ROOT_ROLE:
            if any(role == "raw" for role, _, _ in semantic_role_candidates(source)) and not include_raw:
                reason = "data role is ambiguous and include_raw is false"
            unresolved.append({"source": source, "reason": reason})
            continue
        tail = _normalization_tail(rel_path, root_role=root_role, roots=roots)
        destination = (Path(roots[root_role]) / tail).as_posix()
        proposed.append(
            {
                "source": source,
                "destination": destination,
                "role": SEMANTIC_ROLE_BY_ROOT_ROLE[root_role],
                "confidence": confidence,
                "reason": reason,
                "review_required": True,
            }
        )
    proposed.sort(key=lambda item: (item["destination"], item["source"], item["role"]))
    unresolved.sort(key=lambda item: item["source"])
    return proposed, unresolved


def _normalization_tail(rel_path: Path, *, root_role: str, roots: Mapping[str, str]) -> Path:
    parent_role = "scripts" if root_role.endswith("_scripts") else "results"
    prefixes: list[tuple[str, ...]] = []
    if root_role == "raw":
        prefixes.append(tuple(Path(roots["raw"]).parts))
    elif parent_role in roots:
        prefixes.append(tuple(Path(roots[parent_role]).parts))
    prefixes.extend(_LEGACY_SOURCE_PREFIXES.get(root_role, ()))
    return _tail_after_prefix(rel_path, tuple(prefixes))


def _tail_after_prefix(rel_path: Path, prefixes: tuple[tuple[str, ...], ...]) -> Path:
    parts = rel_path.parts
    for prefix in prefixes:
        if parts[: len(prefix)] == prefix:
            tail_parts = parts[len(prefix) :]
            if tail_parts:
                return Path(*tail_parts)
    return Path(rel_path.name)


def _load_project_config(project_path: Path) -> tuple[Mapping[str, Any], Path]:
    config_path = project_path / "project_config.yaml"
    legacy_config_path = project_path / "scripts" / "project_config.yaml"
    selected = config_path if config_path.exists() else legacy_config_path
    if not selected.exists():
        return {}, selected
    config = load_yaml_with_unique_keys(selected.read_text(encoding="utf-8")) or {}
    if not isinstance(config, Mapping):
        # Preserve diagnostic-only planning for malformed legacy projects.  No
        # proposal can be applied without a separately reviewed mapping/token,
        # and normal config validation still reports this source as invalid.
        return {}, selected
    return config, selected


def _style_summary(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {"target_format": "nature", "profile": "baseline", "presets": [], "style_update_applied": False}
    try:
        config = load_yaml_with_unique_keys(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"target_format": "unknown", "profile": "unknown", "presets": [], "style_update_applied": False}
    if not isinstance(config, dict):
        return {"target_format": "unknown", "profile": "unknown", "presets": [], "style_update_applied": False}
    visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
    presets = config.get("presets") if isinstance(config.get("presets"), dict) else {}
    return {
        "target_format": str(visual_style.get("target_format") or "nature"),
        "profile": str(visual_style.get("profile") or "baseline"),
        "presets": sorted(str(key) for key in presets),
        "style_update_applied": False,
    }


def _safe_destination(project_root: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute():
        raise ValueError("Normalization destination must be relative.")
    if any(part == ".." for part in rel.parts):
        raise ValueError("Normalization destination must stay inside the project root.")
    project_root = _project_root_path(project_root)
    if rel == Path(".") or str(rel) == "":
        return project_root
    destination = Path(os.path.abspath(os.fspath(project_root / rel)))
    destination.relative_to(project_root)
    return destination


def _path_occupied(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _parent_blocker(project_root: Path, destination: Path) -> str | None:
    project_root = _project_root_path(project_root)
    destination = Path(os.path.abspath(os.fspath(destination)))
    if destination == project_root:
        return None
    parent = destination.parent
    while parent != project_root:
        if parent.is_symlink() or (_path_occupied(parent) and not parent.is_dir()):
            return parent.relative_to(project_root).as_posix()
        if parent == parent.parent:
            return str(parent)
        parent = parent.parent
    return None


def _project_root_path(project_root: Path, *, must_exist_dir: bool = False) -> Path:
    root = Path(os.path.abspath(os.fspath(project_root.expanduser())))
    _reject_symlinked_project_boundary(root)
    if must_exist_dir and not root.is_dir():
        raise ValueError("project_path must be an existing directory.")
    return root


def _reject_symlinked_project_boundary(project_root: Path) -> None:
    current = Path(project_root.anchor)
    for part in project_root.parts[1:]:
        current = current / part
        if _is_macos_private_mount_alias(current):
            continue
        if current.is_symlink():
            raise ValueError(f"Project root must not be a symlink or below a symlink: {current}")
        if not current.exists():
            break


def _is_macos_private_mount_alias(path: Path) -> bool:
    if os.name != "posix":
        return False
    try:
        if os.uname().sysname != "Darwin":
            return False
    except AttributeError:
        return False
    aliases = {
        Path("/var"): Path("/private/var"),
        Path("/tmp"): Path("/private/tmp"),
        Path("/etc"): Path("/private/etc"),
    }
    target = aliases.get(path)
    if target is None:
        return False
    return path.is_symlink() and Path(os.path.realpath(path)) == target


def _unlink_destination(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        raise FileExistsError(f"Destination is a directory: {path}")
    path.unlink()


def _without_content(entry: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(entry)
    stripped.pop("content", None)
    return stripped


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
