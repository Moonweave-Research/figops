from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_docs import canonical_docs_registry, missing_canonical_doc_message
from .config_placeholders import placeholder_message, placeholder_report
from .raw_integrity import raw_integrity_config, raw_integrity_drift_message, verify_raw_integrity


def validate_research_ops_contract(project_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    raw_integrity_status = _raw_integrity_status(project_path, config)
    if raw_integrity_status["configured"] and not raw_integrity_status["ok"]:
        message = "; ".join(
            raw_integrity_status.get("errors") or [raw_integrity_drift_message(raw_integrity_status)]
        )
        if raw_integrity_status.get("mode") == "strict":
            errors.append(message)
        else:
            warnings.append(message)

    canonical_registry = canonical_docs_registry(project_path, config)
    if canonical_registry["declared"] and canonical_registry["missing"]:
        message = missing_canonical_doc_message(canonical_registry["missing"])
        if canonical_registry["required"]:
            errors.append(message)
        else:
            warnings.append(message)

    placeholders = placeholder_report(config)
    if placeholders["detected"]:
        message = placeholder_message(placeholders)
        if placeholders["strict"]:
            errors.append(message)
        else:
            warnings.append(message)

    return {
        "errors": errors,
        "warnings": warnings,
        "raw_integrity_status": raw_integrity_status,
        "canonical_docs_registry": canonical_registry,
        "placeholder_report": placeholders,
    }


def _raw_integrity_status(project_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    if raw_integrity_config(config) is None:
        return {
            "configured": False,
            "sealed": False,
            "ok": True,
            "manifest_path": "",
            "mode": "",
            "sealed_at": "",
            "modified": [],
            "added": [],
            "removed": [],
            "errors": [],
        }
    return verify_raw_integrity(project_path, config)
