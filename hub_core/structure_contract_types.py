"""Closed value types for the FigOps project-structure contract.

This module deliberately performs no filesystem writes.  It is the small,
dependency-free contract shared by config loading, migration, and auditing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

LEGACY_CONTRACT_VERSION = "1.0"
CURRENT_CONTRACT_VERSION = "1.1"
CURRENT_CONTRACT = "figops-project-v1.1"

TOP_LEVEL_ROLES = ("raw", "scripts", "results")
SCRIPT_ROLES = ("analysis_scripts", "figure_scripts", "shared_scripts")
RESULT_ROLES = (
    "intermediate",
    "source_data",
    "tables",
    "figures",
    "evidence",
    "publication",
)
ROLE_ROOTS = TOP_LEVEL_ROLES + SCRIPT_ROLES + RESULT_ROLES
RUNTIME_ROLE = "runtime"
FORBIDDEN_ALIAS_ROLES = TOP_LEVEL_ROLES + (RUNTIME_ROLE,)
CANONICAL_PROJECT_ROLES = (
    "raw",
    "script.analysis",
    "script.figure",
    "script.shared",
    "result.intermediate",
    "result.source_data",
    "result.table",
    "result.figure",
    "result.evidence",
    "result.publication",
    "runtime.*",
)

# Public semantic names are derived from structure roles in one place so
# scaffold, inventory, normalization, and migration do not each invent a path
# layout or vocabulary.
SEMANTIC_ROLE_BY_ROOT_ROLE = MappingProxyType(
    {
        "raw": "raw",
        "analysis_scripts": "script.analysis",
        "figure_scripts": "script.figure",
        "shared_scripts": "script.shared",
        "intermediate": "result.intermediate",
        "source_data": "result.source_data",
        "tables": "result.table",
        "figures": "result.figure",
        "evidence": "result.evidence",
        "publication": "result.publication",
    }
)

ALLOWED_ROLE_PARENTS = MappingProxyType(
    {
        "raw": "project",
        "scripts": "project",
        "results": "project",
        "analysis_scripts": "scripts",
        "figure_scripts": "scripts",
        "shared_scripts": "scripts",
        "intermediate": "results",
        "source_data": "results",
        "tables": "results",
        "figures": "results",
        "evidence": "results",
        "publication": "results",
    }
)
ROLE_NESTING_DAG = MappingProxyType(
    {
        "project": frozenset(TOP_LEVEL_ROLES),
        "scripts": frozenset(SCRIPT_ROLES),
        "results": frozenset(RESULT_ROLES),
    }
)

DEFAULT_V11_ROOTS = MappingProxyType(
    {
        "raw": "raw",
        "scripts": "hub_scripts",
        "analysis_scripts": "hub_scripts/analysis",
        "figure_scripts": "hub_scripts/figures",
        "shared_scripts": "hub_scripts/shared",
        "results": "results",
        "intermediate": "results/data/intermediate",
        "source_data": "results/data/source",
        "tables": "results/tables",
        "figures": "results/figures",
        "evidence": "results/evidence",
        "publication": "results/publication",
    }
)


class StructureContractError(ValueError):
    """A project role declaration violates the closed v1.1 contract."""


def _normalize_relative_path(value: object, role: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StructureContractError(f"structure.roots.{role} must be a non-empty relative path")
    text = value.strip().replace("\\", "/")
    path = PurePosixPath(text)
    if not path.parts or path.is_absolute() or ":" in path.parts[0] or ".." in path.parts:
        raise StructureContractError(f"structure.roots.{role} must be project-relative and contained")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise StructureContractError(f"structure.roots.{role} may not name the project root")
    return normalized


def _is_descendant(child: str, parent: str) -> bool:
    child_parts = PurePosixPath(child).parts
    parent_parts = PurePosixPath(parent).parts
    return len(child_parts) > len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts


def _overlap(left: str, right: str) -> bool:
    return left == right or _is_descendant(left, right) or _is_descendant(right, left)


def validate_forbidden_aliases(roots: Mapping[str, str]) -> None:
    """Reject equality or containment outside the explicit role DAG."""

    for index, left_role in enumerate(TOP_LEVEL_ROLES):
        for right_role in TOP_LEVEL_ROLES[index + 1 :]:
            if _overlap(roots[left_role], roots[right_role]):
                raise StructureContractError(
                    f"role roots {left_role!r} and {right_role!r} may not alias or contain one another"
                )

    for roles in (SCRIPT_ROLES, RESULT_ROLES):
        for index, left_role in enumerate(roles):
            for right_role in roles[index + 1 :]:
                if _overlap(roots[left_role], roots[right_role]):
                    raise StructureContractError(
                        f"sibling role roots {left_role!r} and {right_role!r} may not alias or contain one another"
                    )


def validate_role_roots(raw_roots: Mapping[str, object]) -> dict[str, str]:
    """Normalize and validate the complete v1.1 role-root mapping."""

    if not isinstance(raw_roots, Mapping):
        raise StructureContractError("structure.roots must be a mapping")
    missing = set(ROLE_ROOTS) - set(raw_roots)
    extra = set(raw_roots) - set(ROLE_ROOTS)
    if missing:
        raise StructureContractError(f"structure.roots is missing roles: {', '.join(sorted(missing))}")
    if extra:
        raise StructureContractError(f"structure.roots contains unsupported roles: {', '.join(sorted(extra))}")

    roots = {role: _normalize_relative_path(raw_roots[role], role) for role in ROLE_ROOTS}
    for role in SCRIPT_ROLES:
        if not _is_descendant(roots[role], roots["scripts"]):
            raise StructureContractError(f"role root {role!r} must be nested below 'scripts'")
    for role in RESULT_ROLES:
        if not _is_descendant(roots[role], roots["results"]):
            raise StructureContractError(f"role root {role!r} must be nested below 'results'")
    validate_forbidden_aliases(roots)
    return roots


@dataclass(frozen=True, slots=True)
class StructureContract:
    """Resolved, current-version view of a declared project structure."""

    declared_version: str
    effective_version: str
    roots: Mapping[str, str]
    inferred_mappings: tuple[str, ...] = ()
    discovery: str = "declared_first"
    undeclared_files: str = "warn"

    def __post_init__(self) -> None:
        normalized = validate_role_roots(self.roots)
        object.__setattr__(self, "roots", MappingProxyType(normalized))
        if self.effective_version != CURRENT_CONTRACT_VERSION:
            raise StructureContractError("the normalized structure view must use effective version 1.1")

    @property
    def contract(self) -> str:
        return CURRENT_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "declared_version": self.declared_version,
            "effective_version": self.effective_version,
            "roots": dict(self.roots),
            "inferred_mappings": list(self.inferred_mappings),
            "discovery": self.discovery,
            "undeclared_files": self.undeclared_files,
        }


def resolve_structure_contract(config: Mapping[str, Any]) -> StructureContract:
    """Resolve config to v1.1 in memory without mutating or writing its source."""

    structure = config.get("structure") if isinstance(config, Mapping) else None
    if structure is None:
        inferred = tuple(f"{role}={path}" for role, path in DEFAULT_V11_ROOTS.items())
        return StructureContract(
            declared_version=LEGACY_CONTRACT_VERSION,
            effective_version=CURRENT_CONTRACT_VERSION,
            roots=DEFAULT_V11_ROOTS,
            inferred_mappings=inferred,
        )
    if not isinstance(structure, Mapping):
        raise StructureContractError("structure must be a mapping")
    declared = structure.get("contract")
    if declared is None:
        supplied = structure.get("roots", {})
        if supplied is not None and not isinstance(supplied, Mapping):
            raise StructureContractError("structure.roots must be a mapping")
        merged = dict(DEFAULT_V11_ROOTS)
        merged.update(supplied or {})
        inferred = tuple(f"{role}={path}" for role, path in merged.items())
        return StructureContract(
            declared_version=LEGACY_CONTRACT_VERSION,
            effective_version=CURRENT_CONTRACT_VERSION,
            roots=merged,
            inferred_mappings=inferred,
            discovery=str(structure.get("discovery", "declared_first")),
            undeclared_files=str(structure.get("undeclared_files", "warn")),
        )
    if declared != CURRENT_CONTRACT:
        raise StructureContractError(f"unsupported structure contract: {declared!r}")
    return StructureContract(
        declared_version=CURRENT_CONTRACT_VERSION,
        effective_version=CURRENT_CONTRACT_VERSION,
        roots=structure.get("roots", {}),
        discovery=str(structure.get("discovery", "declared_first")),
        undeclared_files=str(structure.get("undeclared_files", "warn")),
    )


resolve_contract = resolve_structure_contract
