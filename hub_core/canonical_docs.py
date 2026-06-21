from __future__ import annotations

from pathlib import Path
from typing import Any


def canonical_docs_registry(project_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    docs = []
    for precedence, entry in enumerate(canonical_docs_entries(config)):
        doc_path = Path(project_path) / entry["path"]
        exists = doc_path.exists()
        docs.append(
            {
                "precedence": precedence,
                "path": entry["path"],
                "label": entry["label"],
                "exists": exists,
            }
        )
    missing = [doc["path"] for doc in docs if not doc["exists"]]
    return {
        "declared": bool(docs),
        "required": require_canonical_docs(config),
        "docs": docs,
        "missing": missing,
    }


def canonical_docs_entries(config: dict[str, Any]) -> list[dict[str, str]]:
    raw_docs = config.get("canonical_docs", []) if isinstance(config, dict) else []
    if not isinstance(raw_docs, list):
        return []

    entries: list[dict[str, str]] = []
    for item in raw_docs:
        if isinstance(item, str):
            path = item.strip()
            label = ""
        elif isinstance(item, dict):
            raw_path = item.get("path")
            path = raw_path.strip() if isinstance(raw_path, str) else ""
            raw_label = item.get("label")
            label = raw_label.strip() if isinstance(raw_label, str) else ""
        else:
            continue
        if path:
            entries.append({"path": _normalize_doc_path(path), "label": label})
    return entries


def require_canonical_docs(config: dict[str, Any]) -> bool:
    data_contract = config.get("data_contract", {}) if isinstance(config, dict) else {}
    return isinstance(data_contract, dict) and data_contract.get("require_canonical_docs") is True


def missing_canonical_doc_message(missing: list[str]) -> str:
    return f"Missing canonical doc(s): {', '.join(missing)}."


def _normalize_doc_path(path: str) -> str:
    return path.strip().replace("\\", "/").strip("/")
