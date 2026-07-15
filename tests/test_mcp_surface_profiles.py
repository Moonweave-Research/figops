from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub_core.mcp import FigOpsMCPServer, GraphHubMCPServer
from hub_core.mcp.config import McpServerConfig
from hub_core.mcp.schemas import LEGACY_TOOL_NAMES, TOOL_NAMES, list_tool_definitions
from hub_core.mcp.security import LEGACY_WRITE_TOOL_NAMES, WRITE_TOOL_NAMES, is_write_tool_name
from hub_core.mcp.surface_profiles import V2_TOOL_NAMES
from hub_core.mcp.transport import _handle_json_rpc, _validate_tool_arguments
from scripts.gen_tool_reference import render_tool_reference


def _names(definitions: list[dict[str, object]]) -> list[str]:
    return [str(definition["name"]) for definition in definitions]


def _tools_list(server: FigOpsMCPServer) -> list[dict[str, object]]:
    response = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return response["result"]["tools"]


def test_figops_server_defaults_to_compact_ai_native_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPH_HUB_MCP_SURFACE_PROFILE", raising=False)
    server = FigOpsMCPServer(write_tools_enabled=True)

    definitions = _tools_list(server)
    assert server.surface_profile == "v2"
    assert _names(definitions) == list(V2_TOOL_NAMES)
    assert len(definitions) <= 7
    assert len(json.dumps(definitions, separators=(",", ":")).encode("utf-8")) <= 24 * 1024
    assert max(
        len(json.dumps(tool["inputSchema"], separators=(",", ":")).encode("utf-8"))
        for tool in definitions
    ) <= 6 * 1024


def test_writes_disabled_v2_discovery_omits_denied_renders() -> None:
    server = FigOpsMCPServer(surface_profile="v2", write_tools_enabled=False)
    definitions = _tools_list(server)

    assert _names(definitions) == [name for name in V2_TOOL_NAMES if not is_write_tool_name(name)]
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in definitions)
    assert {"figops.inspect_data", "figops.audit_artifact"} <= set(_names(definitions))


def test_compatibility_profile_exposes_frozen_fourteen_plus_thirteen() -> None:
    server = FigOpsMCPServer(surface_profile="compatibility", write_tools_enabled=True)
    definitions = _tools_list(server)
    expected = list(TOOL_NAMES[:14]) + list(LEGACY_TOOL_NAMES)

    assert _names(definitions) == expected
    assert len(definitions) == 27
    assert set(expected) <= set(server._handlers)
    alias_render = next(tool for tool in definitions if tool["name"] == "graphhub.render_csv_graph")
    assert alias_render["annotations"]["readOnlyHint"] is False
    assert alias_render["annotations"]["destructiveHint"] is True


def test_each_frozen_alias_resolves_to_a_live_guarded_handler(tmp_path: Path) -> None:
    server = FigOpsMCPServer(
        surface_profile="compatibility",
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=False,
    )

    for name in LEGACY_TOOL_NAMES:
        result = server.call_tool(name, {})
        assert "structuredContent" in result
        assert result["structuredContent"]["status"] in {"ok", "warning", "error"}


def test_writes_disabled_compatibility_omits_all_denied_aliases_and_canonical_tools() -> None:
    server = FigOpsMCPServer(surface_profile="compatibility", write_tools_enabled=False)
    names = set(_names(_tools_list(server)))

    assert not names.intersection(WRITE_TOOL_NAMES)
    assert not names.intersection(LEGACY_WRITE_TOOL_NAMES)
    assert {"figops.health", "graphhub.health", "figops.evaluate_publication_readiness"} <= names


def test_remembered_write_names_fail_before_creating_runtime_state(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    server = FigOpsMCPServer(
        surface_profile="compatibility",
        research_root=tmp_path,
        runtime_root=runtime_root,
        write_tools_enabled=False,
    )

    remembered_writes = [
        name for name in (*WRITE_TOOL_NAMES, *LEGACY_WRITE_TOOL_NAMES) if name in server._handlers
    ]
    for name in remembered_writes:
        result = server.call_tool(name, {"job_id": "must-not-exist"})
        assert result["isError"] is True
        assert result["structuredContent"]["error_category"] == "disabled"
    assert not runtime_root.exists()


def test_v2_describe_uses_summary_then_filtered_detail() -> None:
    server = FigOpsMCPServer(surface_profile="v2", write_tools_enabled=False)

    summary = server.call_tool("figops.describe", {})["structuredContent"]
    serialized = json.dumps(summary, separators=(",", ":"))
    assert summary["detail"] is None
    assert summary["surface_profile"] == "v2"
    assert "inputSchema" not in serialized
    assert len(serialized.encode("utf-8")) < 8 * 1024

    filtered = server.call_tool(
        "figops.describe", {"kind": "tools", "name": "figops.inspect_data"}
    )["structuredContent"]
    assert filtered["detail"]["name"] == "figops.inspect_data"
    assert filtered["detail"]["item"]["inputSchema"]["required"] == ["data_path"]

    invalid = server.call_tool("figops.describe", {"name": "figops.inspect_data"})
    assert invalid["isError"] is True


def test_render_prompts_are_optional_evidence_guidance_not_forced_choreography() -> None:
    v2 = FigOpsMCPServer(surface_profile="v2")
    csv_text = v2.get_prompt(
        "make_publication_graph_from_csv",
        {"data_path": "/allowed/data.csv", "x_column": "time", "y_column": "value"},
    )["messages"][0]["content"]["text"]
    project_text = v2.get_prompt(
        "render_project_figure", {"project_id": "project", "figure_id": "Fig1"}
    )["messages"][0]["content"]["text"]

    assert "figops.render_basic_csv" in csv_text
    assert '- x: "time"' in csv_text
    assert '- y: "value"' in csv_text
    assert "- x_column:" not in csv_text
    assert "- y_column:" not in csv_text
    callable_payload = json.loads(csv_text.split("Callable arguments:\n", 1)[1].split("\n\n", 1)[0])
    assert callable_payload["style_policy"] == "nature"
    assert "target_format" not in callable_payload
    assert "profile" not in callable_payload
    assert _validate_tool_arguments(
        "figops.render_basic_csv", callable_payload, v2.list_tool_definitions()
    ) == []
    assert "figops.render_project_script" in project_text
    assert "dry_run=true" not in csv_text + project_text
    assert "no dry-run or collect call is a prerequisite" in csv_text
    assert "preview" in csv_text.lower() and "preview" in project_text.lower()

    mutation_text = v2.get_prompt(
        "standardize_existing_graph_project", {"project_path": "/allowed/project"}
    )["messages"][0]["content"]["text"]
    assert "dry_run=true" in mutation_text
    assert "explicit user approval" in mutation_text


def test_profile_selection_from_config_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    mapped = McpServerConfig.from_mapping({"surface_profile": "compatibility"})
    assert FigOpsMCPServer(config=mapped).surface_profile == "compatibility"

    monkeypatch.setenv("GRAPH_HUB_MCP_SURFACE_PROFILE", "compat")
    assert FigOpsMCPServer().surface_profile == "compatibility"
    with pytest.raises(ValueError, match="Unknown MCP surface profile"):
        FigOpsMCPServer(surface_profile="unknown")


def test_profile_references_are_generated_on_demand_without_alias_schema_duplication() -> None:
    v2_reference = render_tool_reference("v2")
    compatibility_reference = render_tool_reference("compatibility")

    assert len(v2_reference.encode("utf-8")) < 64 * 1024
    assert len(v2_reference.encode("utf-8")) < len(render_tool_reference().encode("utf-8"))
    assert "### `figops.render_basic_csv`" in v2_reference
    assert "`graphhub.health` → `figops.health`" in compatibility_reference
    assert "### `graphhub.health`" not in compatibility_reference


def test_historical_graphhub_python_alias_selects_truthful_compatibility_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_HUB_MCP_SURFACE_PROFILE", "v2")
    server = GraphHubMCPServer(write_tools_enabled=False)
    names = set(_names(server.list_tool_definitions()))
    assert "graphhub.health" in names
    assert "figops.render_csv_graph" not in names
    assert "graphhub.render_csv_graph" not in names
    assert set(_names(list_tool_definitions())) == set(TOOL_NAMES)

    assert GraphHubMCPServer(surface_profile="compat").surface_profile == "compatibility"
    assert GraphHubMCPServer(config={"surface_profile": "legacy"}).surface_profile == "compatibility"
    with pytest.raises(ValueError, match="only supports surface_profile='compatibility'"):
        GraphHubMCPServer(surface_profile="v2")
    with pytest.raises(ValueError, match="only supports surface_profile='compatibility'"):
        GraphHubMCPServer(config=McpServerConfig(surface_profile="v2"))
