"""Config-facing parser and validator for ``figops-project-v1.1``.

The module is deliberately read-only.  It resolves logical project roles and
checks existing symlink/junction targets, but never creates roots or rewrites a
configuration file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .external_raw import ExternalRawError, validate_external_raw_descriptors
from .legacy_structure_resolver import (
    is_legacy_structure_config,
    legacy_structure_diagnostics,
    resolve_legacy_structure,
)
from .structure_contract_types import (
    CURRENT_CONTRACT,
    ROLE_ROOTS,
    StructureContract,
    StructureContractError,
    resolve_structure_contract,
)

ALLOWED_DISCOVERY_MODES = frozenset({"declared_first"})
ALLOWED_UNDECLARED_FILE_POLICIES = frozenset({"warn"})
STRUCTURE_KEYS = frozenset({"contract", "roots", "discovery", "undeclared_files"})
EXTERNAL_RAW_INPUT_PREFIX = "external_raw:"


def _validate_structure_shape(structure: object) -> None:
    if not isinstance(structure, Mapping):
        raise StructureContractError("structure must be a mapping")
    extra = set(structure) - STRUCTURE_KEYS
    if extra:
        raise StructureContractError(f"structure contains unsupported fields: {', '.join(sorted(extra))}")
    if structure.get("contract") != CURRENT_CONTRACT:
        raise StructureContractError(f"unsupported structure contract: {structure.get('contract')!r}")
    discovery = structure.get("discovery", "declared_first")
    if discovery not in ALLOWED_DISCOVERY_MODES:
        raise StructureContractError("structure.discovery must equal 'declared_first'")
    undeclared = structure.get("undeclared_files", "warn")
    if undeclared not in ALLOWED_UNDECLARED_FILE_POLICIES:
        raise StructureContractError("structure.undeclared_files must equal 'warn'")


def _validate_resolved_containment(project_root: str | Path, contract: StructureContract) -> None:
    root = Path(project_root).resolve()
    for role in ROLE_ROOTS:
        candidate = (root / contract.roots[role]).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise StructureContractError(
                f"structure.roots.{role} resolves outside the project root"
            ) from exc


def resolve_project_structure(
    config: Mapping[str, Any], *, project_root: str | Path | None = None
) -> StructureContract:
    """Return the normalized v1.1 view for current or legacy configuration."""

    if not isinstance(config, Mapping):
        raise StructureContractError("config must be a mapping")
    if is_legacy_structure_config(config):
        contract = resolve_legacy_structure(config)
    else:
        _validate_structure_shape(config.get("structure"))
        contract = resolve_structure_contract(config)
    if project_root is not None:
        _validate_resolved_containment(project_root, contract)
    return contract


def structure_diagnostics(
    config: Mapping[str, Any], *, project_root: str | Path | None = None
) -> dict[str, Any]:
    """Serialize version and inferred-mapping diagnostics for describe/audit callers."""

    contract = resolve_project_structure(config, project_root=project_root)
    if is_legacy_structure_config(config):
        return legacy_structure_diagnostics(config)
    return contract.to_dict()


def validate_external_raw_config(value: object) -> tuple[str, ...]:
    """Validate descriptors separately from project role roots."""

    return tuple(item.id for item in validate_external_raw_descriptors(value))


def validate_external_raw_references(config: Mapping[str, Any]) -> list[str]:
    """Validate producer ``external_raw:<id>`` inputs against declared descriptors."""

    errors: list[str] = []
    try:
        known = set(validate_external_raw_config(config.get("external_raw")))
    except ExternalRawError as exc:
        return [str(exc)]

    sections: tuple[tuple[str, object], ...] = (
        (
            "pipeline.analysis",
            config.get("pipeline", {}).get("analysis", [])
            if isinstance(config.get("pipeline"), Mapping)
            else [],
        ),
        ("figures", config.get("figures", [])),
        ("diagrams", config.get("diagrams", [])),
    )
    for section, records in sections:
        if not isinstance(records, list):
            continue
        for index, record in enumerate(records, 1):
            if not isinstance(record, Mapping) or not isinstance(record.get("inputs"), list):
                continue
            for input_index, value in enumerate(record["inputs"], 1):
                if not isinstance(value, str) or not value.startswith(EXTERNAL_RAW_INPUT_PREFIX):
                    continue
                descriptor_id = value[len(EXTERNAL_RAW_INPUT_PREFIX) :]
                if not descriptor_id or descriptor_id not in known:
                    errors.append(
                        f"{section}[{index}].inputs[{input_index}] references unknown external raw input: {value}"
                    )
    return errors


def validate_project_structure_config(
    config: Mapping[str, Any], *, project_root: str | Path | None = None
) -> list[str]:
    """Collect config-facing structure and external-raw errors."""

    errors: list[str] = []
    try:
        resolve_project_structure(config, project_root=project_root)
    except StructureContractError as exc:
        errors.append(str(exc))
    errors.extend(validate_external_raw_references(config))
    return errors


resolve_contract = resolve_project_structure
