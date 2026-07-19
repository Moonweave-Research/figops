from __future__ import annotations

import copy

import pytest

from hub_core.structure_contract_types import (
    CURRENT_CONTRACT,
    CURRENT_CONTRACT_VERSION,
    DEFAULT_V11_ROOTS,
    LEGACY_CONTRACT_VERSION,
    StructureContractError,
    resolve_structure_contract,
    validate_role_roots,
)


def test_schema_less_structure_resolves_in_memory_without_rewrite() -> None:
    config = {"project": {"name": "legacy"}, "pipeline": {"analysis": []}}
    before = copy.deepcopy(config)

    resolved = resolve_structure_contract(config)

    assert config == before
    assert "structure" not in config
    assert resolved.declared_version == LEGACY_CONTRACT_VERSION
    assert resolved.effective_version == CURRENT_CONTRACT_VERSION
    assert resolved.contract == CURRENT_CONTRACT
    assert dict(resolved.roots) == dict(DEFAULT_V11_ROOTS)
    assert resolved.inferred_mappings


def test_current_contract_resolves_to_closed_v11_dto() -> None:
    config = {"structure": {"contract": CURRENT_CONTRACT, "roots": dict(DEFAULT_V11_ROOTS)}}
    resolved = resolve_structure_contract(config)
    assert resolved.declared_version == resolved.effective_version == "1.1"
    with pytest.raises(TypeError):
        resolved.roots["raw"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize(
    ("role", "path"),
    [
        ("raw", "results/raw"),
        ("analysis_scripts", "analysis"),
        ("figure_scripts", "hub_scripts/analysis/figures"),
        ("publication", "results/figures"),
        ("evidence", "results/tables/evidence"),
    ],
)
def test_role_dag_and_forbidden_aliases_fail_closed(role: str, path: str) -> None:
    roots = dict(DEFAULT_V11_ROOTS)
    roots[role] = path
    with pytest.raises(StructureContractError):
        validate_role_roots(roots)


@pytest.mark.parametrize("path", ["/tmp/raw", "C:/raw", "../raw", "."])
def test_role_roots_must_be_project_relative(path: str) -> None:
    roots = dict(DEFAULT_V11_ROOTS)
    roots["raw"] = path
    with pytest.raises(StructureContractError):
        validate_role_roots(roots)
