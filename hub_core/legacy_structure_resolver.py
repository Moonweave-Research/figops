"""Read-only compatibility adapter for schema-less/v1.0 project layouts."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from .structure_contract_types import (
    LEGACY_CONTRACT_VERSION,
    StructureContract,
    StructureContractError,
    resolve_structure_contract,
)

LEGACY_DATA_ROOT = "results/data"
LEGACY_DISCOVERY_ROOTS = MappingProxyType(
    {
        "intermediate": LEGACY_DATA_ROOT,
        "source_data": LEGACY_DATA_ROOT,
    }
)


def is_legacy_structure_config(config: Mapping[str, Any]) -> bool:
    """Return whether *config* omits an explicit structure contract."""

    structure = config.get("structure") if isinstance(config, Mapping) else None
    return structure is None or (isinstance(structure, Mapping) and structure.get("contract") is None)


def resolve_legacy_structure(config: Mapping[str, Any]) -> StructureContract:
    """Resolve the historical layout in memory, without moving or writing files."""

    if not is_legacy_structure_config(config):
        raise StructureContractError("legacy resolver only accepts configs without structure.contract")
    resolved = resolve_structure_contract(config)
    if resolved.declared_version != LEGACY_CONTRACT_VERSION:
        raise StructureContractError("legacy resolver did not produce a declared v1.0 structure")
    return resolved


def legacy_structure_diagnostics(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the declared/effective versions and all inferred role mappings."""

    diagnostics = resolve_legacy_structure(config).to_dict()
    diagnostics["legacy_discovery_roots"] = dict(LEGACY_DISCOVERY_ROOTS)
    diagnostics["compatibility_warning"] = (
        "Legacy results/data is ambiguous between intermediate and source data; "
        "review `python orchestrator.py --project <project> --normalize-structure --dry-run`."
    )
    return diagnostics
