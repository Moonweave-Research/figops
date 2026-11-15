"""Read-only, declared-first project structure inventory.

The inventory deliberately reports evidence; it does not plan or perform a
migration.  Declared role roots and config relationships take precedence over
name-based candidate classification.
"""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Any, Generator, Iterable, Mapping

from .project_paths import project_path_has_symlink_component
from .project_structure_contract import resolve_project_structure
from .structure_contract_types import ROLE_ROOTS

_SCRIPT_SUFFIXES = frozenset({".py", ".r", ".rmd", ".qmd", ".ipynb"})
_DATA_SUFFIXES = frozenset(
    {".csv", ".tsv", ".txt", ".parquet", ".json", ".xlsx", ".xls", ".h5", ".hdf5", ".feather"}
)
_FIGURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".svg", ".pdf", ".eps", ".tif", ".tiff"})
DEFAULT_INVENTORY_MAX_ENTRIES = 10_000
_PATH_REFERENCE_KEYS = frozenset(
    {
        "asset",
        "assets",
        "file",
        "files",
        "input",
        "inputs",
        "lock",
        "locks",
        "manifest",
        "manifests",
        "output",
        "outputs",
        "path",
        "paths",
        "script",
        "scripts",
        "source",
        "sources",
    }
)


def _relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts or ":" in path.parts[0]:
        return None
    return path.as_posix()


def _is_configured_path(trail: tuple[str, ...]) -> bool:
    """Return whether the scalar sits under a path-bearing config key.

    Config metadata contains many dotted strings (schema versions, helper
    module names, and prose descriptions) that look like paths to a generic
    suffix check.  Explicit path-bearing keys remain the authoritative signal,
    including lock-file keys such as ``environment.python_lock``.
    """

    return any(
        (key := part.lower()) in _PATH_REFERENCE_KEYS or key.endswith("_lock")
        for part in trail
    )


def _walk_references(value: object, trail: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _walk_references(value[key], (*trail, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_references(item, (*trail, str(index)))
    else:
        path = _relative_path(value)
        if path is not None and _is_configured_path(trail):
            yield trail, path


def _reference_role(trail: tuple[str, ...], path: str) -> str | None:
    keys = {part.lower() for part in trail}
    suffix = PurePosixPath(path).suffix.lower()
    if "script" in keys:
        if "figures" in keys or "diagrams" in keys:
            return "figure_scripts"
        if "analysis" in keys or "pipeline" in keys:
            return "analysis_scripts"
        return "shared_scripts"
    if "output" in keys or "outputs" in keys:
        if "figures" in keys or "diagrams" in keys or suffix in _FIGURE_SUFFIXES:
            return "figures"
        if "tables" in keys:
            return "tables"
        return "intermediate"
    if "inputs" in keys or "input" in keys or "path" in keys:
        return "raw"
    return None


def _record_scope(trail: tuple[str, ...]) -> tuple[str, ...]:
    """Identify the enclosing configured pipeline/output record."""

    numeric = [index for index, part in enumerate(trail) if part.isdigit()]
    return trail[: numeric[-1] + 1] if numeric else trail[:-1]


def classify_declared_role(path: str, roots: Mapping[str, str]) -> str | None:
    """Return the most-specific declared role owning *path*, if any."""

    parts = PurePosixPath(path).parts
    matches = [
        role
        for role, root in roots.items()
        if parts[: len(PurePosixPath(root).parts)] == PurePosixPath(root).parts
    ]
    if not matches:
        return None
    return max(matches, key=lambda role: (len(PurePosixPath(roots[role]).parts), role))


def semantic_role_candidates(path: str) -> tuple[tuple[str, float, str], ...]:
    """Return deterministic extension/name candidates without choosing a winner."""

    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(path).suffix.lower()
    candidates: list[tuple[str, float, str]] = []
    if suffix in _SCRIPT_SUFFIXES:
        if any(token in name for token in ("plot", "figure", "chart", "diagram")):
            candidates.append(("figure_scripts", 0.75, "script name indicates figure production"))
        if any(token in name for token in ("analys", "model", "fit", "stat", "process")):
            candidates.append(("analysis_scripts", 0.75, "script name indicates analysis"))
        if not candidates:
            candidates.extend(
                [
                    ("analysis_scripts", 0.4, "script extension permits analysis"),
                    ("figure_scripts", 0.4, "script extension permits figure production"),
                    ("shared_scripts", 0.4, "script extension permits shared code"),
                ]
            )
    elif suffix in _FIGURE_SUFFIXES:
        candidates.append(("figures", 0.7, "rendered-artifact extension"))
    elif suffix in _DATA_SUFFIXES:
        candidates.extend(
            [
                ("raw", 0.4, "data extension permits an input"),
                ("intermediate", 0.4, "data extension permits a derived artifact"),
                ("source_data", 0.4, "data extension permits publication source data"),
            ]
        )
    return tuple(candidates)


def classify_structure_candidate(
    path: str, *, reference_roles: Iterable[str] = ()
) -> dict[str, object]:
    """Classify a path with config-reference semantics before name heuristics."""

    declared = sorted({role for role in reference_roles if role in ROLE_ROOTS})
    if len(declared) == 1:
        return {
            "candidate_role": declared[0],
            "confidence": 1.0,
            "reason": "configured relationship declares the semantic role",
        }
    if len(declared) > 1:
        return {
            "candidate_role": "unknown",
            "confidence": 1.0,
            "reason": f"ambiguous configured relationships: {', '.join(declared)}",
        }

    candidates = semantic_role_candidates(path)
    if not candidates:
        return {"candidate_role": "unknown", "confidence": 0.0, "reason": "no semantic declaration"}
    best = max(score for _, score, _ in candidates)
    winners = [item for item in candidates if item[1] == best]
    if len(winners) != 1:
        roles = ", ".join(sorted(role for role, _, _ in winners))
        return {"candidate_role": "unknown", "confidence": best, "reason": f"ambiguous candidates: {roles}"}
    role, confidence, reason = winners[0]
    return {"candidate_role": role, "confidence": confidence, "reason": reason}


def _active_config_path(project_root: Path, config_path: str | Path | None) -> str:
    """Return the active config path relative to *project_root* when contained.

    A layout audit is diagnostic-only and must never follow an arbitrary
    caller-provided config path outside the project.  Falling back to the
    canonical root config keeps direct callers deterministic.
    """

    candidate = project_root / "project_config.yaml" if config_path is None else Path(config_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve(strict=False).relative_to(project_root).as_posix()
    except ValueError:
        return "project_config.yaml"


def _scan_inventory_entries(
    root: Path,
    roots: Mapping[str, str],
    *,
    max_entries: int,
) -> tuple[dict[str, str], bool]:
    """Share one bounded budget across declared roles without starving small roots."""

    entries: dict[str, str] = {}
    declared_roots = {PurePosixPath(path) for path in roots.values()}

    def scan_directory(
        directory: Path, prefix: PurePosixPath
    ) -> Generator[tuple[str, str], None, None]:
        if prefix != PurePosixPath("."):
            yield prefix.as_posix(), "directory"
        pending = [(directory, prefix)]
        while pending:
            current, current_prefix = pending.pop()
            child_directories: list[tuple[Path, PurePosixPath]] = []
            with os.scandir(current) as iterator:
                for entry in iterator:
                    if entry.is_symlink():
                        continue
                    relative = current_prefix / entry.name
                    if entry.is_file(follow_symlinks=False):
                        yield relative.as_posix(), "file"
                    elif entry.is_dir(follow_symlinks=False):
                        yield relative.as_posix(), "directory"
                        # Nested declared roots have their own scan lane.
                        if relative not in declared_roots:
                            child_directories.append((Path(entry.path), relative))
            pending.extend(reversed(child_directories))

    scans = []
    for relative_root in sorted(declared_roots):
        declared_root = root / relative_root
        if not declared_root.is_dir() or (
            relative_root != PurePosixPath(".")
            and project_path_has_symlink_component(root, relative_root.as_posix())
        ):
            continue
        scans.append(scan_directory(declared_root, relative_root))

    def scan_immediate_entries() -> Generator[tuple[str, str], None, None]:
        with os.scandir(root) as iterator:
            for entry in iterator:
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False):
                    yield entry.name, "file"
                elif entry.is_dir(follow_symlinks=False):
                    yield entry.name, "directory"

    if root.is_dir() and PurePosixPath(".") not in declared_roots:
        scans.append(scan_immediate_entries())
    active = deque(scans)
    try:
        while active:
            scan = active.popleft()
            try:
                relative, kind = next(scan)
            except StopIteration:
                continue
            if relative not in entries:
                if len(entries) >= max_entries:
                    return entries, True
                entries[relative] = kind
            active.append(scan)
    finally:
        for scan in scans:
            scan.close()
    return entries, False


def build_structure_inventory(
    project_root: str | Path,
    config: Mapping[str, Any],
    *,
    config_path: str | Path | None = None,
    max_entries: int = DEFAULT_INVENTORY_MAX_ENTRIES,
) -> dict[str, Any]:
    """Build a deterministic, read-only inventory and relationship graph."""

    if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
        raise ValueError("max_entries must be a positive integer")

    root = Path(project_root).resolve()
    contract = resolve_project_structure(config, project_root=root)
    roots = dict(contract.roots)
    active_config_path = _active_config_path(root, config_path)
    entry_kinds, inventory_truncated = _scan_inventory_entries(root, roots, max_entries=max_entries)

    all_references = list(_walk_references(config))
    references: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    for trail, path in all_references:
        references.setdefault(path, []).append((trail, _reference_role(trail, path) or ""))

    for path in references:
        if path in entry_kinds:
            continue
        candidate = root / path
        if candidate.is_symlink():
            continue
        if candidate.is_file():
            entry_kinds[path] = "file"
        elif candidate.is_dir():
            entry_kinds[path] = "directory"

    for path, kind in tuple(entry_kinds.items()):
        if kind != "directory" or "/" in path or classify_declared_role(path, roots) is not None:
            continue
        nested_config = root / path / "project_config.yaml"
        if nested_config.is_file():
            entry_kinds[f"{path}/project_config.yaml"] = "file"

    entries = sorted(entry_kinds.items())
    files = sorted(path for path, kind in entries if kind == "file")

    roles = {
        role: {
            "root": roots[role],
            "declared": True,
            "exists": (root / roots[role]).is_dir(),
            "paths": [],
        }
        for role in ROLE_ROOTS
    }
    nested_project_configs = [
        path
        for path in files
        if PurePosixPath(path).name == "project_config.yaml" and path != active_config_path
    ]
    nested_config_set = set(nested_project_configs)
    unknowns: list[dict[str, Any]] = []
    for path, kind in entries:
        role = classify_declared_role(path, roots)
        if role is None:
            if path != active_config_path and path not in nested_config_set:
                unknowns.append(
                    {
                        "path": path,
                        "kind": kind,
                        "candidate": classify_structure_candidate(
                            path,
                            reference_roles=(role for _, role in references.get(path, [])),
                        ),
                    }
                )
        elif kind == "file":
            roles[role]["paths"].append(path)

    nodes = [
        {
            "id": path,
            "role": classify_declared_role(path, roots) or "unknown",
            "exists": path in entry_kinds or (root / path).is_file(),
        }
        for path in sorted(set(files) | set(references))
    ]
    edges: list[dict[str, str]] = []
    for path, refs in sorted(references.items()):
        for trail, expected_role in refs:
            edges.append(
                {"from": "config:" + ".".join(trail), "to": path, "relationship": expected_role or "references"}
            )

    findings: list[dict[str, Any]] = []
    if inventory_truncated:
        findings.append(
            {"code": "inventory_entry_limit", "entry_count": max_entries, "max_entries": max_entries}
        )
    for role in ROLE_ROOTS:
        if not roles[role]["exists"]:
            findings.append(
                {"code": "missing_declared", "role": role, "path": roots[role], "expected_kind": "directory"}
            )

    for path in nested_project_configs:
        findings.append(
            {
                "code": "nested_project_config",
                "path": path,
                "active_config_path": active_config_path,
            }
        )

    seen_roots: dict[str, str] = {}
    for role, declared_root in sorted(roots.items()):
        if declared_root in seen_roots:
            findings.append(
                {"code": "collision", "path": declared_root, "roles": sorted([seen_roots[declared_root], role])}
            )
        seen_roots[declared_root] = role

    for path, refs in sorted(references.items()):
        expected = {role for _, role in refs}
        if expected & {"figures", "tables", "intermediate"}:
            if classify_declared_role(path, roots) == "raw":
                findings.append({"code": "raw_output", "path": path})
            if not (root / path).is_file():
                findings.append({"code": "stale_reference", "path": path})
            complete = False
            for output_trail, role in refs:
                if role not in {"figures", "tables", "intermediate"}:
                    continue
                scope = _record_scope(output_trail)
                sibling_keys = {
                    part.lower()
                    for trail, _ in all_references
                    if trail[: len(scope)] == scope
                    for part in trail[len(scope) :]
                }
                if "script" in sibling_keys and ({"input", "inputs"} & sibling_keys):
                    complete = True
            if not complete:
                findings.append({"code": "provenance_incomplete", "path": path})
        elif not ((root / path).is_dir() if path in roots.values() else (root / path).is_file()):
            findings.append({"code": "stale_reference", "path": path})

    result_roles = {"intermediate", "source_data", "tables", "figures", "evidence", "publication"}
    for path in files:
        if classify_declared_role(path, roots) in result_roles and path not in references:
            findings.append({"code": "orphan", "path": path})

    if inventory_truncated:
        for finding in findings:
            if finding["code"] == "orphan":
                finding["provisional"] = True
        for unknown in unknowns:
            unknown["provisional"] = True
            unknown["candidate"]["reason"] = "Partial inventory: " + unknown["candidate"]["reason"]

    findings.sort(key=lambda item: (str(item.get("code")), str(item.get("path")), str(item.get("role"))))
    declared_roots = [
        {
            "role": role,
            "path": roots[role],
            "exists": roles[role]["exists"],
            "expected_kind": "directory",
        }
        for role in ROLE_ROOTS
    ]
    return {
        "contract": contract.to_dict(),
        "roles": roles,
        "graph": {"nodes": nodes, "edges": edges},
        "findings": findings,
        "unknowns": unknowns,
        "declared_vs_actual": {
            "inventory_complete": not inventory_truncated,
            "active_config_path": active_config_path,
            "declared_roots": declared_roots,
            "undeclared_paths": list(unknowns),
            "nested_project_configs": nested_project_configs,
        },
    }


inventory_project_structure = build_structure_inventory
