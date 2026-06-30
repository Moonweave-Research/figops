"""Project registry helpers used by legacy config listing."""

from __future__ import annotations

import os
import unicodedata
from typing import Any

import yaml


def load_registry_operational_states(root_dir: str) -> dict[str, str]:
    registry_path = os.path.join(root_dir, "ACTIVE_PROJECTS.yaml")
    if not os.path.exists(registry_path):
        return {}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f) or {}
    except Exception:
        return {}

    states: dict[str, str] = {}
    for section_name in ("active_projects", "published_project_archives", "incubation_candidates"):
        for item in registry.get(section_name, []) or []:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            op_state = item.get("operational_state")
            if isinstance(path, str) and path.strip() and isinstance(op_state, str) and op_state.strip():
                normalized_path = normalize_registry_path(path.strip())
                states.setdefault(normalized_path, op_state.strip())
    return states


def normalize_registry_path(path: Any) -> str:
    return unicodedata.normalize("NFC", str(path).strip())


def resolve_operational_state(operational_states: dict[str, str], project_path: str) -> str:
    normalized = normalize_registry_path(project_path)
    if normalized in operational_states:
        return operational_states[normalized]

    best_match: tuple[str, str] | None = None
    for registered_path, op_state in operational_states.items():
        prefix = registered_path + os.sep
        if normalized.startswith(prefix):
            if best_match is None or len(registered_path) > len(best_match[0]):
                best_match = (registered_path, op_state)

    if best_match is not None:
        return best_match[1]
    return "-"
