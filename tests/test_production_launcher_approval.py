"""Contract tests for the secure production MCP entry point.

The historical :class:`GraphHubMCPServer` constructor remains available for
compatibility clients.  The graphhub/figops stdio entry point has a separate
factory so that production cannot accidentally inherit the compatibility
server's token-only approval mode.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import graphhub_mcp_server
import hub_core.mcp as mcp_module
from hub_core.approval_authority import ApprovalAuthorityRoot
from hub_core.mcp import FigOpsMCPServer, GraphHubMCPServer, McpServerConfig


def _config(root: Path, **overrides: object) -> McpServerConfig:
    """Build an explicit, side-effect-free config for factory tests."""

    values: dict[str, object] = {
        "hub_path": root,
        "research_root": root,
        "runtime_root": root / "runtime",
    }
    values.update(overrides)
    return McpServerConfig.from_mapping(values)


def _assert_secure_production_server(server: object) -> None:
    """Assert the non-negotiable trust boundary of the production factory."""

    assert type(server) is FigOpsMCPServer
    assert server.require_host_approval is True
    assert type(server.host_authority_root) is ApprovalAuthorityRoot
    assert server.host_authority_root is server.host_authority_index


def test_production_factory_returns_secure_figops_server(tmp_path: Path) -> None:
    config = _config(tmp_path)

    server = graphhub_mcp_server._build_production_server(config)
    _assert_secure_production_server(server)


def test_production_factory_cannot_be_downgraded_by_config_or_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # ``require_host_approval`` is deliberately not an operator/config value;
    # retain this adversarial key to prove a false value cannot reach the
    # production trust boundary.  A compatibility surface and write opt-in
    # likewise must not select GraphHubMCPServer or token-only mode.
    config = McpServerConfig.from_mapping(
        {
            "hub_path": tmp_path,
            "research_root": tmp_path,
            "runtime_root": tmp_path / "runtime",
            "surface_profile": "compatibility",
            "write_tools_enabled": True,
            "require_host_approval": False,
        }
    )
    monkeypatch.setenv("GRAPH_HUB_MCP_REQUIRE_HOST_APPROVAL", "0")
    monkeypatch.setenv("GRAPH_HUB_MCP_SURFACE_PROFILE", "compatibility")
    monkeypatch.setenv("GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED", "1")

    server = graphhub_mcp_server._build_production_server(config)

    _assert_secure_production_server(server)

    # Exercise the real environment parser as well.  None of the supported
    # environment fields is allowed to become a secure-mode opt-out.
    env_config = McpServerConfig.from_env().overlay(
        hub_path=tmp_path,
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime-env",
        write_tools_enabled=True,
    )
    env_server = graphhub_mcp_server._build_production_server(env_config)
    _assert_secure_production_server(env_server)


def test_smoke_constructs_server_through_secure_production_factory(tmp_path: Path) -> None:
    config = _config(tmp_path)
    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    class SmokeServer:
        def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            if name == "figops.health":
                return {"structuredContent": {"status": "ok"}}
            if name == "figops.list_styles":
                return {"structuredContent": {"status": "ok", "target_formats": ["default"]}}
            raise AssertionError(f"unexpected smoke tool: {name}")

    def fake_factory(config: object, *args: object, **kwargs: object) -> SmokeServer:
        assert not args
        calls.append((config, (), kwargs))
        return SmokeServer()

    with (
        patch.object(graphhub_mcp_server, "run_doctor", return_value={"checks": []}),
        patch.object(graphhub_mcp_server, "_build_production_server", side_effect=fake_factory),
    ):
        result = graphhub_mcp_server._run_smoke(config)

    assert result == 0
    assert len(calls) == 1
    assert calls[0][0] is config
    # Smoke is read-only, but it must still use the production factory.  If
    # the factory accepts this knob, it should disable MCP initialize framing;
    # an omitted knob is also valid for a factory whose default is read-only.
    assert calls[0][2].get("require_initialize", False) is False


def test_stdio_cli_routes_through_secure_production_factory(tmp_path: Path) -> None:
    sentinel_server = object()
    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def fake_factory(config: object, *args: object, **kwargs: object) -> object:
        calls.append((config, args, kwargs))
        return sentinel_server

    argv = [
        "graphhub_mcp_server.py",
        "--hub-path",
        str(tmp_path),
        "--research-root",
        str(tmp_path),
        "--runtime-root",
        str(tmp_path / "runtime"),
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(graphhub_mcp_server, "_build_production_server", side_effect=fake_factory),
        patch.object(mcp_module, "run_stdio_server", return_value=23) as run_stdio,
    ):
        result = graphhub_mcp_server.main()

    assert result == 23
    assert len(calls) == 1
    assert calls[0][2].get("require_initialize") is True
    run_stdio.assert_called_once_with(sentinel_server)


def test_direct_graphhub_server_remains_compatibility_token_only(tmp_path: Path) -> None:
    server = GraphHubMCPServer(config=_config(tmp_path, surface_profile="compatibility"))

    assert type(server) is GraphHubMCPServer
    assert server.surface_profile == "compatibility"
    assert server.require_host_approval is False
    assert server.host_authority_root is None
