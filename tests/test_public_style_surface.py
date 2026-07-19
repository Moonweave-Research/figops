from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence

from hub_core.config_parser import ALLOWED_TARGET_FORMATS, PUBLIC_TARGET_FORMATS, validate_config
from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.schemas import list_tool_definitions
from themes.style_profiles import (
    PROFILE_ALIASES,
    PUBLIC_PROFILE_ALIASES,
    list_profiles,
    list_public_profiles,
    resolve_profile_name,
)


def _scalar_strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        strings = {str(key) for key in value}
        for item in value.values():
            strings.update(_scalar_strings(item))
        return strings
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        strings: set[str] = set()
        for item in value:
            strings.update(_scalar_strings(item))
        return strings
    return set()


def _compatibility_only_style_tokens() -> set[str]:
    hidden_targets = set(ALLOWED_TARGET_FORMATS) - set(PUBLIC_TARGET_FORMATS)
    hidden_profiles = set(list_profiles()) - set(list_public_profiles())
    hidden_aliases = set(PROFILE_ALIASES) - set(PUBLIC_PROFILE_ALIASES)
    hidden_alias_targets = {
        PROFILE_ALIASES[alias]
        for alias in hidden_aliases
        if PROFILE_ALIASES[alias] not in set(list_public_profiles())
    }
    return hidden_targets | hidden_profiles | hidden_aliases | hidden_alias_targets


def test_public_style_views_are_explicit_subsets_of_compatibility_contracts() -> None:
    assert set(PUBLIC_TARGET_FORMATS) < set(ALLOWED_TARGET_FORMATS)
    assert set(list_public_profiles()) < set(list_profiles())
    assert set(PUBLIC_PROFILE_ALIASES) < set(PROFILE_ALIASES)
    assert set(PUBLIC_PROFILE_ALIASES.values()) <= set(list_public_profiles())
    assert all(PROFILE_ALIASES[key] == value for key, value in PUBLIC_PROFILE_ALIASES.items())


def test_public_mcp_style_surfaces_exclude_every_compatibility_only_token() -> None:
    server = GraphHubMCPServer(write_tools_enabled=True)
    styles = server.call_tool("figops.list_styles", {})["structuredContent"]
    style_resource = json.loads(server.read_resource("figops://styles")["contents"][0]["text"])
    profile_resource = json.loads(server.read_resource("figops://profiles")["contents"][0]["text"])
    public_surface = {
        "tool_definitions": list_tool_definitions(profile="v2", write_tools_enabled=True),
        "styles": styles,
        "style_resource": style_resource,
        "profile_resource": profile_resource,
    }

    leaked = _scalar_strings(public_surface) & _compatibility_only_style_tokens()
    assert leaked == set()


def test_figops_help_excludes_compatibility_only_style_tokens() -> None:
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    words = set(re.findall(r"[A-Za-z0-9_]+", result.stdout.lower()))
    assert words.isdisjoint(_compatibility_only_style_tokens())
    assert set(PUBLIC_TARGET_FORMATS) <= words


def test_direct_config_and_profile_resolvers_keep_compatibility_values() -> None:
    hidden_target = next(iter(set(ALLOWED_TARGET_FORMATS) - set(PUBLIC_TARGET_FORMATS)))
    hidden_profile = next(iter(set(list_profiles()) - set(list_public_profiles())))
    config = {
        "project": {"name": "Compatibility fixture"},
        "visual_style": {"target_format": hidden_target, "font_scale": 1.0, "profile": hidden_profile},
        "language_policy": {"analysis_lang": "r", "plot_lang": "python"},
    }

    assert validate_config(config) == []
    assert resolve_profile_name(hidden_profile) == hidden_profile
