from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_parser import module_default_contract_bool
from .project_paths import ProjectPathError, project_path_has_symlink_component, resolve_project_input


def canonical_docs_registry(project_path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    docs = []
    for precedence, entry in enumerate(canonical_docs_entries(config)):
        declaration = entry["path"]
        path_evidence = {
            "exists": False,
            "contained": False,
            "regular_file": False,
            "symlinked": False,
            "status": "invalid",
            "error": "",
        }
        try:
            prospective = resolve_project_input(
                project_path,
                declaration,
                must_exist=False,
                purpose=f"canonical_docs[{precedence + 1}].path",
            )
            path_evidence["contained"] = True
            path_evidence["symlinked"] = project_path_has_symlink_component(
                project_path,
                declaration,
                purpose=f"canonical_docs[{precedence + 1}].path",
            )
            if path_evidence["symlinked"]:
                path_evidence["status"] = "invalid"
                path_evidence["error"] = (
                    f"canonical_docs[{precedence + 1}].path must not be a symlink: {declaration!r}."
                )
            elif not prospective.exists():
                path_evidence["status"] = "missing"
            else:
                resolve_project_input(
                    project_path,
                    declaration,
                    purpose=f"canonical_docs[{precedence + 1}].path",
                )
                path_evidence.update({"exists": True, "regular_file": True, "status": "ready"})
        except (FileNotFoundError, ProjectPathError) as exc:
            path_evidence["error"] = str(exc)
        docs.append(
            {
                "precedence": precedence,
                "path": declaration,
                "label": entry["label"],
                **path_evidence,
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
    return module_default_contract_bool(config, "require_canonical_docs")


def missing_canonical_doc_message(missing: list[str]) -> str:
    return f"Missing canonical doc(s): {', '.join(missing)}."


def _normalize_doc_path(path: str) -> str:
    # Do not strip a leading slash: callers may inspect invalid configs and the
    # registry must report an unsafe declaration, never rewrite it as safe.
    return path.strip().replace("\\", "/")
