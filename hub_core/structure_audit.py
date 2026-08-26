"""Deterministic, diagnostic-only project structure audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .structure_inventory import build_structure_inventory


def audit_project_structure(
    project_root: str | Path,
    config: Mapping[str, Any],
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return stable diagnostics without proposing or performing mutations."""

    inventory = build_structure_inventory(project_root, config, config_path=config_path)
    return {
        "roles": inventory["roles"],
        "graph": inventory["graph"],
        "findings": inventory["findings"],
        "unknowns": inventory["unknowns"],
        "declared_vs_actual": inventory["declared_vs_actual"],
        "proposed_changes": [],
    }


structure_audit = audit_project_structure
