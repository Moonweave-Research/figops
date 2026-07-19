"""Canonical v1.1 project scaffold inventory and manifest generator.

This module is the only place that maps declared structure roles to scaffolded
directories and starter files.  Runtime paths are intentionally absent: they
are launcher-owned and live outside the project tree.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .project_structure_contract import resolve_project_structure
from .structure_contract_types import CURRENT_CONTRACT, ROLE_ROOTS

SCAFFOLD_MANIFEST_FILENAME = ".figops_scaffold_manifest.json"
BOOTSTRAP_RAW_FILENAME = "example.csv"
BOOTSTRAP_RAW_SEALED_AT = "2026-07-15T00:00:00+00:00"


def build_scaffold_config(
    hub_path: Path, project_name: str, target_format: str, *, font_scale: float = 1.0
) -> dict[str, Any]:
    """Load, specialize, and validate the frozen v1.1 config template."""

    from .config_parser import validate_config

    config = yaml.safe_load(
        build_scaffold_config_text(
            hub_path,
            project_name,
            target_format,
            font_scale=font_scale,
        )
    )
    if not isinstance(config, dict):
        raise ValueError("Scaffold template must contain a YAML mapping.")
    contract = resolve_project_structure(config)
    if contract.contract != CURRENT_CONTRACT:
        raise ValueError(f"Scaffold template must declare {CURRENT_CONTRACT}.")
    errors = validate_config(config)
    if errors:
        raise ValueError(f"Generated scaffold config is invalid: {errors}")
    return config


def build_scaffold_config_text(
    hub_path: Path, project_name: str, target_format: str, *, font_scale: float = 1.0
) -> str:
    """Render the packaged YAML without discarding comments or scalar quoting."""

    from .scaffold import load_config_template_text

    text = load_config_template_text(hub_path)
    text = _replace_section_scalar(text, "project", "name", json.dumps(project_name.strip(), ensure_ascii=False))
    style_value = json.dumps(target_format, ensure_ascii=False)
    text = _replace_section_scalar(text, "visual_style", "render_policy", style_value)
    text = _replace_section_scalar(text, "visual_style", "target_format", style_value)
    text = _replace_section_scalar(text, "visual_style", "font_scale", str(float(font_scale)))
    return text


def build_scaffold_manifest(
    *,
    project_root: Path,
    hub_path: Path,
    project_name: str,
    target_format: str,
    template: str,
    conventions: Any,
    font_scale: float = 1.0,
) -> dict[str, Any]:
    """Return the canonical, side-effect-free scaffold plan."""

    from .scaffold import (
        DEFAULT_ANALYZE_R,
        DEFAULT_DIAGRAM_PY,
        DEFAULT_PLOT_PY,
        DEFAULT_PROJECT_CONTEXT_PY,
        DEFAULT_RAW_CSV,
    )

    config_text = build_scaffold_config_text(
        hub_path,
        project_name,
        target_format,
        font_scale=font_scale,
    )
    config = yaml.safe_load(config_text)
    validated = build_scaffold_config(hub_path, project_name, target_format, font_scale=font_scale)
    if config != validated:
        raise ValueError("Rendered scaffold config does not match its validated representation.")
    contract = resolve_project_structure(config)
    roots = dict(contract.roots)
    directories = canonical_scaffold_directories(config)
    raw_path = _join(roots["raw"], BOOTSTRAP_RAW_FILENAME)
    raw_manifest_path = _join(roots["raw"], ".raw_manifest.json")
    raw_manifest = _raw_manifest_text(raw_path, DEFAULT_RAW_CSV)
    files = {
        "project_config.yaml": (config_text, "config"),
        raw_path: (DEFAULT_RAW_CSV, "raw"),
        raw_manifest_path: (raw_manifest, "raw"),
        _join(roots["analysis_scripts"], "analyze.R"): (DEFAULT_ANALYZE_R, "script.analysis"),
        _join(roots["shared_scripts"], "project_context.py"): (DEFAULT_PROJECT_CONTEXT_PY, "script.shared"),
        _join(roots["figure_scripts"], "plot.py"): (DEFAULT_PLOT_PY, "script.figure"),
        _join(roots["figure_scripts"], "device_cross_section.py"): (DEFAULT_DIAGRAM_PY, "script.figure"),
    }
    entries = [
        {
            "source": "",
            "destination": path,
            "operation": "mkdir",
            "kind": "directory",
            "role": _directory_role(path, roots),
            "reason": conventions.scaffold_directory_reason(),
            "status": "planned",
            "checksum": "",
        }
        for path in directories
    ]
    entries.extend(
        {
            "source": "",
            "destination": path,
            "operation": "write",
            "kind": "file",
            "role": role,
            "reason": conventions.scaffold_file_reason(),
            "status": "planned",
            "checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
        }
        for path, (content, role) in files.items()
    )
    return {
        "operation": "scaffold_project",
        "project_root": str(project_root),
        "project_name": project_name,
        "template": template,
        "structure": {
            "contract": contract.contract,
            "roots": roots,
            "discovery": contract.discovery,
            "undeclared_files": contract.undeclared_files,
        },
        "boundaries": {
            "durable_results": [roots[role] for role in ROLE_ROOTS if role in {
                "intermediate", "source_data", "tables", "figures", "evidence", "publication"
            }],
            "runtime": {
                "included_in_project": False,
                "configured_externally": True,
                "disposable": True,
            },
        },
        "entries": entries,
    }


def canonical_scaffold_directories(config: dict[str, Any]) -> tuple[str, ...]:
    """Return all and only project/durable directories implied by role roots."""

    roots = resolve_project_structure(config).roots
    ordered = ["."]
    seen = {"."}
    for role in ROLE_ROOTS:
        path = PurePosixPath(roots[role])
        for index in range(1, len(path.parts) + 1):
            candidate = PurePosixPath(*path.parts[:index]).as_posix()
            if candidate not in seen:
                ordered.append(candidate)
                seen.add(candidate)
    return tuple(ordered)


def _raw_manifest_text(raw_path: str, content: str) -> str:
    payload = {
        "_metadata": {"sealed_at": BOOTSTRAP_RAW_SEALED_AT, "algorithm": "sha256"},
        raw_path: hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _join(root: str, name: str) -> str:
    return (PurePosixPath(root) / name).as_posix()


def _directory_role(path: str, roots: dict[str, str]) -> str:
    matches = [role for role, root in roots.items() if path == root]
    return matches[0] if matches else "container"


def _replace_section_scalar(text: str, section: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    in_section = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if line and not line[0].isspace() and stripped and not stripped.startswith("#"):
            in_section = stripped == f"{section}:"
            continue
        if not in_section or not line.startswith(f"  {key}:"):
            continue
        body = line.rstrip("\r\n")
        newline = line[len(body) :]
        comment_index = body.find("#")
        comment = f" {body[comment_index:].strip()}" if comment_index >= 0 else ""
        lines[index] = f"  {key}: {value}{comment}{newline}"
        replaced = True
        break
    if not replaced:
        raise ValueError(f"Scaffold template is missing {section}.{key}.")
    return "".join(lines)
