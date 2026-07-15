from __future__ import annotations

import glob
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Sequence

from .project_paths import normalize_project_relative_path, resolve_project_input, resolve_project_root

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
REQUIRED_PROVENANCE_HASHES = (
    "input_sha256",
    "config_sha256",
    "script_sha256",
    "environment_sha256",
    "output_sha256",
)
_HASH_ALIASES = {
    "input_sha256": ("input_sha256", "source_data_sha256", "copied_data_sha256"),
    "config_sha256": ("config_sha256",),
    "script_sha256": ("script_sha256",),
    "environment_sha256": ("environment_sha256",),
    "output_sha256": ("output_sha256",),
}


def provenance_hash_coverage(provenance: Any) -> dict[str, Any]:
    """Normalize required reproducibility hashes without inventing evidence."""

    normalized: dict[str, str] = {}
    if isinstance(provenance, Mapping):
        for canonical, aliases in _HASH_ALIASES.items():
            value = _first_sha256(provenance, aliases)
            if value:
                normalized[canonical] = value
    missing = [field for field in REQUIRED_PROVENANCE_HASHES if field not in normalized]
    return {
        "status": "passed" if not missing else "incomplete",
        "hashes": normalized,
        "missing": missing,
    }


def resolved_research_ops_evidence(config: Mapping[str, Any]) -> dict[str, Any]:
    """Record module defaults and scoped explicit opt-outs as resolved facts."""

    from .config_parser import data_contract_bool, module_default_contract_bool, project_role
    from .raw_integrity import raw_integrity_config

    parameters: dict[str, Any] = {}
    for key in (
        "require_figure_traceability",
        "require_canonical_docs",
        "forbid_todo_placeholders",
    ):
        explicit = data_contract_bool(dict(config), key)
        parameters[key] = {
            "value": module_default_contract_bool(dict(config), key),
            "source": "project_config" if explicit is not None else "module-default",
        }
    raw = raw_integrity_config(dict(config))
    raw_declared = config.get("data_contract", {}) if isinstance(config, Mapping) else {}
    raw_mapping = raw_declared.get("raw_integrity", {}) if isinstance(raw_declared, Mapping) else {}
    parameters["raw_integrity_mode"] = {
        "value": str((raw or {}).get("mode") or "off"),
        "source": "project_config" if isinstance(raw_mapping, Mapping) and "mode" in raw_mapping else "module-default",
    }
    role = project_role(dict(config))
    return {
        "id": "research-ops-v4",
        "version": "4",
        "source": "resolved-project-config",
        "project_role": role,
        "enabled_by_default": role == "module",
        "parameters": parameters,
    }


def _first_sha256(value: Any, aliases: tuple[str, ...]) -> str:
    if not isinstance(value, Mapping):
        return ""
    for alias in aliases:
        candidate = value.get(alias)
        if isinstance(candidate, str) and _SHA256.fullmatch(candidate):
            return candidate.lower()
    return ""


def _expand_declaration(project_root: Path, declaration: str) -> list[Path]:
    candidate = project_root / Path(declaration)
    if glob.has_magic(declaration):
        raw_matches = [Path(match) for match in glob.glob(str(candidate), recursive=True)]
    elif candidate.is_dir():
        resolve_project_input(
            project_root,
            declaration,
            regular_file=False,
            purpose="project input declaration",
        )
        raw_matches = list(candidate.rglob("*"))
    elif candidate.exists():
        raw_matches = [candidate]
    else:
        raw_matches = []
    resolved_matches: list[Path] = []
    for match in raw_matches:
        if not match.is_file():
            continue
        relative = match.relative_to(project_root).as_posix()
        resolved_matches.append(
            resolve_project_input(
                project_root,
                relative,
                purpose="project input declaration",
            )
        )
    return resolved_matches


def expand_project_input_files(
    project_dir: str | os.PathLike[str],
    declarations: Sequence[str],
    *,
    require_matches: bool,
) -> list[Path]:
    project_root = resolve_project_root(project_dir)

    expanded: set[Path] = set()
    for raw in declarations:
        declaration = normalize_project_relative_path(raw, purpose="project input declaration")
        matches = _expand_declaration(project_root, declaration)
        if require_matches and not matches:
            raise FileNotFoundError(f"input declaration matched zero files: {raw}")
        expanded.update(matches)
    return sorted(expanded, key=lambda path: path.relative_to(project_root).as_posix())


def expand_project_input_groups(
    project_dir: str | os.PathLike[str],
    declarations: Sequence[str],
) -> list[tuple[str, list[str]]]:
    """Expand contained project inputs while preserving declaration grouping."""

    project_root = resolve_project_root(project_dir)
    groups: list[tuple[str, list[str]]] = []
    for raw in declarations:
        declaration = normalize_project_relative_path(raw, purpose="project input declaration")
        matches = _expand_declaration(project_root, declaration)
        groups.append(
            (
                raw,
                [
                    str(path)
                    for path in sorted(set(matches), key=lambda path: path.relative_to(project_root).as_posix())
                ],
            )
        )
    return groups
