from __future__ import annotations

from .project_roles import DEFAULT_PROJECT_ROLE, project_role


def data_contract_bool(config: dict, key: str) -> bool | None:
    data_contract = config.get("data_contract", {}) if isinstance(config, dict) else {}
    if not isinstance(data_contract, dict):
        return None
    value = data_contract.get(key)
    return value if isinstance(value, bool) else None


def module_default_contract_bool(config: dict, key: str) -> bool:
    explicit = data_contract_bool(config, key)
    if explicit is not None:
        return explicit
    return project_role(config) == DEFAULT_PROJECT_ROLE
