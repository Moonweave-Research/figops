from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pytest

from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.schemas import (
    LEGACY_TOOL_NAMES,
    TOOL_HANDLER_NAMES,
    TOOL_NAMES,
    get_tool_handlers,
    list_prompt_definitions,
    list_tool_definitions,
)
from hub_core.mcp.transport import _handle_json_rpc
from scripts.gen_tool_reference import render_tool_reference

HUB_ROOT = Path(__file__).resolve().parent.parent
TOOL_REFERENCE_PATH = HUB_ROOT / "docs" / "tools.md"
WORKFLOW_PATH = HUB_ROOT / "docs" / "internal" / "protocols" / "00_agent_graph_workflow.md"
PLAYBOOK_PATH = HUB_ROOT / "docs" / "internal" / "protocols" / "05_mcp_tool_playbook.md"
TOOL_REFERENCE_HEADER_RE = re.compile(r"^### `(?P<name>figops\.[a-z0-9_]+)`$", re.MULTILINE)
TOOL_MENTION_RE = re.compile(r"\b(?:figops|graphhub)\.[a-z0-9_]+\b")


@dataclass(frozen=True, slots=True)
class RegistryNames:
    canonical_tools: frozenset[str]
    legacy_tools: frozenset[str]
    handler_tools: frozenset[str]
    definition_tools: frozenset[str]


@dataclass(frozen=True, slots=True)
class DiscoveryNames:
    server_handler_tools: frozenset[str]
    server_definition_tools: frozenset[str]
    json_rpc_tools: frozenset[str]


@dataclass(frozen=True, slots=True)
class DocsSurface:
    tool_reference_text: str
    workflow_text: str
    playbook_text: str
    prompt_texts: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AgentConsumabilitySurface:
    registry: RegistryNames
    discovery: DiscoveryNames
    docs: DocsSurface


def _assert_agent_consumability(surface: AgentConsumabilitySurface) -> None:
    canonical_tools = surface.registry.canonical_tools
    legacy_tools = surface.registry.legacy_tools
    all_tools = canonical_tools | legacy_tools
    expected_legacy_tools = frozenset(name.replace("figops.", "graphhub.", 1) for name in canonical_tools)

    assert all(name.startswith("figops.") for name in canonical_tools), "canonical tools must use figops.* names"
    assert legacy_tools == expected_legacy_tools, "legacy aliases must be derived from canonical figops.* names"

    missing_handler_tools = all_tools - surface.registry.handler_tools
    assert not missing_handler_tools, f"handlers missing registered tools: {sorted(missing_handler_tools)}"
    missing_server_handlers = all_tools - surface.discovery.server_handler_tools
    assert not missing_server_handlers, f"server handlers missing registered tools: {sorted(missing_server_handlers)}"

    assert surface.registry.definition_tools == canonical_tools, "list_tool_definitions must match canonical tools"
    assert surface.discovery.server_definition_tools == canonical_tools, (
        "GraphHubMCPServer.list_tool_definitions must match canonical tools"
    )
    assert surface.discovery.json_rpc_tools == canonical_tools, "JSON-RPC tools/list must expose canonical tools"

    committed_reference = surface.docs.tool_reference_text
    assert committed_reference == render_tool_reference(), "docs/tools.md is stale"
    documented_tools = frozenset(TOOL_REFERENCE_HEADER_RE.findall(committed_reference))
    missing_reference_tools = canonical_tools - documented_tools
    assert not missing_reference_tools, f"generated docs missing canonical tools: {sorted(missing_reference_tools)}"

    _assert_docs_only_reference_live_tools(
        {
            "docs/tools.md": committed_reference,
            str(WORKFLOW_PATH.relative_to(HUB_ROOT)): surface.docs.workflow_text,
            str(PLAYBOOK_PATH.relative_to(HUB_ROOT)): surface.docs.playbook_text,
        },
        all_tools,
    )

    playbook_tools = _tool_mentions(surface.docs.playbook_text)
    missing_guidance_tools = canonical_tools - playbook_tools
    assert not missing_guidance_tools, f"agent guidance missing canonical tools: {sorted(missing_guidance_tools)}"

    _assert_render_prompts_are_actionable(surface.docs.prompt_texts)


def _assert_docs_only_reference_live_tools(text_by_name: Mapping[str, str], live_tools: frozenset[str]) -> None:
    for name, text in text_by_name.items():
        unknown_tools = _tool_mentions(text) - live_tools
        assert not unknown_tools, f"{name} has unknown tool references: {sorted(unknown_tools)}"


def _assert_render_prompts_are_actionable(prompt_texts: Mapping[str, str]) -> None:
    csv_prompt = prompt_texts["make_publication_graph_from_csv"]
    project_prompt = prompt_texts["render_project_figure"]
    for tool_name in ("figops.list_styles", "figops.render_csv_graph", "figops.collect_artifacts"):
        assert tool_name in csv_prompt, f"CSV render prompt missing {tool_name}"
    for tool_name in ("figops.inspect_project", "figops.validate_project", "figops.render_project_figure"):
        assert tool_name in project_prompt, f"project render prompt missing {tool_name}"
    for text in (csv_prompt, project_prompt):
        assert "manual_review_needed" in text, "render prompt must preserve manual_review_needed guidance"


def _tool_mentions(text: str) -> frozenset[str]:
    return frozenset(TOOL_MENTION_RE.findall(text))


def _definition_names(definitions) -> frozenset[str]:
    return frozenset(definition["name"] for definition in definitions)


def _live_prompt_texts(server: GraphHubMCPServer) -> Mapping[str, str]:
    prompt_args = {
        "make_publication_graph_from_csv": {
            "data_path": "/allowed/data.csv",
            "x_column": "time",
            "y_column": "voltage",
        },
        "inspect_graph_project_quality": {"project_id": "project-1"},
        "standardize_existing_graph_project": {"project_path": "/allowed/project"},
        "render_project_figure": {"project_id": "project-1", "figure_id": "Fig1"},
    }
    prompts = {}
    for prompt in list_prompt_definitions():
        name = prompt["name"]
        payload = server.get_prompt(name, prompt_args[name])
        prompts[name] = payload["messages"][0]["content"]["text"]
    return prompts


def _live_surface() -> AgentConsumabilitySurface:
    server = GraphHubMCPServer()
    listed = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return AgentConsumabilitySurface(
        registry=RegistryNames(
            canonical_tools=frozenset(TOOL_NAMES),
            legacy_tools=frozenset(LEGACY_TOOL_NAMES),
            handler_tools=frozenset(TOOL_HANDLER_NAMES),
            definition_tools=_definition_names(list_tool_definitions()),
        ),
        discovery=DiscoveryNames(
            server_handler_tools=frozenset(get_tool_handlers(server)),
            server_definition_tools=_definition_names(server.list_tool_definitions()),
            json_rpc_tools=_definition_names(listed["result"]["tools"]),
        ),
        docs=DocsSurface(
            tool_reference_text=TOOL_REFERENCE_PATH.read_text(encoding="utf-8"),
            workflow_text=WORKFLOW_PATH.read_text(encoding="utf-8"),
            playbook_text=PLAYBOOK_PATH.read_text(encoding="utf-8"),
            prompt_texts=_live_prompt_texts(server),
        ),
    )


def test_live_mcp_surface_is_agent_consumable() -> None:
    _assert_agent_consumability(_live_surface())


def test_guard_rejects_tool_without_agent_guidance() -> None:
    surface = AgentConsumabilitySurface(
        registry=RegistryNames(
            canonical_tools=frozenset({"figops.health", "figops.new_tool"}),
            legacy_tools=frozenset({"graphhub.health", "graphhub.new_tool"}),
            handler_tools=frozenset({"figops.health", "figops.new_tool", "graphhub.health", "graphhub.new_tool"}),
            definition_tools=frozenset({"figops.health", "figops.new_tool"}),
        ),
        discovery=DiscoveryNames(
            server_handler_tools=frozenset(
                {"figops.health", "figops.new_tool", "graphhub.health", "graphhub.new_tool"}
            ),
            server_definition_tools=frozenset({"figops.health", "figops.new_tool"}),
            json_rpc_tools=frozenset({"figops.health", "figops.new_tool"}),
        ),
        docs=DocsSurface(
            tool_reference_text=render_tool_reference(),
            workflow_text="Call `figops.health`.",
            playbook_text="| `figops.health` | Readiness |",
            prompt_texts={
                "make_publication_graph_from_csv": (
                    "figops.list_styles figops.render_csv_graph figops.collect_artifacts manual_review_needed"
                ),
                "render_project_figure": (
                    "figops.inspect_project figops.validate_project figops.render_project_figure manual_review_needed"
                ),
            },
        ),
    )

    with pytest.raises(AssertionError, match="generated docs missing|agent guidance"):
        _assert_agent_consumability(surface)


def test_guard_rejects_legacy_alias_without_handler() -> None:
    surface = AgentConsumabilitySurface(
        registry=RegistryNames(
            canonical_tools=frozenset({"figops.health"}),
            legacy_tools=frozenset({"graphhub.health"}),
            handler_tools=frozenset({"figops.health"}),
            definition_tools=frozenset({"figops.health"}),
        ),
        discovery=DiscoveryNames(
            server_handler_tools=frozenset({"figops.health"}),
            server_definition_tools=frozenset({"figops.health"}),
            json_rpc_tools=frozenset({"figops.health"}),
        ),
        docs=DocsSurface(
            tool_reference_text=render_tool_reference(),
            workflow_text="Call `figops.health`.",
            playbook_text="| `figops.health` | Readiness |",
            prompt_texts={
                "make_publication_graph_from_csv": (
                    "figops.list_styles figops.render_csv_graph figops.collect_artifacts manual_review_needed"
                ),
                "render_project_figure": (
                    "figops.inspect_project figops.validate_project figops.render_project_figure manual_review_needed"
                ),
            },
        ),
    )

    with pytest.raises(AssertionError, match="handlers"):
        _assert_agent_consumability(surface)
