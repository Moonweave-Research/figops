from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from .adapters import select_adapters
from .config_parser import ALLOWED_TARGET_FORMATS, load_yaml_with_unique_keys, validate_config
from .scaffold import (
    DEFAULT_ANALYZE_R,
    DEFAULT_CONFIG_TEMPLATE,
    DEFAULT_DIAGRAM_PY,
    DEFAULT_PLOT_PY,
    DEFAULT_PROJECT_CONTEXT_PY,
)

MANIFEST_FILENAME = ".figops_normalization_manifest.json"
SCAFFOLD_MANIFEST_FILENAME = ".figops_scaffold_manifest.json"

_SCRIPT_SUFFIXES = {".py", ".r"}
_DATA_SUFFIXES = {".csv", ".tsv", ".txt", ".parquet", ".h5", ".hdf5", ".feather"}
_FIGURE_SUFFIXES = {".png", ".pdf", ".svg", ".tif", ".tiff", ".eps", ".jpg", ".jpeg"}
_DOC_SUFFIXES = {".md", ".rst"}


def plan_scaffold_project(
    *,
    project_root: Path,
    hub_path: Path,
    project_name: str,
    target_format: str,
    template: str,
    conventions=None,
) -> dict[str, Any]:
    if template not in {"standard", "researchos"}:
        raise ValueError("template must be 'standard' or 'researchos'.")
    if target_format not in ALLOWED_TARGET_FORMATS:
        raise ValueError(f"Invalid target_format: {target_format}.")

    project_root = _project_root_path(project_root)
    conventions = conventions if conventions is not None else select_adapters({}).conventions
    config = _scaffold_config(hub_path, project_name, target_format)
    entries = _scaffold_entries(project_root, config, conventions=conventions)
    return {
        "operation": "scaffold_project",
        "project_root": str(project_root),
        "project_name": project_name,
        "template": template,
        "entries": entries,
    }


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
            if _path_occupied(destination) and not overwrite:
                conflicts.append(entry["destination"])
    if conflicts:
        raise FileExistsError(f"Destination already exists: {conflicts[0]}. Set overwrite=true to replace it.")

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
            if overwrite and existed:
                _unlink_destination(path)
            path.write_text(str(entry["content"]), encoding="utf-8")
            applied["status"] = "modified" if existed else "created"
            (modified if existed else created).append(str(path))
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
    move_policy: str,
    include_raw: bool,
) -> dict[str, Any]:
    if move_policy not in {"copy", "move", "symlink"}:
        raise ValueError("move_policy must be one of: copy, move, symlink.")
    project_path = _project_root_path(project_path, must_exist_dir=True)

    entries: list[dict[str, Any]] = []
    for path in _iter_normalization_files(project_path):
        rel_source = path.relative_to(project_path).as_posix()
        if rel_source in {"project_config.yaml", "scripts/project_config.yaml"}:
            continue
        destination, reason, operation = _normalization_destination(
            Path(rel_source), include_raw=include_raw, move_policy=move_policy
        )
        if destination is None:
            entries.append(
                {
                    "source": rel_source,
                    "destination": "",
                    "operation": "skip",
                    "kind": "file",
                    "reason": reason,
                    "status": "planned",
                    "checksum": _sha256(path),
                }
            )
            continue
        entries.append(
            {
                "source": rel_source,
                "destination": destination,
                "operation": operation,
                "kind": "file",
                "reason": reason,
                "status": "planned",
                "checksum": _sha256(path),
            }
        )

    config_path = project_path / "project_config.yaml"
    legacy_config_path = project_path / "scripts" / "project_config.yaml"
    style_config_path = config_path if config_path.exists() else legacy_config_path
    if not config_path.exists() and legacy_config_path.exists():
        entries.append(
            {
                "source": "scripts/project_config.yaml",
                "destination": "project_config.yaml",
                "operation": "copy",
                "kind": "file",
                "reason": "preserve legacy scripts/project_config.yaml",
                "status": "planned",
                "checksum": _sha256(legacy_config_path),
            }
        )
    elif not config_path.exists():
        entries.append(
            {
                "source": "",
                "destination": "project_config.yaml",
                "operation": "create_config",
                "kind": "file",
                "reason": "missing project_config.yaml",
                "status": "planned",
                "checksum": "",
            }
        )
    if not (project_path / "hub_scripts" / "project_context.py").exists():
        entries.append(
            {
                "source": "",
                "destination": "hub_scripts/project_context.py",
                "operation": "create_project_context",
                "kind": "file",
                "reason": "missing env-first project_context.py with theme font tokens",
                "status": "planned",
                "checksum": hashlib.sha256(DEFAULT_PROJECT_CONTEXT_PY.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "operation": "normalize_project_structure",
        "project_root": str(project_path),
        "move_policy": move_policy,
        "include_raw": include_raw,
        "entries": entries,
        "style_summary": _style_summary(style_config_path),
    }


def apply_normalize_project(manifest: dict[str, Any], *, hub_path: Path, overwrite: bool) -> dict[str, Any]:
    project_root = _project_root_path(Path(str(manifest["project_root"])))
    entries = list(manifest["entries"])
    conflicts = []
    manifest_path = _safe_destination(project_root, MANIFEST_FILENAME)
    if manifest_path.is_dir() and not manifest_path.is_symlink():
        conflicts.append(manifest_path.name)
    elif _path_occupied(manifest_path) and not overwrite:
        conflicts.append(manifest_path.name)
    conflicts.extend(_manifest_destination_collisions(entries))
    for entry in entries:
        if entry["operation"] == "skip":
            continue
        destination = _safe_destination(project_root, entry["destination"])
        source = _safe_destination(project_root, entry["source"]) if entry["source"] else None
        same_path = source is not None and _same_path(destination, source)
        blocker = _parent_blocker(project_root, destination)
        if blocker:
            conflicts.append(blocker)
        if destination.is_dir() and not destination.is_symlink():
            conflicts.append(entry["destination"])
        if _path_occupied(destination) and not same_path and not overwrite:
            conflicts.append(entry["destination"])
    if conflicts:
        raise FileExistsError(f"Destination already exists: {conflicts[0]}. Set overwrite=true to replace it.")

    created: list[str] = []
    modified: list[str] = []
    skipped: list[str] = []
    applied_entries: list[dict[str, Any]] = []
    for entry in entries:
        applied = dict(entry)
        if entry["operation"] == "skip":
            skipped.append(entry["source"])
            applied["status"] = "skipped"
            applied_entries.append(applied)
            continue

        destination = _safe_destination(project_root, entry["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        existed = _path_occupied(destination)
        if entry["operation"] == "create_config":
            if overwrite and existed:
                _unlink_destination(destination)
            config = _scaffold_config(hub_path, project_root.name, "nature")
            destination.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
        elif entry["operation"] == "create_project_context":
            if overwrite and existed:
                _unlink_destination(destination)
            destination.write_text(DEFAULT_PROJECT_CONTEXT_PY, encoding="utf-8")
        else:
            source = _safe_destination(project_root, entry["source"])
            if _same_path(destination, source):
                skipped.append(str(destination))
                applied["status"] = "skipped"
                applied_entries.append(applied)
                continue
            if overwrite and existed:
                _unlink_destination(destination)
            if entry["operation"] == "copy":
                shutil.copy2(source, destination)
            elif entry["operation"] == "move":
                shutil.move(str(source), str(destination))
            elif entry["operation"] == "symlink":
                try:
                    Path(source).resolve().relative_to(project_root.resolve())
                except ValueError as exc:
                    raise ValueError("Normalization symlink source must stay inside the project root.") from exc
                os.symlink(source, destination)
        applied["status"] = "modified" if existed else "created"
        applied["checksum"] = _sha256(destination) if destination.exists() else applied.get("checksum", "")
        (modified if existed else created).append(str(destination))
        applied_entries.append(applied)

    if overwrite and _path_occupied(manifest_path):
        _unlink_destination(manifest_path)
    manifest_payload = {
        **manifest,
        "entries": applied_entries,
        "style_summary": _style_summary(project_root / "project_config.yaml"),
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    created.append(str(manifest_path))
    return {
        "manifest": manifest_payload,
        "created_paths": created,
        "modified_paths": modified,
        "skipped_paths": skipped,
    }


def _scaffold_config(hub_path: Path, project_name: str, target_format: str) -> dict[str, Any]:
    template_path = hub_path.expanduser().resolve() / DEFAULT_CONFIG_TEMPLATE
    if not template_path.exists():
        raise RuntimeError(f"Missing scaffold template: {template_path}")
    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    config["project"]["name"] = project_name.strip()
    config["visual_style"]["target_format"] = target_format
    errors = validate_config(config)
    if errors:
        raise ValueError(f"Generated scaffold config is invalid: {errors}")
    return config


def _scaffold_entries(project_root: Path, config: dict[str, Any], *, conventions) -> list[dict[str, Any]]:
    directories = [
        ".",
        "raw",
        "work",
        "results/data",
        "results/figures",
        "results/final",
        "docs",
        "archive",
        "hub_scripts",
        "hub_scripts/diagrams",
    ]
    files = {
        "project_config.yaml": yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        "hub_scripts/analyze.R": DEFAULT_ANALYZE_R,
        "hub_scripts/project_context.py": DEFAULT_PROJECT_CONTEXT_PY,
        "hub_scripts/plot.py": DEFAULT_PLOT_PY,
        "hub_scripts/diagrams/device_cross_section.py": DEFAULT_DIAGRAM_PY,
    }
    entries = [
        {
            "source": "",
            "destination": rel_path,
            "operation": "mkdir",
            "kind": "directory",
            "reason": conventions.scaffold_directory_reason(),
            "status": "planned",
            "checksum": "",
        }
        for rel_path in directories
    ]
    entries.extend(
        {
            "source": "",
            "destination": rel_path,
            "operation": "write",
            "kind": "file",
            "reason": conventions.scaffold_file_reason(),
            "status": "planned",
            "checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
        }
        for rel_path, content in files.items()
    )
    for entry in entries:
        _safe_destination(project_root, entry["destination"])
    return entries


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


def _normalization_destination(rel_path: Path, *, include_raw: bool, move_policy: str) -> tuple[str | None, str, str]:
    suffix = rel_path.suffix.lower()
    if suffix in _SCRIPT_SUFFIXES:
        tail = _tail_after_prefix(rel_path, (("scripts",), ("hub_scripts",)))
        return (Path("hub_scripts") / tail).as_posix(), "script moved into hub_scripts", move_policy
    if suffix in _DATA_SUFFIXES:
        if rel_path.parts[:2] == ("results", "data"):
            tail = _tail_after_prefix(rel_path, (("results", "data"),))
            return (Path("results/data") / tail).as_posix(), "existing result table preserved", "copy"
        if rel_path.parts[:1] == ("work",):
            tail = _tail_after_prefix(rel_path, (("work",),))
            return (Path("results/data") / tail).as_posix(), "derived table preserved", "copy"
        if not include_raw:
            return None, "raw/data input excluded by include_raw=false", "skip"
        tail = _tail_after_prefix(rel_path, (("data", "raw"), ("data",), ("raw",)))
        return (Path("raw") / tail).as_posix(), "raw/data input preserved", "copy"
    if suffix in _FIGURE_SUFFIXES:
        tail = _tail_after_prefix(rel_path, (("results", "figures"), ("figures",), ("images",)))
        return (Path("results/figures") / tail).as_posix(), "existing figure preserved", move_policy
    if suffix in _DOC_SUFFIXES:
        tail = _tail_after_prefix(rel_path, (("docs",),))
        return (Path("docs") / tail).as_posix(), "documentation preserved", move_policy
    return None, "unrecognized file type", "skip"


def _tail_after_prefix(rel_path: Path, prefixes: tuple[tuple[str, ...], ...]) -> Path:
    parts = rel_path.parts
    for prefix in prefixes:
        if parts[: len(prefix)] == prefix:
            tail_parts = parts[len(prefix) :]
            if tail_parts:
                return Path(*tail_parts)
    return Path(rel_path.name)


def _manifest_destination_collisions(entries: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for entry in entries:
        if entry["operation"] == "skip":
            continue
        destination = str(entry.get("destination") or "")
        source = str(entry.get("source") or "")
        if not destination:
            continue
        previous_source = seen.get(destination)
        if previous_source is not None and previous_source != source:
            collisions.append(destination)
            continue
        seen[destination] = source
    return collisions


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


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


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
