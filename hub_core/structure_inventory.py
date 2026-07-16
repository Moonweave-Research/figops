"""Read-only, declared-first project structure inventory.

The inventory deliberately reports evidence; it does not plan or perform a
migration.  Declared role roots and config relationships take precedence over
name-based candidate classification.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .project_structure_contract import resolve_project_structure
from .structure_contract_types import ROLE_ROOTS

_SCRIPT_SUFFIXES = frozenset({".py", ".r", ".rmd", ".qmd", ".ipynb"})
_DATA_SUFFIXES = frozenset(
    {".csv", ".tsv", ".txt", ".parquet", ".json", ".xlsx", ".xls", ".h5", ".hdf5", ".feather"}
)
_FIGURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".svg", ".pdf", ".eps", ".tif", ".tiff"})


def _relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts or ":" in path.parts[0]:
        return None
    return path.as_posix()


def _walk_references(value: object, trail: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _walk_references(value[key], (*trail, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_references(item, (*trail, str(index)))
    else:
        path = _relative_path(value)
        if path is not None and ("/" in path or PurePosixPath(path).suffix):
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


def build_structure_inventory(project_root: str | Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic, read-only inventory and relationship graph."""

    root = Path(project_root).resolve()
    contract = resolve_project_structure(config, project_root=root)
    roots = dict(contract.roots)
    files: list[str] = []
    if root.is_dir():
        for item in root.rglob("*"):
            if item.is_file() and not item.is_symlink():
                files.append(item.relative_to(root).as_posix())
    files.sort()

    all_references = list(_walk_references(config))
    references: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    for trail, path in all_references:
        references.setdefault(path, []).append((trail, _reference_role(trail, path) or ""))

    roles = {
        role: {
            "root": roots[role],
            "declared": True,
            "exists": (root / roots[role]).is_dir(),
            "paths": [],
        }
        for role in ROLE_ROOTS
    }
    unknowns: list[dict[str, Any]] = []
    for path in files:
        role = classify_declared_role(path, roots)
        if role is None:
            if path not in {"project_config.yaml", "scripts/project_config.yaml"}:
                unknowns.append(
                    {
                        "path": path,
                        "candidate": classify_structure_candidate(
                            path,
                            reference_roles=(role for _, role in references.get(path, [])),
                        ),
                    }
                )
        else:
            roles[role]["paths"].append(path)

    nodes = [
        {
            "id": path,
            "role": classify_declared_role(path, roots) or "unknown",
            "exists": (root / path).is_file(),
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
    for role in ROLE_ROOTS:
        if not roles[role]["exists"]:
            findings.append({"code": "missing_declared", "role": role, "path": roots[role]})

    seen_roots: dict[str, str] = {}
    for role, declared_root in sorted(roots.items()):
        if declared_root in seen_roots:
            findings.append(
                {"code": "collision", "path": declared_root, "roles": sorted([seen_roots[declared_root], role])}
            )
        seen_roots[declared_root] = role

    referenced_outputs: set[str] = set()
    for path, refs in sorted(references.items()):
        expected = {role for _, role in refs}
        if expected & {"figures", "tables", "intermediate"}:
            referenced_outputs.add(path)
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
        elif not (root / path).is_file():
            findings.append({"code": "stale_reference", "path": path})

    result_roles = {"intermediate", "source_data", "tables", "figures", "evidence", "publication"}
    for path in files:
        if classify_declared_role(path, roots) in result_roles and path not in referenced_outputs:
            findings.append({"code": "orphan", "path": path})

    findings.sort(key=lambda item: (str(item.get("code")), str(item.get("path")), str(item.get("role"))))
    return {
        "contract": contract.to_dict(),
        "roles": roles,
        "graph": {"nodes": nodes, "edges": edges},
        "findings": findings,
        "unknowns": unknowns,
    }


inventory_project_structure = build_structure_inventory
