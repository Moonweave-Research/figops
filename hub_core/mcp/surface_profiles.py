"""Profile-aware MCP discovery and callable boundaries.

A profile controls both the contract placed in an agent's context and the
names that the server will dispatch.  Write-disabled servers may retain their
profile's write handlers only so the independent write guard can return its
stable disabled response; names from another profile are never callable.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from hub_core.mcp.security import is_write_tool_name

AI_NATIVE_PROFILE = "v2"
COMPATIBILITY_PROFILE = "compatibility"
SURFACE_PROFILES = (AI_NATIVE_PROFILE, COMPATIBILITY_PROFILE)

# Seven concise entry points are sufficient for the default figure-making
# loop.  Project discovery remains available through figops://projects.
V2_TOOL_NAMES = (
    "figops.health",
    "figops.describe",
    "figops.list_styles",
    "figops.inspect_data",
    "figops.render_basic_csv",
    "figops.render_project_script",
    "figops.audit_artifact",
)

# The frozen pre-v2 contract was 14 canonical tools and 13 graphhub aliases.
COMPATIBILITY_CANONICAL_COUNT = 14
COMPATIBILITY_ALIAS_COUNT = 13
COMPATIBILITY_CANONICAL_NAMES = (
    "figops.health",
    "figops.describe",
    "figops.list_styles",
    "figops.list_projects",
    "figops.inspect_project",
    "figops.validate_project",
    "figops.render_csv_graph",
    "figops.render_csv_multipanel",
    "figops.render_project_figure",
    "figops.collect_artifacts",
    "figops.scaffold_project",
    "figops.normalize_project_structure",
    "figops.batch_check",
    "figops.evaluate_publication_readiness",
)

DESCRIBE_KINDS = (
    "tools",
    "plot_types",
    "semantic_checks",
    "domain_helpers",
    "project_structure",
)


def normalize_surface_profile(value: Any, *, default: str = AI_NATIVE_PROFILE) -> str:
    """Return a public profile name or fail closed on unknown values."""

    normalized = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "ai_native": AI_NATIVE_PROFILE,
        "default": AI_NATIVE_PROFILE,
        "lean": AI_NATIVE_PROFILE,
        "legacy": COMPATIBILITY_PROFILE,
        "compat": COMPATIBILITY_PROFILE,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SURFACE_PROFILES:
        raise ValueError(
            f"Unknown MCP surface profile {value!r}; expected one of: {', '.join(SURFACE_PROFILES)}."
        )
    return normalized


def callable_tool_names(profile: str) -> tuple[str, ...]:
    """Return the complete, ordered dispatch boundary for one profile."""

    normalized = normalize_surface_profile(profile)
    if normalized == AI_NATIVE_PROFILE:
        return V2_TOOL_NAMES
    aliases = tuple(
        name.replace("figops.", "graphhub.", 1)
        for name in COMPATIBILITY_CANONICAL_NAMES[:COMPATIBILITY_ALIAS_COUNT]
    )
    return (*COMPATIBILITY_CANONICAL_NAMES, *aliases)


def select_tool_definitions(
    definitions: list[dict[str, Any]],
    *,
    profile: str,
    write_tools_enabled: bool,
) -> list[dict[str, Any]]:
    """Select and annotate the definitions truthfully exposed by one server."""

    profile = normalize_surface_profile(profile)
    by_name = {definition["name"]: definition for definition in definitions}
    if profile == AI_NATIVE_PROFILE:
        selected = [deepcopy(by_name[name]) for name in V2_TOOL_NAMES]
        selected = [_compact_describe_definition(item) for item in selected]
    else:
        canonical_names = list(COMPATIBILITY_CANONICAL_NAMES)
        selected = [deepcopy(by_name[name]) for name in canonical_names]
        for name in canonical_names[:COMPATIBILITY_ALIAS_COUNT]:
            alias = deepcopy(by_name[name])
            alias_name = name.replace("figops.", "graphhub.", 1)
            alias["name"] = alias_name
            alias["description"] = (
                f"Compatibility alias for {name}. " + str(alias.get("description", ""))
            ).strip()
            alias["annotations"] = _annotations_for_alias(alias_name, alias.get("annotations"))
            selected.append(alias)

    # Omission is less ambiguous than an annotation extension that older MCP
    # clients may ignore. The server's dispatch registry is independently
    # restricted to callable_tool_names(profile).
    if not write_tools_enabled:
        selected = [item for item in selected if not is_write_tool_name(str(item["name"]))]
    return selected


def compact_surface_description(
    *,
    arguments: dict[str, Any],
    profile: str,
    write_tools_enabled: bool,
    tool_definitions: list[dict[str, Any]],
    plot_types: list[dict[str, Any]],
    semantic_checks: list[dict[str, Any]],
    domain_helpers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a bounded summary, or one on-demand kind/name detail projection."""

    kind = arguments.get("kind")
    name = arguments.get("name")
    if name is not None and kind is None:
        raise ValueError("figops.describe name requires kind.")
    if kind is not None and kind not in DESCRIBE_KINDS:
        raise ValueError(f"figops.describe kind must be one of: {', '.join(DESCRIBE_KINDS)}.")

    collections = {
        "tools": tool_definitions,
        "plot_types": plot_types,
        "semantic_checks": semantic_checks,
        "domain_helpers": domain_helpers,
        "project_structure": [
            {
                "name": "project_structure",
                "purpose": (
                    "Read declared project roles, dependency graph, findings, unknowns, and "
                    "non-mutating proposed changes for one project."
                ),
            }
        ],
    }
    summaries = [
        {
            "kind": entry_kind,
            "count": len(items),
            "names": [str(item.get("name", "")) for item in items],
        }
        for entry_kind, items in collections.items()
    ]
    result: dict[str, Any] = {
        "surface_profile": profile,
        "available_profiles": list(SURFACE_PROFILES),
        "write_tools_enabled": write_tools_enabled,
        "kinds": summaries,
        "detail": None,
    }
    if kind is None:
        return result

    items = collections[kind]
    if name is None:
        result["detail"] = {
            "kind": kind,
            "items": [_compact_item(kind, item) for item in items],
        }
        return result

    matches = [item for item in items if item.get("name") == name]
    if not matches:
        raise ValueError(f"Unknown {kind} name: {name}.")
    result["detail"] = {"kind": kind, "name": name, "item": matches[0]}
    return result


def _compact_describe_definition(definition: dict[str, Any]) -> dict[str, Any]:
    if definition.get("name") != "figops.describe":
        return definition
    definition["description"] = (
        "Summarize capabilities or inspect one project's declared structure without writing files."
    )
    definition["inputSchema"] = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(DESCRIBE_KINDS)},
            "name": {"type": "string", "minLength": 1, "maxLength": 256},
            "project_id": {"type": "string", "minLength": 1, "maxLength": 256},
            "project_path": {"type": "string", "minLength": 1, "maxLength": 4096},
        },
        "additionalProperties": False,
    }
    definition["outputSchema"] = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "surface_profile": {"type": "string", "enum": list(SURFACE_PROFILES)},
            "available_profiles": {"type": "array", "items": {"type": "string"}},
            "write_tools_enabled": {"type": "boolean"},
            "kinds": {"type": "array", "items": {"type": "object"}},
            "detail": {"type": ["object", "null"]},
            "schema_version": {"type": "string"},
            "status_code": {"type": "string"},
            "roles": {"type": "object"},
            "graph": {"type": "object"},
            "findings": {"type": "array", "items": {"type": "object"}},
            "unknowns": {"type": "array", "items": {"type": "object"}},
            "proposed_changes": {"type": "array", "items": {"type": "object"}},
        },
        "additionalProperties": True,
    }
    return definition


def _compact_item(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    compact = {"name": str(item.get("name", ""))}
    if kind == "tools":
        compact["purpose"] = str(item.get("description", ""))
        compact["annotations"] = dict(item.get("annotations") or {})
    else:
        compact["purpose"] = str(item.get("purpose", ""))
    if kind == "plot_types":
        compact["capabilities"] = dict(item.get("capabilities") or {})
    return compact


def _annotations_for_alias(name: str, source: Any) -> dict[str, bool]:
    annotations = dict(source) if isinstance(source, dict) else {}
    writes = is_write_tool_name(name)
    annotations.update(
        {
            "readOnlyHint": not writes,
            "destructiveHint": writes,
            "idempotentHint": not writes,
            "openWorldHint": False,
        }
    )
    return annotations


__all__ = [
    "AI_NATIVE_PROFILE",
    "COMPATIBILITY_PROFILE",
    "COMPATIBILITY_CANONICAL_NAMES",
    "DESCRIBE_KINDS",
    "SURFACE_PROFILES",
    "V2_TOOL_NAMES",
    "callable_tool_names",
    "compact_surface_description",
    "normalize_surface_profile",
    "select_tool_definitions",
]
