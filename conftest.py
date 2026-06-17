"""Pytest root conftest — anchors rootdir and ensures hub_core is importable."""

import os
import sys
from pathlib import Path

import pytest

# Guarantee the hub root is on sys.path regardless of how pytest is invoked.
_HUB_ROOT = Path(__file__).resolve().parent
if str(_HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HUB_ROOT))


@pytest.fixture(autouse=True, scope="session")
def _enable_mcp_write_tools_for_tests():
    """The MCP server fails closed on write tools by default (security posture).
    The suite exercises write tools, so opt in via the documented env var. Tests that
    assert the fail-closed default override this locally (e.g. by popping the env var)."""
    previous = os.environ.get("GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED")
    os.environ["GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED"] = "1"
    yield
    if previous is None:
        os.environ.pop("GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED", None)
    else:
        os.environ["GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED"] = previous
