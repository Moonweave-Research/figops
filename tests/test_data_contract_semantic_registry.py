from hub_core import data_contract, data_contract_semantic_registry, data_contract_semantics
from hub_core.mcp.schemas import list_semantic_check_descriptions

registry = data_contract_semantic_registry


def test_semantic_registry_is_reexported_through_existing_contract_modules():
    assert data_contract_semantics.SEMANTIC_CHECK_DEFINITIONS is registry.SEMANTIC_CHECK_DEFINITIONS
    assert data_contract.SEMANTIC_CHECK_DEFINITIONS is registry.SEMANTIC_CHECK_DEFINITIONS
    assert data_contract._MONOTONIC_MODES is registry._MONOTONIC_MODES


def test_mcp_semantic_descriptions_are_backed_by_registry_definitions():
    described = {check["name"]: check for check in list_semantic_check_descriptions()}

    assert set(described) == set(registry.SEMANTIC_CHECK_DEFINITIONS)
    assert described["monotonic"]["schema"]["enum"] == sorted(registry._MONOTONIC_MODES)
    assert described["unit_coherence"]["example"] == registry.SEMANTIC_CHECK_DEFINITIONS["unit_coherence"]["example"]
